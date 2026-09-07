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
import json
import os
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
                "WHERE status IN ('activo','pendiente') GROUP BY tenant_id"
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

    return {
        "id": user.id,
        "rut": user.rut,
        "email": user.email,
        "tenant_id": user.tenant_id,
        "role": user.role,
    }
