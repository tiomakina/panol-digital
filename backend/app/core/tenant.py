"""
Contexto de tenant multi-empresa — Pañol 360.

El alias del cliente activo (ej: 'vms-ingenieria') se lee de la cookie
panol_tenant y se almacena en una ContextVar de asyncio para que cada
petición HTTP tenga su propio valor sin interferir con otras peticiones
concurrentes.

El middleware TenantMiddleware (ver main.py) escribe el contexto al inicio
de cada petición; get_db() lo lee para configurar el filtro automático de
la sesión de base de datos.
"""
from contextvars import ContextVar
from typing import Optional

# Variable de contexto por petición (hilo / tarea asyncio).
# default=None → sin tenant activo (peticiones públicas: portal, terminos, etc.)
_current_tenant: ContextVar[Optional[str]] = ContextVar("current_tenant", default=None)

# Alias del tenant "sistema" para operaciones que deben omitir el filtro:
# seeds, migraciones, admin-panel. Se usa como option en el execute:
#   session.execute(stmt, execution_options={"skip_tenant_filter": True})
SKIP_TENANT_FILTER_KEY = "skip_tenant_filter"


def get_current_tenant() -> Optional[str]:
    """
    Devuelve el alias del tenant activo para la petición en curso,
    o None si es una petición pública (portal, legales, etc.).
    """
    return _current_tenant.get()


def set_current_tenant(tenant_id: str) -> None:
    """
    Registra el tenant activo para la petición en curso.
    Llamado por TenantMiddleware en main.py.
    """
    _current_tenant.set(tenant_id)


def clear_tenant() -> None:
    """Limpia el contexto de tenant. Útil en tests."""
    _current_tenant.set(None)
