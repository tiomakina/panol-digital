"""
Servicio de respaldo integral del sistema — vuelca la base de datos con
pg_dump y comprime los archivos subidos (logos, fotos, QR, vales, etc.),
todo bajo BACKUP_DIR. Es la versión "desde la web" de scripts/backup.sh y
scripts/restore.sh (que siguen sirviendo para restaurar a mano si el
sistema completo estuviera caído).
"""
import asyncio
import io
import re
import shutil
import tarfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import settings

BACKUP_DIR = Path(settings.BACKUP_DIR)
UPLOAD_DIR = Path(settings.UPLOAD_DIR)

# Nombre de backup = timestamp que nosotros mismos generamos (o que ya
# viene validado contra este mismo patrón al subir uno) — nunca se arma a
# partir de un path que mande el usuario tal cual, así no hay forma de
# hacer path traversal con "../../etc/passwd" ni nada por el estilo.
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


@dataclass
class BackupInfo:
    name: str
    created_at: datetime
    database_size: int | None
    uploads_size: int | None


def list_backups() -> list[BackupInfo]:
    if not BACKUP_DIR.exists():
        return []
    backups = []
    for entry in sorted(BACKUP_DIR.iterdir(), reverse=True):
        if not entry.is_dir() or not _NAME_PATTERN.match(entry.name):
            continue
        db_file = entry / "database.sql"
        uploads_file = entry / "uploads.tar.gz"
        backups.append(BackupInfo(
            name=entry.name,
            created_at=datetime.fromtimestamp(entry.stat().st_mtime),
            database_size=db_file.stat().st_size if db_file.exists() else None,
            uploads_size=uploads_file.stat().st_size if uploads_file.exists() else None,
        ))
    return backups


