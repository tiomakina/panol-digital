"""Schemas Pydantic v2 para herramientas."""
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict
from app.models.tool import DepreciationMethod, ToolStatus


class ToolBase(BaseModel):
    name: str
    brand: str | None = None
    model: str | None = None
    serial_number: str | None = None
    category: str | None = None
    location: str | None = None
    purchase_date: date | None = None
    purchase_cost: Decimal | None = None
    salvage_value: Decimal = Decimal("0")
    useful_life_years: int = 5
    depreciation_method: DepreciationMethod = DepreciationMethod.lineal
    description: str | None = None
    supplier: str | None = None


class ToolCreate(ToolBase):
    pass


class ToolUpdate(BaseModel):
    name: str | None = None
    brand: str | None = None
    model: str | None = None
    serial_number: str | None = None
    category: str | None = None
    location: str | None = None
    status: ToolStatus | None = None
    purchase_date: date | None = None
    purchase_cost: Decimal | None = None
    salvage_value: Decimal | None = None
    useful_life_years: int | None = None
    depreciation_method: DepreciationMethod | None = None
    description: str | None = None
    supplier: str | None = None


class DecommissionAuthorizedByOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str


class ToolOut(ToolBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: ToolStatus
    photo_url: str | None = None
    qr_code_url: str | None = None
    created_at: datetime
    updated_at: datetime
    current_value: Decimal | None = None
    decommission_reason: str | None = None
    decommission_date: date | None = None
    decommission_authorized_by: DecommissionAuthorizedByOut | None = None
