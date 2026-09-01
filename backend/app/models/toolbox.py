"""Modelo de Caja de Herramientas (Toolbox) — agrupa herramientas para préstamos conjuntos."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# Import real (no solo TYPE_CHECKING) — ver la explicación en models/loan.py:
# relationship() necesita que Tool ya esté registrado en el registro
# declarativo compartido, sin depender de que otro módulo lo importe antes.
from app.models.tool import Tool  # noqa: F401
from app.models.user import User  # noqa: F401


class Toolbox(Base):
    __tablename__ = "toolboxes"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    location: Mapped[str] = mapped_column(String(255), nullable=True)
    qr_code_url: Mapped[str] = mapped_column(String(500), nullable=True)
    # Mecánico responsable de la caja — quien la tiene a cargo y responde por
    # su contenido en el inventario/auditoría. Nullable: una caja puede crearse
    # sin asignar todavía.
    responsible_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    items: Mapped[list["ToolboxItem"]] = relationship(
        back_populates="toolbox", cascade="all, delete-orphan", lazy="selectin"
    )
    responsible: Mapped["User | None"] = relationship(lazy="joined")


class ToolboxItem(Base):
    """Relación entre una caja y las herramientas que contiene."""
    __tablename__ = "toolbox_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    toolbox_id: Mapped[int] = mapped_column(ForeignKey("toolboxes.id"))
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id"), unique=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    toolbox: Mapped["Toolbox"] = relationship(back_populates="items")
    tool: Mapped["Tool"] = relationship(lazy="joined")
