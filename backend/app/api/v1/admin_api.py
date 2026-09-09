"""
Endpoints de administración interna — Solo accesibles desde el admin-panel.

Autenticación: header X-Admin-Token (no JWT) que se compara contra la
variable de entorno ADMIN_API_SECRET. Jamás deben estar expuestos
a internet — el Nginx solo los pasa si el request viene de la red Docker
interna (admin-panel → backend:8000).

Rutas:
  GET    /admin/stats                    → métricas globales + por tenant
  POST   /admin/provision               → crea usuario admin en un tenant
  POST   /admin/delete-tenant/{id}      → respalda y elimina tenant
  GET    /admin/deleted-tenants          → lista tenants eliminados
  POST   /admin/restore-tenant/{id}     → restaura desde respaldo
  DELETE /admin/purge-tenant/{id}       → purga definitiva e irreversible
"""
import asyncio
import datetime as _dt
import decimal as _decimal
import json
import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_superuser_db

# ── Configuración ─────────────────────────────────────────────────────────────
ADMIN_API_SECRET = os.environ.get("ADMIN_API_SECRET", "")
TENANTS_FILE = Path(os.environ.get("TENANTS_FILE", "/app/app/tenants.json"))

# Directorio de respaldos de tenants (mapeado al host: ./backups/tenants/)
BACKUP_TENANTS_DIR = Path("/app/backups/tenants")
DELETED_TENANTS_FILE = Path("/app/backups/deleted_tenants.json")
PURGE_LOG_FILE = Path("/app/backups/purge_log.json")
ADMIN_NOTIFY_EMAIL = "hablemos@valentinmorales.cl"

# Tablas en orden de dependencia FK (para INSERT en restore y DELETE en purge)
_TENANT_TABLES = [
    "brands", "categories", "locations", "providers",
    "users", "brand_configs",
    "tools",
    "toolboxes", "toolbox_items",
    "loans", "loan_documents",
    "maintenance_records", "maintenance_documents",
    "toolbox_audits", "toolbox_audit_items",
    "notification_configs",
]

# Regex para detectar fechas/datetimes en JSON deserializado
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_DATETIME_RE = re.compile(r'^\d{4}-\d{2}-\d{2}T')

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Auth de API key ───────────────────────────────────────────────────────────

def require_admin_token(x_admin_token: Annotated[str, Header()] = "") -> None:
    """Dependencia que verifica el token de administración interno."""
    if not ADMIN_API_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_SECRET no configurado en el servidor.",
        )
    if x_admin_token != ADMIN_API_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de administración inválido.",
        )


AdminAuth = Annotated[None, Depends(require_admin_token)]


# ── Schemas ───────────────────────────────────────────────────────────────────

class ProvisionRequest(BaseModel):
    tenant_id: str
    rut: str
    email: str
    full_name: str
    password: str
    company_name: str | None = None  # Si se pasa, inicializa brand_config con ese nombre


