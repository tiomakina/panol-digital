"""Schemas Pydantic v2 para usuarios."""
import re
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from app.core.rut import format_rut, is_valid_rut
from app.models.user import UserRole

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _validar_color_hex(v: str | None) -> str | None:
    if v is None:
        return v
    if not HEX_COLOR_RE.fullmatch(v):
        raise ValueError("El color debe ser un hex de 6 dígitos, ej. #3B82F6")
    return v.upper()


class UserBase(BaseModel):
    email: EmailStr
    rut: str
    full_name: str
    role: UserRole = UserRole.mecanico
    phone: str | None = None

    @field_validator("rut")
    @classmethod
    def rut_valido(cls, v: str) -> str:
        if not is_valid_rut(v):
            raise ValueError("RUT inválido — verificá el número y el dígito verificador")
        return format_rut(v)


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
    totp_enabled: bool = False
    identifying_color: str | None = None
    identifying_color_photo_url: str | None = None


class UserUpdate(BaseModel):
    """Campos editables de un usuario. role/is_active solo los puede tocar un jefe (ver users.py)."""
    email: EmailStr | None = None
    rut: str | None = None
    full_name: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    identifying_color: str | None = None

    @field_validator("rut")
    @classmethod
    def rut_valido(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not is_valid_rut(v):
            raise ValueError("RUT inválido — verificá el número y el dígito verificador")
        return format_rut(v)

    @field_validator("identifying_color")
    @classmethod
    def color_valido(cls, v: str | None) -> str | None:
        return _validar_color_hex(v)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        return v
