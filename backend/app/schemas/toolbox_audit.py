"""Schemas Pydantic v2 para auditoría/inventario de cajas de herramientas."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.toolbox_audit import AuditItemCondition, ToolboxAuditStatus
from app.schemas.tool import ToolOut


class ToolboxAuditCreate(BaseModel):
    toolbox_id: int
    notes: str | None = None


class ToolboxAuditItemUpdate(BaseModel):
    condition: AuditItemCondition
    observation: str | None = None


class AuditPerformedByOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str


class ToolboxAuditItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tool_id: int
    tool: ToolOut | None = None
    condition: AuditItemCondition | None = None
    observation: str | None = None
    sent_to_maintenance: bool
    reviewed_at: datetime | None = None


class ToolboxAuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    toolbox_id: int
    audit_date: date
    status: ToolboxAuditStatus
    notes: str | None = None
    performed_by: AuditPerformedByOut | None = None
    created_at: datetime
    completed_at: datetime | None = None
    items: list[ToolboxAuditItemOut] = []


class SendItemToMaintenanceInput(BaseModel):
    provider: str | None = None
    reason: str | None = None