class ChangePasswordRequest(BaseModel):
    tenant_id: str
    rut: str
    new_password: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_tenants() -> dict:
    """Lee tenants.json y retorna el dict."""
    if not TENANTS_FILE.exists():
        return {}
    try:
        return json.loads(TENANTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(
    _: AdminAuth,
    db: AsyncSession = Depends(get_superuser_db),
):
    """
    Retorna estadísticas globales y por-tenant:
    usuarios, herramientas y préstamos activos de cada tenant.
    """
    tenants = load_tenants()

    # Conteos por tenant (sin filtro de tenant — usamos get_superuser_db)
    user_counts: dict[str, int] = {}
    tool_counts: dict[str, int] = {}
    loan_counts: dict[str, int] = {}

    try:
        # Usuarios por tenant
        rows = await db.execute(
            text("SELECT tenant_id, COUNT(*) FROM users GROUP BY tenant_id")
        )
        for tenant_id, count in rows.fetchall():
            user_counts[tenant_id] = count

        # Herramientas por tenant
        rows = await db.execute(
            text("SELECT tenant_id, COUNT(*) FROM tools GROUP BY tenant_id")
        )
        for tenant_id, count in rows.fetchall():
            tool_counts[tenant_id] = count

        # Préstamos activos por tenant
        rows = await db.execute(
            text(
                "SELECT tenant_id, COUNT(*) FROM loans "
                "WHERE status IN ('activo','vencido') GROUP BY tenant_id"
            )
        )
        for tenant_id, count in rows.fetchall():
            loan_counts[tenant_id] = count

    except Exception as exc:
        # Si las tablas no existen aún (primera migración), devolver vacío
        return {
            "tenants": tenants,
            "stats": {},
            "error": str(exc),
        }

    stats: dict[str, dict] = {}
    for alias in tenants:
        stats[alias] = {
            "users": user_counts.get(alias, 0),
            "tools": tool_counts.get(alias, 0),
            "active_loans": loan_counts.get(alias, 0),
        }

    return {
        "tenants": tenants,
        "stats": stats,
    }


@router.get("/tenant-users/{tenant_id}")
async def list_tenant_users(
    tenant_id: str,
    _: AdminAuth,
    db: AsyncSession = Depends(get_superuser_db),
):
    """Lista todos los usuarios de un tenant con sus datos básicos."""
    from app.models.user import User

    result = await db.execute(
        select(User).where(User.tenant_id == tenant_id).order_by(User.full_name)
    )
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "rut": u.rut,
            "full_name": u.full_name,
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
        }
        for u in users
    ]


@router.post("/change-password", status_code=200)
async def change_user_password(
    body: ChangePasswordRequest,
    _: AdminAuth,
    db: AsyncSession = Depends(get_superuser_db),
):
    """Cambia la contraseña de un usuario en un tenant."""
    from app.core.security import hash_password
    from app.models.user import User

    result = await db.execute(
        select(User).where(
            User.rut == body.rut,
            User.tenant_id == body.tenant_id,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Usuario con RUT {body.rut} no encontrado en tenant {body.tenant_id}.",
        )

    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="La contraseña debe tener al menos 8 caracteres.",
        )

    user.hashed_password = hash_password(body.new_password)
    await db.flush()
    return {"ok": True, "rut": user.rut, "tenant_id": body.tenant_id}


