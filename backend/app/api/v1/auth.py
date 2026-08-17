"""
API de Autenticación — login, refresh token, logout, perfil y 2FA (TOTP).
Endpoint: /api/v1/auth/
"""
import base64
import io
from datetime import datetime

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import rate_limiter
from app.core.rut import format_rut
from app.core.security import (
    create_2fa_pending_token,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    is_token_revoked,
    oauth2_scheme,
    revoke_token,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    RefreshRequest,
    Token,
    TwoFactorDisableRequest,
    TwoFactorEnableRequest,
    TwoFactorRequired,
    TwoFactorSetupOut,
    TwoFactorVerifyRequest,
)
from app.schemas.user import UserOut
from app.services.audit_service import log_action

router = APIRouter(prefix="/auth", tags=["Autenticación"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/login", response_model=Token | TwoFactorRequired)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
    _rate_limit=Depends(
        rate_limiter(
            "login",
            max_attempts=settings.LOGIN_RATE_LIMIT_ATTEMPTS,
            window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        )
    ),
):
    """
    Autentica con RUT + contraseña (campo `username` del form OAuth2 — el
    RUT es el identificador único del usuario, no el email, que puede
    cambiar con el tiempo). Acepta el RUT con o sin puntos/guión.
    Si el usuario tiene 2FA activo, todavía no emite tokens: devuelve
    requires_2fa + un temp_token de 5 minutos para completar en /2fa/verify.
    """
    try:
        rut = format_rut(form_data.username)
    except IndexError:
        rut = form_data.username  # RUT vacío o mal formado: no matchea nada, cae al 401 de abajo

    result = await db.execute(select(User).where(User.rut == rut))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        await log_action(
            db,
            user_id=user.id if user else None,
            action="auth.login_failed",
            entity_type="user",
            detail=f"Intento fallido para {form_data.username}",
            ip_address=_client_ip(request),
        )
        await db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="RUT o contraseña incorrectos")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario inactivo, contacte al administrador")

    if user.totp_enabled:
        await log_action(
            db, user_id=user.id, action="auth.login_password_ok_2fa_pending",
            entity_type="user", entity_id=user.id, ip_address=_client_ip(request),
        )
        await db.commit()
        return TwoFactorRequired(temp_token=create_2fa_pending_token(user.id))

    user.last_login = datetime.utcnow()
    await log_action(
        db, user_id=user.id, action="auth.login", entity_type="user", entity_id=user.id, ip_address=_client_ip(request)
    )
    await db.commit()

    access_token = create_access_token(user.id, user.role.value)
    refresh_token = create_refresh_token(user.id)
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/2fa/verify", response_model=Token)
async def verify_2fa(
    payload: TwoFactorVerifyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _rate_limit=Depends(rate_limiter("2fa_verify", max_attempts=10, window_seconds=300)),
):
    """Segundo paso del login cuando el usuario tiene 2FA activo: código TOTP + temp_token → tokens reales."""
    token_payload = decode_token(payload.temp_token, expected_type="2fa_pending")
    if await is_token_revoked(token_payload):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="El código de verificación expiró, iniciá sesión de nuevo")

    user = await db.get(User, int(token_payload["sub"]))
    if not user or not user.is_active or not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No se pudo verificar el código")

    if not pyotp.TOTP(user.totp_secret).verify(payload.code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Código de verificación incorrecto")

    await revoke_token(token_payload)  # de un solo uso
    user.last_login = datetime.utcnow()
    await log_action(
        db, user_id=user.id, action="auth.login", entity_type="user", entity_id=user.id,
        detail="con 2FA", ip_address=_client_ip(request),
    )
    await db.commit()

    access_token = create_access_token(user.id, user.role.value)
    refresh_token = create_refresh_token(user.id)
    return Token(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=Token)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """Rota el refresh token vigente y emite un nuevo par de tokens."""
    token_payload = decode_token(payload.refresh_token, expected_type="refresh")
    if await is_token_revoked(token_payload):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token revocado")

    user = await db.get(User, int(token_payload["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no válido")

    await revoke_token(token_payload)  # rotación: el refresh token usado deja de ser válido
    new_access_token = create_access_token(user.id, user.role.value)
    new_refresh_token = create_refresh_token(user.id)
    return Token(access_token=new_access_token, refresh_token=new_refresh_token)


@router.post("/logout")
async def logout(payload: RefreshRequest, token: str = Depends(oauth2_scheme)):
    """Revoca el access token de la sesión actual y su refresh token asociado."""
    access_payload = decode_token(token, expected_type="access")
    refresh_payload = decode_token(payload.refresh_token, expected_type="refresh")
    await revoke_token(access_payload)
    await revoke_token(refresh_payload)
    return {"success": True, "message": "Sesión cerrada correctamente"}


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    """Devuelve el perfil del usuario autenticado."""
    return current_user


@router.post("/2fa/setup", response_model=TwoFactorSetupOut)
async def setup_2fa(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Genera un nuevo secreto TOTP y el QR para escanear con Google
    Authenticator/Authy. El 2FA todavía NO queda activo — hay que confirmar
    con un código válido en /2fa/enable (si no, un secreto nunca escaneado
    dejaría al usuario sin poder volver a iniciar sesión).
    """
    secret = pyotp.random_base32()
    current_user.totp_secret = secret
    await db.commit()

    otpauth_uri = pyotp.TOTP(secret).provisioning_uri(name=current_user.email, issuer_name=settings.APP_NAME)

    qr_img = qrcode.make(otpauth_uri)
    buffer = io.BytesIO()
    qr_img.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    return TwoFactorSetupOut(secret=secret, otpauth_uri=otpauth_uri, qr_code_base64=qr_base64)


@router.post("/2fa/enable")
async def enable_2fa(
    payload: TwoFactorEnableRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Confirma el 2FA con un código generado por la app autenticadora y lo activa."""
    if not current_user.totp_secret:
        raise HTTPException(status_code=400, detail="Primero pedí un código QR en /2fa/setup")
    if not pyotp.TOTP(current_user.totp_secret).verify(payload.code, valid_window=1):
        raise HTTPException(status_code=400, detail="Código incorrecto — probá de nuevo")

    current_user.totp_enabled = True
    await log_action(
        db, user_id=current_user.id, action="user.2fa_enabled", entity_type="user",
        entity_id=current_user.id, ip_address=_client_ip(request),
    )
    await db.commit()
    return {"success": True, "message": "Verificación en dos pasos activada"}


@router.post("/2fa/disable")
async def disable_2fa(
    payload: TwoFactorDisableRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Desactiva el 2FA de la cuenta propia. Requiere reingresar la contraseña."""
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="La contraseña es incorrecta")

    current_user.totp_enabled = False
    current_user.totp_secret = None
    await log_action(
        db, user_id=current_user.id, action="user.2fa_disabled", entity_type="user",
        entity_id=current_user.id, ip_address=_client_ip(request),
    )
    await db.commit()
    return {"success": True, "message": "Verificación en dos pasos desactivada"}
