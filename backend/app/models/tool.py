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
    # Un Mecánico pidió mantención desde su caja asignada, pero todavía no
    # la confirmó un Encargado/Jefe (eso recién crea el MaintenanceRecord y
    # pasa a "mantenimiento" — ver send_tool_to_maintenance). Es un estado
    # intermedio, no un mantenimiento en curso todavía.
    mantenimiento_solicitada = "mantenimiento_solicitada"
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
    # Código de producto — identifica el MODELO/producto (no la unidad
    # física). A propósito no es único: varias unidades del mismo producto
    # comparten el mismo product_code pero cada una tiene su propio
    # serial_number (ver "Duplicar herramienta" en la API de herramientas).
    product_code: Mapped[str] = mapped_column(String(100), nullable=True, index=True)
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
    # Folio del documento de compra (boleta/factura) + el comprobante
    # escaneado (imagen o PDF) — igual que MaintenanceDocument, pero acá
    # es uno solo por herramienta, no una lista.
    purchase_document_folio: Mapped[str] = mapped_column(String(100), nullable=True)
    purchase_document_url: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Baja definitiva — motivo y quién la autorizó, para que quede en la
    # auditoría (ver app/api/v1/tools.py::decommission_tool). Separado de
    # MaintenanceRecord porque una herramienta puede darse de baja sin haber
    # pasado por mantenimiento (ej. pérdida total constatada directamente).
    decommission_reason: Mapped[str] = mapped_column(Text, nullable=True)
    decommission_authorized_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decommission_date: Mapped[date] = mapped_column(Date, nullable=True)

    # Solicitud de mantención hecha por un Mecánico desde su caja asignada
    # (status pasa a mantenimiento_solicitada) — quién y cuándo, para que
    # el popup en Cajas/Herramientas lo pueda mostrar. Se limpia cuando un
    # Encargado/Jefe la confirma (pasa a MaintenanceRecord real) o la
    # descarta.
    maintenance_requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    maintenance_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    maintenance_requested_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    decommission_authorized_by: Mapped["User | None"] = relationship(
        lazy="joined", foreign_keys=[decommission_authorized_by_id]
    )
    maintenance_requested_by: Mapped["User | None"] = relationship(
        lazy="joined", foreign_keys=[maintenance_requested_by_id]
    )