async def create_backup() -> BackupInfo:
    """Genera un backup nuevo: pg_dump de la base + tar.gz de los uploads."""
    conn = _db_connection_args()
    name = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    target_dir = BACKUP_DIR / name
    target_dir.mkdir(parents=True, exist_ok=True)

    env = {"PGPASSWORD": conn["password"], "PATH": "/usr/bin:/usr/local/bin"}
    try:
        dump = await _run(
            [
                "pg_dump", "-h", conn["host"], "-p", conn["port"], "-U", conn["user"],
                # --clean --if-exists: el dump incluye un DROP ... IF EXISTS
                # antes de cada CREATE, así psql lo puede aplicar tanto sobre
                # una base vacía (catástrofe real) como sobre una que ya
                # tiene datos (volver a un backup anterior) — sin esto,
                # restaurar sobre una base no vacía revienta con "ya existe"
                # en el primer CREATE TABLE/TYPE.
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

    if UPLOAD_DIR.exists():
        with tarfile.open(target_dir / "uploads.tar.gz", "w:gz") as tar:
            tar.add(UPLOAD_DIR, arcname="uploads")

    stat = (target_dir / "database.sql").stat()
    uploads_path = target_dir / "uploads.tar.gz"
    return BackupInfo(
        name=name,
        created_at=datetime.fromtimestamp(stat.st_mtime),
        database_size=stat.st_size,
        uploads_size=uploads_path.stat().st_size if uploads_path.exists() else None,
    )


def _validated_backup_dir(name: str) -> Path:
    if not _NAME_PATTERN.match(name):
        raise BackupError("Nombre de backup inválido")
    target_dir = BACKUP_DIR / name
    if not target_dir.is_dir():
        raise BackupError("Ese backup no existe")
    return target_dir


def backup_zip_bytes(name: str) -> bytes:
    """Empaqueta database.sql + uploads.tar.gz de un backup en un único .zip para descargar."""
    target_dir = _validated_backup_dir(name)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename in ("database.sql", "uploads.tar.gz"):
            path = target_dir / filename
            if path.exists():
                zf.write(path, arcname=filename)
    return buf.getvalue()


def save_uploaded_backup(zip_bytes: bytes) -> BackupInfo:
    """
    Guarda un backup subido desde afuera (por ejemplo bajado de otro
    servidor) como un backup más, listo para restaurar con
    restore_backup(). No lo restaura solo — eso es un paso aparte y
    explícito.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise BackupError("El archivo no es un .zip válido")

    names = set(zf.namelist())
    if "database.sql" not in names:
        raise BackupError("El .zip tiene que incluir 'database.sql' (generado por este mismo módulo)")

    name = datetime.utcnow().strftime("%Y%m%d_%H%M%S") + "_subido"
    target_dir = BACKUP_DIR / name
    target_dir.mkdir(parents=True, exist_ok=True)
    zf.extract("database.sql", target_dir)
    if "uploads.tar.gz" in names:
        zf.extract("uploads.tar.gz", target_dir)

    stat = (target_dir / "database.sql").stat()
    uploads_path = target_dir / "uploads.tar.gz"
    return BackupInfo(
        name=name,
        created_at=datetime.fromtimestamp(stat.st_mtime),
        database_size=stat.st_size,
        uploads_size=uploads_path.stat().st_size if uploads_path.exists() else None,
    )


async def restore_backup(name: str) -> None:
    """
    Restaura un backup ya guardado en el servidor (generado acá o subido
    con save_uploaded_backup). SOBREESCRIBE la base de datos actual y los
    archivos subidos — es destructivo a propósito, el llamador es
    responsable de haber confirmado con el usuario antes de invocarlo.
    """
    target_dir = _validated_backup_dir(name)
    conn = _db_connection_args()
    env = {"PGPASSWORD": conn["password"], "PATH": "/usr/bin:/usr/local/bin"}

    db_file = target_dir / "database.sql"
    if db_file.exists():
        # El propio backend mantiene un pool de conexiones abiertas contra
        # esta misma base — si alguna quedó con una transacción sin cerrar
        # (algo normal en un pool), su lock de sólo-lectura alcanza para
        # trabar el DROP TABLE del restore para siempre (nos pasó en la
        # prueba real: el restore quedó colgado indefinidamente). Cerramos
        # nuestro propio pool y matamos cualquier otra sesión contra esta
        # base antes de restaurar, así el restore no tiene con qué
        # trabarse. Las conexiones se recrean solas en el próximo request.
        # Solo aplica a Postgres real — en los tests (SQLite en memoria con
        # StaticPool) tirar el engine borraría directamente la base de la
        # suite, y ahí no existe este problema de locks entre procesos.
        if not settings.DATABASE_URL.startswith("sqlite"):
            from app.core.database import engine as _app_engine
            await _app_engine.dispose()
            try:
                await _run(
                    ["psql", "-h", conn["host"], "-p", conn["port"], "-U", conn["user"], "-d", conn["dbname"], "-c",
                     "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                     "WHERE datname = current_database() AND pid <> pg_backend_pid();"],
                    env=env,
                )
            except FileNotFoundError:
                pass  # si psql no está, el intento de restore de más abajo va a fallar con un mensaje claro

        try:
            await _run(
                [
                    "psql", "-h", conn["host"], "-p", conn["port"], "-U", conn["user"],
                    "-d", conn["dbname"], "-v", "ON_ERROR_STOP=1",
                    # Todo el restore en una sola transacción: si algo falla
                    # a mitad de camino, Postgres deshace los DROP que ya
                    # había hecho y la base queda como estaba antes de
                    # intentar restaurar, no a medio camino.
                    "--single-transaction",
                ],
                env=env,
                stdin_bytes=db_file.read_bytes(),
            )
        except FileNotFoundError:
            raise BackupError(
                "psql no está instalado en este servidor — hace falta el paquete 'postgresql-client'."
            )

    uploads_file = target_dir / "uploads.tar.gz"
    if uploads_file.exists():
        # Reemplaza el contenido actual de uploads/ por el del backup, en
        # vez de mezclarlo — un restore tiene que dejar todo como estaba
        # en el momento del backup, no arrastrar archivos que se hayan
        # subido después.
        if UPLOAD_DIR.exists():
            shutil.rmtree(UPLOAD_DIR)
        UPLOAD_DIR.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(uploads_file, "r:gz") as tar:
            # filter="data" (Python 3.12+) rechaza entradas con paths que se
            # escapen del directorio destino — importante acá porque el
            # .tar.gz puede venir de un backup SUBIDO desde afuera, no
            # necesariamente generado por este mismo servidor.
            tar.extractall(UPLOAD_DIR.parent, filter="data")
