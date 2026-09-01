"""Modelo de Auditoría — registro forense de acciones sensibles del sistema."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.user import User  # noqa: F401 — ver models/loan.py


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)  # ej: "tool.delete", "user.role_change"
    entity_type: Mapped[str] = mapped_column(String(50), nullable=True)  # ej: "tool", "loan", "user"
    entity_id: Mapped[int] = mapped_column(Integer, nullable=True)
    detail: Mapped[str] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    user: Mapped["User"] = relationship(lazy="joined")
