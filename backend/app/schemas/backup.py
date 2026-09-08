"""Schemas Pydantic v2 para el módulo de respaldo integral."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class BackupOut(BaseModel):
    name: str
    created_at: datetime
    database_size: Optional[int] = None
    uploads_size: Optional[int] = None
    # Resultado de la verificación automática de integridad
    verified: Optional[bool] = None           # None = no verificado aún
    table_count: Optional[int] = None         # CREATE TABLE encontrados en el SQL
    upload_file_count: Optional[int] = None   # Archivos en el tar.gz
    includes_tenants: bool = False            # Si incluye tenants.json
    verification_errors: list[str] = []


class RestoreInput(BaseModel):
    """Confirmación liviana antes de un restore — es destructivo, así que
    pedimos la contraseña actual además del rol Jefe, mismo criterio que
    desactivar el 2FA."""
    current_password: str
