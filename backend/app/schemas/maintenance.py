"""Schemas Pydantic v2 para el módulo de mantenimiento."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.maintenance import MaintenanceStatus
from app.schemas.tool import ToolOut


class MaintenanceCreate(BaseModel):
    tool_id: int
    provider: str | None = None
    reason: str


class MaintenanceResolve(BaseModel):
    status: Literal[MaintenanceStatus.resuelto, MaintenanceStatus.sin_solucion]
    resolution_notes: str | None = None


class MaintenanceCreatedByOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str


class MaintenanceDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_url: str
    original_filename: str | None = None
    mime_type: str
    uploaded_at: datetime
    uploaded_by: MaintenanceCreatedByOut | None = None


class MaintenanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tool_id: int
    tool: ToolOut | None = None
    provider: str | None = None
    reason: str
    status: MaintenanceStatus
    sent_date: date
    resolved_date: date | None = None
    documents: list[MaintenanceDocumentOut] = []
    resolution_notes: str | None = None
    created_by: MaintenanceCreatedByOut | None = None
    created_at: datetime


class DecommissionInput(BaseModel):
    reason: str
    authorized_by_id: int
