"""
Modelo de Mantenimiento — seguimiento de una herramienta enviada a un
proveedor externo para reparación, con la foto del comprobante físico
(orden de trabajo, cotización o factura) y el resultado final.
"""
import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum as SQLEnum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

# Imports reales (no solo TYPE_CHECKING) — ver la explicación en
# models/loan.py: relationship() necesita que Tool/User ya estén
# registrados en el registro declarativo compartido.
from app.models.tool import Tool  # noqa: F401
from app.models.user import User  # noqa: F401


class MaintenanceStatus(str, enum.Enum):
    en_proceso = "en_proceso"
    resuelto = "resuelto"
    sin_solucion = "sin_solucion"


class MaintenanceRecord(Base):
    __tablename__ = "maintenance_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    tool_id: Mapped[int] = mapped_column(ForeignKey("tools.id"))
    provider: Mapped[str] = mapped_column(String(255), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[MaintenanceStatus] = mapped_column(SQLEnum(MaintenanceStatus), default=MaintenanceStatus.en_proceso)
    sent_date: Mapped[date] = mapped_column(Date, default=date.today)
    resolved_date: Mapped[date] = mapped_column(Date, nullable=True)
    resolution_notes: Mapped[str] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    tool: Mapped["Tool"] = relationship(lazy="joined")
    created_by: Mapped["User | None"] = relationship(lazy="joined")
    # Comprobantes del seguimiento: orden de trabajo, cotización, factura...
    # Puede haber varios (antes era un solo document_url que se pisaba con
    # cada subida nueva). No es la foto de la herramienta (esa es
    # Tool.photo_url).
    documents: Mapped[list["MaintenanceDocument"]] = relationship(
        back_populates="record", cascade="all, delete-orphan",
        order_by="MaintenanceDocument.uploaded_at", lazy="selectin",
    )


class MaintenanceDocument(Base):
    """Un comprobante subido para un registro de mantenimiento (imagen o PDF)."""
    __tablename__ = "maintenance_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    maintenance_record_id: Mapped[int] = mapped_column(ForeignKey("maintenance_records.id"))
    file_url: Mapped[str] = mapped_column(String(500))
    original_filename: Mapped[str] = mapped_column(String(255), nullable=True)
    # Título corto ("Cotización", "Factura N°123") y observación libre que
    # el que sube el archivo carga a mano — sin esto, la lista de
    # comprobantes de un mantenimiento con varios documentos es solo
    # nombres de archivo sueltos, difícil de distinguir a simple vista.
    title: Mapped[str] = mapped_column(String(255), nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    record: Mapped["MaintenanceRecord"] = relationship(back_populates="documents")
    uploaded_by: Mapped["User | None"] = relationship(lazy="joined")
