"""
Modelo de Auditoría/Inventario de Caja de Herramientas — registra, en una
fecha dada, el estado real de cada herramienta que debería estar en la
caja: si está en buen estado, dañada, o directamente no aparece (con la
observación del mecánico justificando qué pasó).
"""
import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum as SQLEnum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# Imports reales (no solo TYPE_CHECKING) — ver la explicación en
# models/loan.py: relationship() necesita que Toolbox/Tool/User ya estén
# registrados en el registro declarativo compartido.
from app.models.tool import Tool  # noqa: F401
from app.models.toolbox import Toolbox  # noqa: F401
from app.models.user import User  # noqa: F401


class ToolboxAuditStatus(str, enum.Enum):
    en_progreso = "en_progreso"
    completado = "completado"


class AuditItemCondition(str, enum.Enum):
    bueno = "bueno"
    dañado = "dañado"
    faltante = "faltante"


class ToolboxAudit(Base):
    __tablename__ = "toolbox_audits"

    id: Mapped[int] = mapped_column(primary_key=True)
    toolbox_id: Mapped[int] = mapped_column(ForeignKey("toolboxes.id"))
    audit_date: Mapped[date] = mapped_column(Date, default=date.today)
    performed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[ToolboxAuditStatus] = mapped_column(SQLEnum(ToolboxAuditStatus), default=ToolboxAuditStatus.en_progreso)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    toolbox: Mapped["Toolbox"] = relationship(lazy="joined")
    performed_by: Mapped["User | None"] = relationship(lazy="joined")
    items: Mapped[list["ToolboxAuditItem"]] = relationship(
        back_populates="audit", cascade="all, delete-orphan", lazy="selectin"
    )


class ToolboxAuditItem(Base):
    """
    Una línea del checklist: una herramienta que estaba en la caja al
    momento de arrancar la auditoría. condition/observation quedan en
    null hasta que el mecánico la revisa.
    """
    __tablename__ = "toolbox_audit_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("toolbox_audits.id"))
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id"))
    condition: Mapped[AuditItemCondition | None] = mapped_column(SQLEnum(AuditItemCondition), nullable=True)
    # Obligatoria cuando condition != "bueno" (se valida en la API) — es la
    # justificación del mecánico de qué pasó con la herramienta.
    observation: Mapped[str] = mapped_column(Text, nullable=True)
    sent_to_maintenance: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    audit: Mapped["ToolboxAudit"] = relationship(back_populates="items")
    tool: Mapped["Tool"] = relationship(lazy="joined")
