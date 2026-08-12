"""Schemas Pydantic v2 para cajas de herramientas."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict

from app.schemas.tool import ToolOut


class ToolboxBase(BaseModel):
    name: str
    description: str | None = None
    location: str | None = None
    responsible_user_id: int | None = None


class ToolboxCreate(ToolboxBase):
    pass


class ToolboxUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    location: str | None = None
    responsible_user_id: int | None = None


class ToolboxResponsibleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str


class ToolboxItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tool_id: int
    added_at: datetime
    tool: ToolOut | None = None


class ToolboxOut(ToolboxBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    qr_code_url: str | None = None
    created_at: datetime
    updated_at: datetime
    items: list[ToolboxItemOut] = []
    responsible: ToolboxResponsibleOut | None = None
