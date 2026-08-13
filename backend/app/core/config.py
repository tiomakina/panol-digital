"""Configuración central del sistema con pydantic-settings."""
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    APP_NAME: str = "Pañol 360"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    SECRET_KEY: str = "CAMBIAR_EN_PRODUCCION_clave_muy_segura_2025"
    DATABASE_URL: str = "postgresql+asyncpg://panol:panol123@localhost:5432/panol_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET_KEY: str = "CAMBIAR_EN_PRODUCCION_jwt_secret_2025"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
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
