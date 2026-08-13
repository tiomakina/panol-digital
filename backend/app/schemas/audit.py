"""Schemas Pydantic v2 para el registro de auditoría."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class AuditLogUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    user: AuditLogUserOut | None = None
    action: str
    entity_type: str | None = None
    entity_id: int | None = None
    detail: str | None = None
    ip_address: str | None = None
    created_at: datetime