@router.post("/provision", status_code=201)
async def provision_tenant_user(
    body: ProvisionRequest,
    _: AdminAuth,
    db: AsyncSession = Depends(get_superuser_db),
):
    """
    Crea un usuario administrador (rol jefe) en el tenant indicado.
    Si el RUT ya existe en ese tenant, retorna 409 Conflict.
    """
    from app.core.rut import format_rut
    from app.core.security import hash_password
    from app.models.user import User, UserRole

    # Normalizar RUT
    try:
        rut = format_rut(body.rut)
    except Exception:
        rut = body.rut.strip()

    # Verificar si ya existe
    result = await db.execute(
        select(User).where(
            User.rut == rut,
            User.tenant_id == body.tenant_id,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un usuario con RUT {rut} en el tenant {body.tenant_id}.",
        )

    user = User(
        email=body.email,
        rut=rut,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=UserRole.jefe,
        is_active=True,
        tenant_id=body.tenant_id,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    # Inicializar branding del tenant con el nombre de empresa si se proporcionó.
    # Esto evita que el nuevo cliente vea "Mi Empresa" (el default) en su panel.
    if body.company_name:
        from app.core.branding import init_brand_for_tenant
        try:
            init_brand_for_tenant(body.tenant_id, body.company_name)
        except Exception:
            # No fatal: el usuario podrá configurar el branding desde el panel
            pass

    return {
        "id": user.id,
        "rut": user.rut,
        "email": user.email,
        "tenant_id": user.tenant_id,
        "role": user.role,
    }


# ── Suite QA ──────────────────────────────────────────────────────────────────

QA_SCRIPT = Path("/app/scripts/qa_test.py")
_SAFE_ALIAS = re.compile(r"^[a-z0-9][a-z0-9-]{0,49}$")


@router.post("/run-qa")
async def run_qa(tenant_id: str, _: AdminAuth):
    """
    Ejecuta la suite de QA automatizada (scripts/qa_test.py) para el tenant
    indicado y retorna el informe JSON con los resultados.

    Solo accesible desde el admin-panel (requiere X-Admin-Token).
    Timeout: 90 s — la suite completa tarda ~10-15 s en condiciones normales.
    """
    if not _SAFE_ALIAS.match(tenant_id):
        raise HTTPException(status_code=400, detail="tenant_id inválido")

    if not QA_SCRIPT.exists():
        raise HTTPException(
            status_code=503,
            detail="Script de QA no encontrado en /app/scripts/qa_test.py. "
                   "Reconstruye la imagen del backend.",
        )

    output_file = f"/tmp/qa_{tenant_id}.json"

    # Determinar la contraseña de QA según el entorno del tenant.
    # Los tenants demo usan Demo1234! (seeded por seed_demo_tenant.py);
    # los tenants de producción usan Admin123! (seeded por seed.py).
    qa_password = "Admin123!"
    if TENANTS_FILE.exists():
        try:
            tenants_data = json.loads(TENANTS_FILE.read_text(encoding="utf-8"))
            tenant_env = tenants_data.get(tenant_id, {}).get("env", "prod")
            if tenant_env == "demo":
                qa_password = "Demo1234!"
        except Exception:
            pass

    env = dict(
        os.environ,
        PANOL_TENANT=tenant_id,
        PANOL_QA_OUTPUT=output_file,
        PANOL_QA_PASSWORD=qa_password,
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            "python3", str(QA_SCRIPT),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=90)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="La suite QA superó el tiempo límite (90 s)")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error al ejecutar la suite: {exc}")

    # Leer el JSON de resultados que el script escribió
    try:
        report = json.loads(Path(output_file).read_text(encoding="utf-8"))
    except Exception:
        # Si el script falló antes de escribir el JSON, devolver la salida en texto
        report = {
            "error": "El script no generó un archivo de resultados.",
            "stdout": stdout.decode(errors="replace")[-3000:],
            "stderr": stderr.decode(errors="replace")[-1000:],
            "returncode": proc.returncode,
        }

    return report


# ══════════════════════════════════════════════════════════════════════════════
# GESTIÓN DE CICLO DE VIDA DE TENANTS — Respaldo / Eliminación / Restauración
# ══════════════════════════════════════════════════════════════════════════════

class _BackupEncoder(json.JSONEncoder):
    """Serializa tipos Python que json.dumps no maneja: date, datetime, Decimal, bytes."""
    def default(self, obj):
        if isinstance(obj, _dt.datetime):
            return obj.isoformat()
        if isinstance(obj, _dt.date):
            return obj.isoformat()
        if isinstance(obj, _decimal.Decimal):
            return float(obj)
        if isinstance(obj, bytes):
            return obj.hex()
        return super().default(obj)


def _restore_value(v):
    """Convierte strings ISO date/datetime → objetos Python (para re-insertar en PostgreSQL)."""
    if not isinstance(v, str):
        return v
    if _DATETIME_RE.match(v):
        try:
            return _dt.datetime.fromisoformat(v)
        except Exception:
            return v
    if _DATE_RE.match(v):
        try:
            return _dt.date.fromisoformat(v)
        except Exception:
            return v
    return v


def _restore_row(row: dict) -> dict:
    return {k: _restore_value(v) for k, v in row.items()}


def _load_deleted_registry() -> dict:
    if not DELETED_TENANTS_FILE.exists():
        return {}
    try:
        return json.loads(DELETED_TENANTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_deleted_registry(data: dict) -> None:
    DELETED_TENANTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    DELETED_TENANTS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _send_admin_email(subject: str, body: str) -> bool:
    """Envía email de notificación a ADMIN_NOTIFY_EMAIL usando SMTP configurado en .env."""
    smtp_host = os.environ.get("SMTP_HOST", "")
    if not smtp_host:
        print(f"[ADMIN-EMAIL] SMTP no configurado — email omitido: {subject}")
        return False
    try:
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_password = os.environ.get("SMTP_PASSWORD", "")
        smtp_from = os.environ.get("SMTP_FROM", smtp_user) or "no-reply@panol360.app"

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = ADMIN_NOTIFY_EMAIL
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        print(f"[ADMIN-EMAIL] Enviado: {subject}")
        return True
    except Exception as exc:
        print(f"[ADMIN-EMAIL] Error: {exc}")
        return False


# ── Schemas ───────────────────────────────────────────────────────────────────

class DeleteTenantRequest(BaseModel):
    operator: str = "admin"
    tenant_name: str = ""
    original_config: dict = {}


class RestoreTenantRequest(BaseModel):
    backup_file: str
    operator: str = "admin"


class PurgeTenantRequest(BaseModel):
    backup_file: str = ""
    operator: str = "admin"
    tenant_name: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/delete-tenant/{tenant_id}", status_code=200)
async def delete_tenant_with_backup(
    tenant_id: str,
    body: DeleteTenantRequest,
    _: AdminAuth,
    db: AsyncSession = Depends(get_superuser_db),
):
    """
    Paso 1 de la eliminación de un tenant:
    1. Exporta TODOS los datos del tenant a un archivo JSON en /app/backups/tenants/.
    2. Registra el tenant en deleted_tenants.json (NO borra la BD todavía).
    3. Envía email de notificación a ADMIN_NOTIFY_EMAIL.

    El admin-panel es responsable de remover el tenant de tenants.json.
    Los datos quedan en la BD hasta que se ejecute purge-tenant.
    """
    if not _SAFE_ALIAS.match(tenant_id):
        raise HTTPException(400, "tenant_id inválido")

    BACKUP_TENANTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_TENANTS_DIR / f"{tenant_id}_{ts}.json"

    # Exportar cada tabla (ignora tablas que no existan)
    tables: dict[str, list] = {}
    stats: dict[str, int] = {}
    for table in _TENANT_TABLES:
        try:
            rows = await db.execute(
                text(f"SELECT * FROM {table} WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
            data = [dict(row._mapping) for row in rows.fetchall()]
            tables[table] = data
            stats[table] = len(data)
        except Exception:
            tables[table] = []
            stats[table] = 0

    tenant_name = body.tenant_name or tenant_id

    payload = {
        "version": "1.0",
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "backed_up_at": _dt.datetime.now().isoformat(),
        "deleted_by": body.operator,
        "original_config": body.original_config,
        "stats": stats,
        "tables": tables,
    }

    backup_file.write_text(
        json.dumps(payload, cls=_BackupEncoder, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Registrar en deleted_tenants.json
    registry = _load_deleted_registry()
    registry[tenant_id] = {
        "alias": tenant_id,
        "tenant_name": tenant_name,
        "deleted_at": _dt.datetime.now().isoformat(),
        "deleted_by": body.operator,
        "backup_file": str(backup_file),
        "original_config": body.original_config,
        "stats": stats,
    }
    _save_deleted_registry(registry)

    total_rows = sum(stats.values())
    non_empty = {t: n for t, n in stats.items() if n > 0}

    # Notificación por email (best-effort)
    _send_admin_email(
        subject=f"[Pañol 360] Tenant eliminado: {tenant_name} ({tenant_id})",
        body=(
            f"El tenant '{tenant_name}' (alias: {tenant_id}) ha sido ELIMINADO del sistema Pañol 360.\n\n"
            f"Fecha y hora : {_dt.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
            f"Operador     : {body.operator}\n\n"
            f"Respaldo creado:\n"
            f"  Archivo : {backup_file}\n"
            f"  Total   : {total_rows} registros respaldados\n\n"
            f"Detalle por tabla:\n"
            + "\n".join(f"  • {t}: {n}" for t, n in non_empty.items())
            + "\n\nLos datos se mantienen en la BD hasta que se ejecute una purga definitiva.\n"
            f"Para restaurar: Admin Panel → Tenants Eliminados → Restaurar."
        ),
    )

    return {
        "ok": True,
        "backup_file": str(backup_file),
        "backup_id": f"{tenant_id}_{ts}",
        "tenant_name": tenant_name,
        "stats": stats,
        "total_rows": total_rows,
    }


@router.get("/deleted-tenants", status_code=200)
async def list_deleted_tenants(_: AdminAuth):
    """Retorna la lista de tenants eliminados (pendientes de purga o restauración)."""
    registry = _load_deleted_registry()
    return list(registry.values())


@router.post("/restore-tenant/{tenant_id}", status_code=200)
async def restore_tenant_from_backup(
    tenant_id: str,
    body: RestoreTenantRequest,
    _: AdminAuth,
    db: AsyncSession = Depends(get_superuser_db),
):
    """
    Restaura un tenant eliminado desde su archivo de respaldo:
    1. Elimina cualquier dato residual del tenant en la BD.
    2. Re-inserta todos los datos en orden FK-seguro.
    3. Actualiza las sequences de PostgreSQL.
    4. Quita el tenant del registro de eliminados.
    5. Envía email de notificación.

    El admin-panel re-agrega el tenant a tenants.json con el original_config.
    """
    if not _SAFE_ALIAS.match(tenant_id):
        raise HTTPException(400, "tenant_id inválido")

    bkp_path = Path(body.backup_file)
    if not bkp_path.exists() or not str(bkp_path).startswith(str(BACKUP_TENANTS_DIR)):
        raise HTTPException(400, "Archivo de respaldo no encontrado o ruta inválida")

    payload = json.loads(bkp_path.read_text(encoding="utf-8"))
    tables = payload.get("tables", {})
    tenant_name = payload.get("tenant_name", tenant_id)
    original_config = payload.get("original_config", {})

    # Limpiar datos actuales (por si el tenant fue re-creado parcialmente)
    for table in reversed(_TENANT_TABLES):
        try:
            await db.execute(
                text(f"DELETE FROM {table} WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            )
        except Exception:
            pass

    # Re-insertar en orden FK
    errors: list[str] = []
    restored_counts: dict[str, int] = {}
    for table in _TENANT_TABLES:
        rows = tables.get(table, [])
        count = 0
        for row in rows:
            if not row:
                continue
            row = _restore_row(row)
            cols = list(row.keys())
            placeholders = ", ".join(f":{c}" for c in cols)
            try:
                await db.execute(
                    text(
                        f"INSERT INTO {table} ({', '.join(cols)}) "
                        f"VALUES ({placeholders}) ON CONFLICT (id) DO NOTHING"
                    ),
                    row,
                )
                count += 1
            except Exception as exc:
                errors.append(f"{table}: {exc}")
        restored_counts[table] = count

    # Actualizar sequences para que futuros INSERTs no colisionen con IDs restaurados
    for table in _TENANT_TABLES:
        try:
            await db.execute(
                text(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
                )
            )
        except Exception:
            pass

    await db.commit()

    # Quitar del registro de eliminados
    registry = _load_deleted_registry()
    registry.pop(tenant_id, None)
    _save_deleted_registry(registry)

    total_restored = sum(restored_counts.values())

    # Email
    _send_admin_email(
        subject=f"[Pañol 360] ✅ Tenant RESTAURADO: {tenant_name} ({tenant_id})",
        body=(
            f"El tenant '{tenant_name}' (alias: {tenant_id}) ha sido RESTAURADO en Pañol 360.\n\n"
            f"Fecha y hora  : {_dt.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
            f"Operador      : {body.operator}\n"
            f"Respaldo usado: {body.backup_file}\n"
            f"Registros re-insertados: {total_restored}\n\n"
            f"El tenant está activo y operativo nuevamente."
            + (f"\n\nAdvertencias ({len(errors)}):\n" + "\n".join(f"  • {e}" for e in errors[:5]) if errors else "")
        ),
    )

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "original_config": original_config,
        "total_restored": total_restored,
        "errors": errors[:10],
    }


@router.delete("/purge-tenant/{tenant_id}", status_code=200)
async def purge_tenant_permanently(
    tenant_id: str,
    body: PurgeTenantRequest,
    _: AdminAuth,
    db: AsyncSession = Depends(get_superuser_db),
):
    """
    Purga DEFINITIVA e IRREVERSIBLE de un tenant:
    1. Elimina TODOS los registros de la BD para este tenant_id.
    2. Elimina el archivo de respaldo.
    3. Registra en purge_log.json (auditoría permanente que nunca se borra).
    4. Envía email de notificación a ADMIN_NOTIFY_EMAIL.

    Esta operación NO puede deshacerse.
    """
    if not _SAFE_ALIAS.match(tenant_id):
        raise HTTPException(400, "tenant_id inválido")

    registry = _load_deleted_registry()
    entry = registry.get(tenant_id, {})
    tenant_name = body.tenant_name or entry.get("tenant_name", tenant_id)
    backup_file_path = body.backup_file or entry.get("backup_file", "")

    # Eliminar datos de BD en orden FK inverso
    deleted_counts: dict[str, int] = {}
    for table in reversed(_TENANT_TABLES):
        try:
            result = await db.execute(
                text(f"DELETE FROM {table} WHERE tenant_id = :tid RETURNING id"),
                {"tid": tenant_id},
            )
            deleted_counts[table] = len(result.fetchall())
        except Exception:
            deleted_counts[table] = 0

    await db.commit()

    # Eliminar archivo de respaldo
    backup_removed = False
    if backup_file_path:
        bkp = Path(backup_file_path)
        if bkp.exists() and str(bkp).startswith(str(BACKUP_TENANTS_DIR)):
            try:
                bkp.unlink()
                backup_removed = True
            except Exception:
                pass

    # Quitar del registro de eliminados
    registry.pop(tenant_id, None)
    _save_deleted_registry(registry)

    # Registro permanente de auditoría (nunca se borra)
    purge_log: list = []
    if PURGE_LOG_FILE.exists():
        try:
            purge_log = json.loads(PURGE_LOG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    purge_log.append({
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "purged_at": _dt.datetime.now().isoformat(),
        "purged_by": body.operator,
        "backup_removed": backup_removed,
        "deleted_counts": deleted_counts,
        "total_deleted": sum(deleted_counts.values()),
    })
    PURGE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    PURGE_LOG_FILE.write_text(json.dumps(purge_log, ensure_ascii=False, indent=2), encoding="utf-8")

    total_deleted = sum(deleted_counts.values())
    non_empty = {t: n for t, n in deleted_counts.items() if n > 0}

    # Email de auditoría (crítico — siempre intentar)
    _send_admin_email(
        subject=f"[Pañol 360] ⚠️ PURGA DEFINITIVA: {tenant_name} ({tenant_id})",
        body=(
            f"ATENCIÓN — ACCIÓN IRREVERSIBLE EJECUTADA\n"
            f"{'='*55}\n\n"
            f"El tenant '{tenant_name}' (alias: {tenant_id}) ha sido\n"
            f"ELIMINADO DEFINITIVAMENTE del sistema Pañol 360.\n\n"
            f"Fecha y hora      : {_dt.datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
            f"Operador          : {body.operator}\n"
            f"Registros borrados: {total_deleted}\n"
            f"Respaldo eliminado: {'Sí' if backup_removed else 'No (no encontrado)'}\n\n"
            f"Detalle por tabla:\n"
            + "\n".join(f"  • {t}: {n}" for t, n in non_empty.items())
            + "\n\nEste evento ha sido registrado en purge_log.json en el servidor.\n"
            f"La información de este tenant NO puede recuperarse."
        ),
    )

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "total_deleted": total_deleted,
        "backup_removed": backup_removed,
    }
