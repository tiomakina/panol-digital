"""
API de Autenticación — login, refresh token, logout y perfil del usuario.
Endpoint: /api/v1/auth/
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import rate_limiter
from app.core.security import (
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
from app.schemas.auth import RefreshRequest, Token
from app.schemas.user import UserOut
from app.services.audit_service import log_action

router = APIRouter(prefix="/auth", tags=["Autenticación"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/login", response_model=Token)
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
    """Autentica con email + contraseña (campo `username` del form OAuth2) y emite tokens."""
    result = await db.execute(select(User).where(User.email == form_data.username))
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email o contraseña incorrectos")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario inactivo, contacte al administrador")

    user.last_login = datetime.utcnow()
    await log_action(
        db, user_id=user.id, action="auth.login", entity_type="user", entity_id=user.id, ip_address=_client_ip(request)
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
