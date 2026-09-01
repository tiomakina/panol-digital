"""Modelo de configuración de branding empresarial."""
from datetime import datetime
from sqlalchemy import String, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

class BrandConfig(Base):
    __tablename__ = "brand_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), default="Mi Empresa")
    primary_color: Mapped[str] = mapped_column(String(7), default="#4f46e5")
    secondary_color: Mapped[str] = mapped_column(String(7), default="#06b6d4")
    accent_color: Mapped[str] = mapped_column(String(7), default="#f59e0b")
    dark_color: Mapped[str] = mapped_column(String(7), default="#1e1b4b")
    light_color: Mapped[str] = mapped_column(String(7), default="#ede9fe")
    sidebar_bg: Mapped[str] = mapped_column(String(7), default="#0f172a")
    sidebar_text: Mapped[str] = mapped_column(String(7), default="#e2e8f0")
    text_on_primary: Mapped[str] = mapped_column(String(7), default="#ffffff")
    logo_url: Mapped[str] = mapped_column(String(500), nullable=True)
    font_heading: Mapped[str] = mapped_column(String(100), default="Inter")
    font_body: Mapped[str] = mapped_column(String(100), default="Inter")
    border_radius: Mapped[str] = mapped_column(String(10), default="8px")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=True)
