"""Schemas Pydantic v2 para usuarios."""
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from app.models.user import UserRole


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: UserRole = UserRole.mecanico
    phone: str | None = None


class UserCreate(UserBase):
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        return v


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    avatar_url: str | None = None
    created_at: datetime
    last_login: datetime | None = None
