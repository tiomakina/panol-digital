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
    # Identificador único real: el email puede cambiar con el tiempo, el RUT
    # no. Es la credencial de login (reemplaza al email en /auth/login).
    # Formato canónico "NNNNNNNN-D" sin puntos (ver app/core/rut.py).
    rut: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), default=UserRole.mecanico)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_url: Mapped[str] = mapped_column(String(500), nullable=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # 2FA (TOTP, compatible con Google Authenticator/Authy) — recomendado
    # especialmente para el rol Jefe. totp_secret se guarda apenas se pide
    # /2fa/setup pero totp_enabled queda en False hasta confirmar un código
    # válido en /2fa/enable, para no bloquear al usuario con un secreto que
    # nunca llegó a escanear.
    totp_secret: Mapped[str] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Color identificador (pensado para Mecánico): así se marca físicamente
    # sus herramientas y su caja con pintura/spray de ese color, y la app
    # muestra el mismo color junto a su nombre para poder cotejarlo a
    # simple vista. identifying_color_photo_url guarda una foto de la
    # pintura real como referencia (ver POST /users/{id}/color-photo, que
    # extrae identifying_color automáticamente de esa foto como punto de
    # partida — un Jefe puede después ajustarlo a mano si la foto salió
    # con mala luz).
    identifying_color: Mapped[str] = mapped_column(String(7), nullable=True)
    identifying_color_photo_url: Mapped[str] = mapped_column(String(500), nullable=True)
