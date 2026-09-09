"""
Servicio de respaldo integral del sistema — vuelca la base de datos con
pg_dump y comprime los archivos subidos (logos, fotos, QR, vales, etc.),
todo bajo BACKUP_DIR. Es la versión "desde la web" de scripts/backup.sh y
scripts/restore.sh (que siguen sirviendo para restaurar a mano si el
sistema completo estuviera caído).

Cada backup incluye:
  - database.sql      → volcado completo con pg_dump (plain text, --clean --if-exists)
  - uploads.tar.gz    → logos, fotos, QR, vales, configs de branding y notificaciones
  - tenants.json      → registro de clientes (fuente de verdad del multi-tenant)
  - manifest.json     → metadatos: timestamp UTC+Chile, tamaños, resultado de verificación

La verificación automática (post-create y bajo demanda) comprueba:
  1. Que database.sql existe y contiene al menos 1 CREATE TABLE
  2. Que uploads.tar.gz se puede abrir correctamente
  No hace un restore real — es solo integridad de archivos, O(1) en tiempo.
"""
import asyncio
import io
import json
import re
import shutil
import tarfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import settings

BACKUP_DIR = Path(settings.BACKUP_DIR)
UPLOAD_DIR = Path(settings.UPLOAD_DIR)

# tenants.json está en la raíz del contenedor (app/tenants.json montado read-only)
_TENANTS_FILE = Path("app/tenants.json")

# Nombre de backup = timestamp UTC que nosotros mismos generamos (o validado
# contra este mismo patrón al subir uno) — nunca se arma a partir de un path
# que mande el usuario, así no hay path traversal posible.
_NAME_PATTERN = re.compile(r"^\d{8}_\d{6}(_subido)?$")


class BackupError(Exception):
    pass


def _db_connection_args() -> dict:
    url = make_url(settings.DATABASE_URL)
    return {
        "host": url.host or "localhost",
        "port": str(url.port or 5432),
        "user": url.username or "panol",
        "password": url.password or "",
        "dbname": url.database or "panol_db",
    }


async def _run(cmd: list[str], *, env: dict, stdin_bytes: bytes | None = None) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if stdin_bytes is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    stdout, stderr = await proc.communicate(input=stdin_bytes)
    if proc.returncode != 0:
        raise BackupError(stderr.decode(errors="replace")[-2000:] or "El comando falló sin detalle")
    return stdout


