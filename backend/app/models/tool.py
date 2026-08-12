"""Modelo de Herramienta con depreciación automática."""
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, Numeric, Date, DateTime, Enum as SQLEnum, Text, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base
import enum

# Import real (no solo TYPE_CHECKING) — ver la explicación en models/loan.py:
# relationship() necesita que User ya esté registrado en el registro
# declarativo compartido, sin depender de que otro módulo lo importe antes.
from app.models.user import User  # noqa: F401,E402

class ToolStatus(str, enum.Enum):
    disponible = "disponible"
    prestado = "prestado"
    mantenimiento = "mantenimiento"
    baja = "baja"
    en_caja = "en_caja"  # dentro de una caja de herramientas (toolbox)

class DepreciationMethod(str, enum.Enum):
    lineal = "lineal"
    uop = "uop"                    # Unidades de producción
    doble_saldo = "doble_saldo"    # Doble saldo decreciente

class Tool(Base):
    __tablename__ = "tools"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    brand: Mapped[str] = mapped_column(String(100), nullable=True)
    model: Mapped[str] = mapped_column(String(100), nullable=True)
    serial_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    location: Mapped[str] = mapped_column(String(255), nullable=True)
    status: Mapped[ToolStatus] = mapped_column(SQLEnum(ToolStatus), default=ToolStatus.disponible)
    purchase_date: Mapped[date] = mapped_column(Date, nullable=True)
    purchase_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=True)
    salvage_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    useful_life_years: Mapped[int] = mapped_column(Integer, default=5)
    depreciation_method: Mapped[DepreciationMethod] = mapped_column(SQLEnum(DepreciationMethod), default=DepreciationMethod.lineal)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str] = mapped_column(String(500), nullable=True)
    qr_code_url: Mapped[str] = mapped_column(String(500), nullable=True)
    supplier: Mapped[str] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Baja definitiva — motivo y quién la autorizó, para que quede en la
    # auditoría (ver app/api/v1/tools.py::decommission_tool). Separado de
    # MaintenanceRecord porque una herramienta puede darse de baja sin haber
    # pasado por mantenimiento (ej. pérdida total constatada directamente).
    decommission_reason: Mapped[str] = mapped_column(Text, nullable=True)
    decommission_authorized_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decommission_date: Mapped[date] = mapped_column(Date, nullable=True)

    decommission_authorized_by: Mapped["User | None"] = relationship(lazy="joined")
