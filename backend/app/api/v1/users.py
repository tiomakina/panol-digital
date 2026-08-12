"""
API de Usuarios — alta, edición de perfil/roles y cambio de contraseña.
Endpoint: /api/v1/users/
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, hash_password, require_role, verify_password
from app.models.user import User
from app.schemas.user import PasswordChange, UserCreate, UserOut, UserUpdate
from app.services.audit_service import log_action

router = APIRouter(prefix="/users", tags=["Usuarios"])


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("", response_model=list[UserOut])
async def list_users(
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    """Lista los usuarios del sistema, con búsqueda opcional por nombre o email."""
    stmt = select(User)
    if search:
        like = f"%{search}%"
        stmt = stmt.where((User.full_name.ilike(like)) | (User.email.ilike(like)))
    stmt = stmt.order_by(User.full_name)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_role("encargado"))
):
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return target


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("jefe")),
):
    """Crea un nuevo usuario. Solo el Jefe puede dar de alta cuentas."""
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Ya existe un usuario con ese email")

    new_user = User(
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role,
        phone=payload.phone,
        hashed_password=hash_password(payload.password),
    )
    db.add(new_user)
    await db.flush()

    await log_action(
        db,
        user_id=current_user.id,
        action="user.create",
        entity_type="user",
        entity_id=new_user.id,
        detail=f"Usuario creado: {new_user.email} (rol {new_user.role.value})",
        ip_address=_client_ip(request),
    )

    await db.commit()
    await db.refresh(new_user)
    return new_user


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Actualiza un usuario. Cualquier usuario puede editar sus propios datos de
    contacto; cambiar rol o estado activo/inactivo requiere ser Jefe (incluso
    para el propio perfil, así nadie se auto-asciende).
    """
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    is_self = current_user.id == target.id
    is_jefe = current_user.role.value == "jefe"

    if not is_self and not is_jefe:
        raise HTTPException(status_code=403, detail="Sin permisos suficientes")

    updates = payload.model_dump(exclude_unset=True)
    if ("role" in updates or "is_active" in updates) and not is_jefe:
        raise HTTPException(status_code=403, detail="Solo un Jefe puede cambiar rol o estado de la cuenta")

    changed_fields = list(updates.keys())
    for field, value in updates.items():
        setattr(target, field, value)

    if changed_fields:
        await log_action(
            db,
            user_id=current_user.id,
            action="user.update",
            entity_type="user",
            entity_id=target.id,
            detail=f"Campos modificados: {', '.join(changed_fields)}",
            ip_address=_client_ip(request),
        )

    await db.commit()
    await db.refresh(target)
    return target


@router.post("/{user_id}/deactivate", response_model=UserOut)
async def deactivate_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("jefe")),
):
    """Desactiva una cuenta (no puede volver a iniciar sesión) sin borrar su historial."""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="No podés desactivar tu propia cuenta")

    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    target.is_active = False
    await log_action(
        db,
        user_id=current_user.id,
        action="user.deactivate",
        entity_type="user",
        entity_id=target.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(target)
    return target


@router.post("/{user_id}/reactivate", response_model=UserOut)
async def reactivate_user(
    user_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("jefe")),
):
    """Reactiva una cuenta previamente desactivada."""
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    target.is_active = True
    await log_action(
        db,
        user_id=current_user.id,
        action="user.reactivate",
        entity_type="user",
        entity_id=target.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(target)
    return target


@router.put("/me/password")
async def change_own_password(
    payload: PasswordChange,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cambia la contraseña del usuario autenticado, verificando la actual."""
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta")

    current_user.hashed_password = hash_password(payload.new_password)
    await log_action(
        db,
        user_id=current_user.id,
        action="user.password_change",
        entity_type="user",
        entity_id=current_user.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    return {"success": True, "message": "Contraseña actualizada correctamente"}