def _parse_backup_dt(name: str) -> datetime:
    """
    Parsea el nombre de carpeta (YYYYmmdd_HHMMSS, siempre UTC) y devuelve
    un datetime timezone-aware en hora Chile para que el frontend lo muestre
    correctamente sin ninguna conversión extra.
    Si zoneinfo no está disponible (Python < 3.9 sin backport) devuelve UTC.
    """
    try:
        base = name.split("_subido")[0]
        dt_utc = datetime.strptime(base, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        try:
            from zoneinfo import ZoneInfo
            return dt_utc.astimezone(ZoneInfo("America/Santiago"))
        except Exception:
            return dt_utc
    except Exception:
        return datetime.now(tz=timezone.utc)


@dataclass
class BackupInfo:
    name: str
    created_at: datetime
    database_size: int | None
    uploads_size: int | None
    verified: bool | None = None          # None=no verificado, True=OK, False=fallido
    table_count: int | None = None        # CREATE TABLE encontrados en el SQL
    upload_file_count: int | None = None  # Archivos en el tar.gz
    includes_tenants: bool = False        # Si tiene tenants.json
    verification_errors: list[str] = field(default_factory=list)


def _load_manifest(backup_dir: Path) -> dict:
    manifest_file = backup_dir / "manifest.json"
    if manifest_file.exists():
        try:
            return json.loads(manifest_file.read_text())
        except Exception:
            pass
    return {}


def list_backups() -> list[BackupInfo]:
    if not BACKUP_DIR.exists():
        return []
    backups = []
    for entry in sorted(BACKUP_DIR.iterdir(), reverse=True):
        if not entry.is_dir() or not _NAME_PATTERN.match(entry.name):
            continue
        db_file = entry / "database.sql"
        uploads_file = entry / "uploads.tar.gz"
        manifest = _load_manifest(entry)
        backups.append(BackupInfo(
            name=entry.name,
            created_at=_parse_backup_dt(entry.name),
            database_size=db_file.stat().st_size if db_file.exists() else None,
            uploads_size=uploads_file.stat().st_size if uploads_file.exists() else None,
            verified=manifest.get("ok"),
            table_count=manifest.get("table_count"),
            upload_file_count=manifest.get("upload_file_count"),
            includes_tenants=(entry / "tenants.json").exists(),
            verification_errors=manifest.get("errors", []),
        ))
    return backups


def verify_backup(name: str) -> dict:
    """
    Verifica la integridad de un backup SIN hacer restore.
    Comprobaciones:
      1. database.sql existe y tiene al menos 1 CREATE TABLE
      2. uploads.tar.gz se puede abrir y listar su contenido
    Guarda el resultado en manifest.json dentro del backup.
    Devuelve el dict de resultado (ok, table_count, upload_file_count, errors).
    """
    target_dir = _validated_backup_dir(name)
    result: dict = {
        "ok": True,
        "errors": [],
        "table_count": None,
        "upload_file_count": None,
    }

    # ── 1. Verificar SQL ────────────────────────────────────────────────────
    db_file = target_dir / "database.sql"
    if db_file.exists():
        try:
            content = db_file.read_text(errors="replace")
            table_count = content.count("CREATE TABLE")
            result["table_count"] = table_count
            if table_count == 0:
                result["errors"].append(
                    "database.sql no contiene ningún CREATE TABLE — posiblemente vacío o corrupto"
                )
                result["ok"] = False
        except Exception as exc:
            result["errors"].append(f"No se pudo leer database.sql: {exc}")
            result["ok"] = False
    else:
        result["errors"].append("No existe database.sql en este backup")
        result["ok"] = False

    # ── 2. Verificar tar.gz de uploads ─────────────────────────────────────
    uploads_file = target_dir / "uploads.tar.gz"
    if uploads_file.exists():
        try:
            with tarfile.open(uploads_file, "r:gz") as tar:
                members = tar.getmembers()
                result["upload_file_count"] = len(members)
        except Exception as exc:
            result["errors"].append(f"uploads.tar.gz corrupto: {exc}")
            result["ok"] = False

    # ── Guardar manifest ────────────────────────────────────────────────────
    manifest = {
        "verified_at": datetime.now(tz=timezone.utc).isoformat(),
        **result,
    }
    (target_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return result


async def create_backup() -> BackupInfo:
    """
    Genera un backup completo:
      1. pg_dump de la base de datos
      2. tar.gz de uploads/
      3. Copia de tenants.json
      4. Verificación automática de integridad
      5. manifest.json con resultado
    """
    conn = _db_connection_args()
    name = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    target_dir = BACKUP_DIR / name
    target_dir.mkdir(parents=True, exist_ok=True)

    env = {"PGPASSWORD": conn["password"], "PATH": "/usr/bin:/usr/local/bin"}

    # ── pg_dump ─────────────────────────────────────────────────────────────
    try:
        dump = await _run(
            [
                "pg_dump", "-h", conn["host"], "-p", conn["port"], "-U", conn["user"],
                "--clean", "--if-exists", conn["dbname"],
            ],
            env=env,
        )
    except FileNotFoundError:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise BackupError(
            "pg_dump no está instalado en este servidor — hace falta el paquete 'postgresql-client'."
        )
    (target_dir / "database.sql").write_bytes(dump)

    # ── uploads.tar.gz ──────────────────────────────────────────────────────
    if UPLOAD_DIR.exists():
        with tarfile.open(target_dir / "uploads.tar.gz", "w:gz") as tar:
            tar.add(UPLOAD_DIR, arcname="uploads")

    # ── tenants.json ─────────────────────────────────────────────────────────
    # Es la fuente de verdad del multi-tenant: sin este archivo, un restore
    # deja el sistema con la BD restaurada pero sin ningún cliente registrado.
    if _TENANTS_FILE.exists():
        shutil.copy2(_TENANTS_FILE, target_dir / "tenants.json")

    # ── Verificación automática ──────────────────────────────────────────────
    verify_backup(name)  # escribe manifest.json con el resultado

    # ── Recargar el manifest para devolver estado completo ───────────────────
    manifest = _load_manifest(target_dir)
    db_stat = (target_dir / "database.sql").stat()
    uploads_path = target_dir / "uploads.tar.gz"
    return BackupInfo(
        name=name,
        created_at=_parse_backup_dt(name),
        database_size=db_stat.st_size,
        uploads_size=uploads_path.stat().st_size if uploads_path.exists() else None,
        verified=manifest.get("ok"),
        table_count=manifest.get("table_count"),
        upload_file_count=manifest.get("upload_file_count"),
        includes_tenants=(target_dir / "tenants.json").exists(),
        verification_errors=manifest.get("errors", []),
    )


def _validated_backup_dir(name: str) -> Path:
    if not _NAME_PATTERN.match(name):
        raise BackupError("Nombre de backup inválido")
    target_dir = BACKUP_DIR / name
    if not target_dir.is_dir():
        raise BackupError("Ese backup no existe")
    return target_dir


def backup_zip_bytes(name: str) -> bytes:
    """Empaqueta database.sql + uploads.tar.gz + tenants.json + manifest.json en un único .zip."""
    target_dir = _validated_backup_dir(name)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename in ("database.sql", "uploads.tar.gz", "tenants.json", "manifest.json"):
            path = target_dir / filename
            if path.exists():
                zf.write(path, arcname=filename)
    return buf.getvalue()


def save_uploaded_backup(zip_bytes: bytes) -> BackupInfo:
    """
    Guarda un backup subido desde afuera (bajado de otro servidor) como un
    backup más, listo para restaurar. No lo restaura solo — eso es explícito.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise BackupError("El archivo no es un .zip válido")

    names = set(zf.namelist())
    if "database.sql" not in names:
        raise BackupError("El .zip tiene que incluir 'database.sql' (generado por este mismo módulo)")

    name = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S") + "_subido"
    target_dir = BACKUP_DIR / name
    target_dir.mkdir(parents=True, exist_ok=True)
    zf.extract("database.sql", target_dir)
    if "uploads.tar.gz" in names:
        zf.extract("uploads.tar.gz", target_dir)
    if "tenants.json" in names:
        zf.extract("tenants.json", target_dir)

    # Verificar automáticamente el backup subido también
    verify_backup(name)

    manifest = _load_manifest(target_dir)
    stat = (target_dir / "database.sql").stat()
    uploads_path = target_dir / "uploads.tar.gz"
    return BackupInfo(
        name=name,
        created_at=_parse_backup_dt(name),
        database_size=stat.st_size,
        uploads_size=uploads_path.stat().st_size if uploads_path.exists() else None,
        verified=manifest.get("ok"),
        table_count=manifest.get("table_count"),
        upload_file_count=manifest.get("upload_file_count"),
        includes_tenants=(target_dir / "tenants.json").exists(),
        verification_errors=manifest.get("errors", []),
    )


async def restore_backup(name: str) -> None:
    """
    Restaura un backup ya guardado en el servidor. SOBREESCRIBE la base de
    datos actual y los archivos subidos — es destructivo a propósito.
    Si el backup incluye tenants.json, también lo restaura.
    """
    target_dir = _validated_backup_dir(name)
    conn = _db_connection_args()
    env = {"PGPASSWORD": conn["password"], "PATH": "/usr/bin:/usr/local/bin"}

    db_file = target_dir / "database.sql"
    if db_file.exists():
        if not settings.DATABASE_URL.startswith("sqlite"):
            from app.core.database import engine as _app_engine
            await _app_engine.dispose()
            try:
                await _run(
                    ["psql", "-h", conn["host"], "-p", conn["port"], "-U", conn["user"],
                     "-d", conn["dbname"], "-c",
                     "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                     "WHERE datname = current_database() AND pid <> pg_backend_pid();"],
                    env=env,
                )
            except FileNotFoundError:
                pass

        try:
            await _run(
                [
                    "psql", "-h", conn["host"], "-p", conn["port"], "-U", conn["user"],
                    "-d", conn["dbname"], "-v", "ON_ERROR_STOP=1", "--single-transaction",
                ],
                env=env,
                stdin_bytes=db_file.read_bytes(),
            )
        except FileNotFoundError:
            raise BackupError(
                "psql no está instalado en este servidor — hace falta el paquete 'postgresql-client'."
            )

    # ── uploads ─────────────────────────────────────────────────────────────
    uploads_file = target_dir / "uploads.tar.gz"
    if uploads_file.exists():
        if UPLOAD_DIR.exists():
            shutil.rmtree(UPLOAD_DIR)
        UPLOAD_DIR.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(uploads_file, "r:gz") as tar:
            tar.extractall(UPLOAD_DIR.parent, filter="data")

    # ── tenants.json ─────────────────────────────────────────────────────────
    # Solo se puede restaurar si el archivo no está montado read-only (en
    # producción puede estarlo — en ese caso se omite en silencio y el admin
    # debe actualizarlo a mano si cambió entre backups).
    tenant_src = target_dir / "tenants.json"
    if tenant_src.exists() and _TENANTS_FILE.exists():
        try:
            shutil.copy2(tenant_src, _TENANTS_FILE)
        except OSError:
            pass  # montado read-only — ignorar
