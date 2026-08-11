"""Modelo de Usuario con roles RBAC."""
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
import enum

class UserRole(str, enum.Enum):
    jefe = "jefe"
    encargado = "encargado"
    mecanico = "mecanico"

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), default=UserRole.mecanico)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_url: Mapped[str] = mapped_column(String(500), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[datetime] = mapped_column(DateTime, nullable=True)
