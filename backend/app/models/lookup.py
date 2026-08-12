"""
Tablas maestras ("maestro de tablas") — Marca, Categoría, Ubicación, Proveedor.

Son catálogos simples de texto que alimentan los desplegables del formulario
de herramientas. A propósito NO son claves foráneas de Tool: Tool.brand,
Tool.category, Tool.location y Tool.supplier siguen siendo texto libre
(como ya estaban desde el modelo inicial), y estas tablas solo controlan qué
valores aparecen en el desplegable al cargar/editar una herramienta. Esto
evita una migración invasiva sobre datos ya cargados — el pedido original es
"que se puedan seleccionar de una lista", no una normalización estricta.
"""
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Brand(Base):
    __tablename__ = "brands"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Location(Base):
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Provider(Base):
    __tablename__ = "providers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    contact_info: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
