"""Seguridad: JWT (access + refresh), bcrypt, OAuth2, RBAC por roles."""
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.redis_client import redis_client

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

ROLES = {"jefe": 3, "encargado": 2, "mecanico": 1}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: int, role: str, expires_delta: Optional[timedelta] = None) -> str:
    """Genera un access token de corta duración con el rol embebido para autorización rápida."""
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {"sub": str(user_id), "role": role, "type": "access", "jti": str(uuid4()), "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: int, expires_delta: Optional[timedelta] = None) -> str:
    """Genera un refresh token de larga duración, sin rol (se revalida contra la BD al usarlo)."""
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))
    payload = {"sub": str(user_id), "type": "refresh", "jti": str(uuid4()), "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str, expected_type: Optional[str] = None) -> dict:
    """Decodifica y valida la firma/expiración de un token. Opcionalmente exige un tipo (access/refresh)."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido o expirado")

    if expected_type and payload.get("type") != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tipo de token incorrecto")
    return payload


async def revoke_token(payload: dict) -> None:
    """Agrega el jti del token a la lista negra en Redis hasta que expire por sí mismo."""
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti or not exp:
        return
    ttl = int(exp - datetime.now(timezone.utc).timestamp())
    if ttl > 0:
        await redis_client.set(f"revoked:{jti}", "1", ex=ttl)


async def is_token_revoked(payload: dict) -> bool:
    jti = payload.get("jti")
    if not jti:
        return False
    return await redis_client.exists(f"revoked:{jti}") == 1


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """Dependencia base: resuelve el usuario autenticado a partir del access token."""
    from app.models.user import User  # import diferido para evitar ciclos con database/models

    payload = decode_token(token, expected_type="access")
    if await is_token_revoked(payload):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesión cerrada, inicie sesión nuevamente")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    user = await db.get(User, int(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no válido o inactivo")
    return user


def require_role(min_role: str):
    """Dependencia que exige un rol mínimo (jefe > encargado > mecanico)."""
    async def role_checker(current_user=Depends(get_current_user)):
        if ROLES.get(current_user.role.value, 0) < ROLES.get(min_role, 0):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sin permisos suficientes")
        return current_user
    return role_checker
