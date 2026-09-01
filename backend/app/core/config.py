"""Configuración central del sistema con pydantic-settings."""
import secrets
import sys
from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List

# Valores por defecto inseguros — solo se aceptan en modo DEBUG.
_INSECURE_SECRET_KEY = "CAMBIAR_EN_PRODUCCION_clave_muy_segura_2025"
_INSECURE_JWT_KEY    = "CAMBIAR_EN_PRODUCCION_jwt_secret_2025"


class Settings(BaseSettings):
    APP_NAME: str = "Pañol 360"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = _INSECURE_SECRET_KEY
    DATABASE_URL: str = "postgresql+asyncpg://panol:panol123@localhost:5432/panol_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET_KEY: str = _INSECURE_JWT_KEY
    JWT_ALGORITHM: str = "HS256"
    # 60 min de sesión activa; el refresh token (7 días) renueva sin re-login.
    # 480 min (8 h) era demasiado largo — una sesión robada quedaba válida
    # toda la jornada sin posibilidad de revocarla hasta que expirara.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    @field_validator("SECRET_KEY", mode="after")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        if v == _INSECURE_SECRET_KEY:
            debug = info.data.get("DEBUG", False)
            if not debug:
                print(
                    "\n[SEGURIDAD] SECRET_KEY tiene el valor por defecto inseguro. "
                    "Generando uno aleatorio para esta sesión.\n"
                    "  → Agrega SECRET_KEY=<valor> al archivo .env para hacerlo permanente.\n"
                    "  → Genera uno con: python -c \"import secrets; print(secrets.token_hex(32))\"\n",
                    file=sys.stderr,
                )
            return secrets.token_hex(32)
        return v

    @field_validator("JWT_SECRET_KEY", mode="after")
    @classmethod
    def validate_jwt_key(cls, v: str, info) -> str:
        if v == _INSECURE_JWT_KEY:
            debug = info.data.get("DEBUG", False)
            if not debug:
                print(
                    "\n[SEGURIDAD] JWT_SECRET_KEY tiene el valor por defecto inseguro. "
                    "Generando uno aleatorio para esta sesión.\n"
                    "  → Agrega JWT_SECRET_KEY=<valor> al archivo .env para hacerlo permanente.\n",
                    file=sys.stderr,
                )
            return secrets.token_hex(32)
        return v
    LOGIN_RATE_LIMIT_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300
    CORS_ORIGINS: List[str] = ["http://localhost:8080", "http://localhost:3000"]
    UPLOAD_DIR: str = "app/static/uploads"
    BACKUP_DIR: str = "backups"
    MAX_UPLOAD_SIZE_MB: int = 2
    ALLOWED_IMAGE_TYPES: List[str] = ["image/png", "image/jpeg", "image/svg+xml", "image/webp"]
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    WHATSAPP_API_TOKEN: str = ""
    WHATSAPP_PHONE_ID: str = ""
    COMPANY_NAME: str = "Mi Empresa"
    COMPANY_PRIMARY_COLOR: str = "#4f46e5"
    COMPANY_SECONDARY_COLOR: str = "#06b6d4"
    COMPANY_ACCENT_COLOR: str = "#f59e0b"

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
