"""Schemas Pydantic v2 para las tablas maestras (marca, categoría, ubicación, proveedor)."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class LookupCreate(BaseModel):
    name: str


class LookupUpdate(BaseModel):
    name: str | None = None


class LookupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


class ProviderCreate(LookupCreate):
    contact_info: str | None = None


class ProviderUpdate(LookupUpdate):
    contact_info: str | None = None


class ProviderOut(LookupOut):
    contact_info: str | None = None
