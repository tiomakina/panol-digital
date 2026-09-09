"""
Endpoints de administración interna — Solo accesibles desde el admin-panel.

Autenticación: header X-Admin-Token (no JWT) que se compara contra la
variable de entorno ADMIN_API_SECRET. Jamás deben estar expuestos
a internet — el Nginx solo los pasa si el request viene de la red Docker
interna (admin-panel → backend:8000).

Rutas:
  GET  /admin/stats       → métricas globales + por tenant
  POST /admin/provision   → crea usuario admin en un tenant
"""
import asyncio
import json
import os
import re
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
