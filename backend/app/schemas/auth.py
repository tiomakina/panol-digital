"""Schemas Pydantic v2 para autenticación (tokens) y 2FA."""
from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TwoFactorRequired(BaseModel):
    """Respuesta de /auth/login cuando el usuario tiene 2FA activo: todavía no hay tokens."""
    requires_2fa: bool = True
    temp_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TwoFactorSetupOut(BaseModel):
    """Secreto + QR para escanear con Google Authenticator/Authy. 2FA aún no queda activo."""
    secret: str
    otpauth_uri: str
    qr_code_base64: str  # PNG en base64, listo para <img src="data:image/png;base64,...">


class TwoFactorEnableRequest(BaseModel):
    code: str


class TwoFactorDisableRequest(BaseModel):
    password: str


class TwoFactorVerifyRequest(BaseModel):
    temp_token: str
    code: str
