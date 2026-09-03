"""Modelo de Préstamo con vales PDF y firma digital."""
from datetime import datetime, date
from sqlalchemy import String, DateTime, Date, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

# Import real (no solo TYPE_CHECKING): relationship() resuelve "Tool"/"User"
# contra el registro declarativo compartido, y ese registro solo los conoce
# si sus módulos fueron importados. Dejarlo librado a que algún otro código
# (p. ej. los routers de FastAPI) los importe primero es frágil — se rompe
# en cualquier contexto que solo toque Loan, como las tareas de Celery.
from app.models.tool import Tool  # noqa: F401
from app.models.user import User  # noqa: F401
import enum

class LoanStatus(str, enum.Enum):
    activo = "activo"
    devuelto = "devuelto"
    vencido = "vencido"
    extraviado = "extraviado"

class ReturnCondition(str, enum.Enum):
    bueno = "bueno"
    dañado = "dañado"
    reparacion = "reparacion"
    perdido = "perdido"

class Loan(Base):
    __tablename__ = "loans"
    id: Mapped[int] = mapped_column(primary_key=True)
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id"))
    borrower_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    issued_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    loan_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    due_date: Mapped[date] = mapped_column(Date)
    return_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    status: Mapped[LoanStatus] = mapped_column(SQLEnum(LoanStatus), default=LoanStatus.activo)
    return_condition: Mapped[ReturnCondition] = mapped_column(SQLEnum(ReturnCondition), nullable=True)
    purpose: Mapped[str] = mapped_column(String(500), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    signature_data: Mapped[str] = mapped_column(Text, nullable=True)  # base64 firma digital
    voucher_pdf_url: Mapped[str] = mapped_column(String(500), nullable=True)
    alert_sent: Mapped[bool] = mapped_column(default=False)
    reminder_sent: Mapped[bool] = mapped_column(default=False)  # aviso 1 día antes de vencer

    # Relaciones con carga "joined" (eager) para evitar lazy-load fuera del contexto async
    tool: Mapped["Tool"] = relationship(foreign_keys=[tool_id], lazy="joined")
    borrower: Mapped["User"] = relationship(foreign_keys=[borrower_id], lazy="joined")
    issued_by: Mapped["User"] = relationship(foreign_keys=[issued_by_id], lazy="joined")
