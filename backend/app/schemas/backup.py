"""Schemas Pydantic v2 para el módulo de respaldo integral."""
from datetime import datetime

from pydantic import BaseModel


class BackupOut(BaseModel):
    name: str
    created_at: datetime
    database_size: int | None = None
    uploads_size: int | None = None


class RestoreInput(BaseModel):
    """Confirmación liviana antes de un restore — es destructivo, así que
    pedimos la contraseña actual además del rol Jefe, mismo criterio que
    desactivar el 2FA."""
    current_password: str
