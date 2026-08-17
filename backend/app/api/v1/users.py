"""
API de Usuarios — alta, edición de perfil/roles y cambio de contraseña.
Endpoint: /api/v1/users/
"""
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user, hash_password, require_role, verify_password
from app.models.user import User
from app.schemas.user import PasswordChange, UserCreate, UserOut, UserUpdate
from app.services.audit_service import log_action
from app.services.brand_service import extract_dominant_colors, validate_image_magic_bytes

router = APIRouter(prefix="/users", tags=["Usuarios"])

AVATAR_DIR = Path(settings.UPLOAD_DIR) / "avatars"
COLOR_PHOTO_DIR = Path(settings.UPLOAD_DIR) / "color_photos"


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("", response_model=list[UserOut])
async def list_users(
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    """Lista los usuarios del sistema, con búsqueda opcional por nombre, email o RUT."""
    stmt = select(User)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            (User.full_name.ilike(like)) | (User.email.ilike(like)) | (User.rut.ilike(like))
        )
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

    existing_rut = await db.execute(select(User).where(User.rut == payload.rut))
    if existing_rut.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Ya existe un usuario con ese RUT")

    new_user = User(
        email=payload.email,
        rut=payload.rut,
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
    Actualiza un usuario. Solo un Jefe puede editar datos de usuarios —
    Encargado y Mecánico pueden VER (el Encargado ve el listado completo,
    el Mecánico solo su propio perfil vía /auth/me) pero no modificar
    nada, ni siquiera su propio nombre/teléfono: tienen que pedírselo a
    un Jefe. Esto es a propósito más estricto que "cualquiera edita lo
    suyo": la administración de la ficha de cada usuario (incluida su
    propia) queda centralizada en un solo rol.
    """
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    is_jefe = current_user.role.value == "jefe"
    if not is_jefe:
        raise HTTPException(
            status_code=403, detail="Solo un Jefe puede editar usuarios — Encargado y Mecánico solo pueden verlos"
        )

    updates = payload.model_dump(exclude_unset=True)

    if "email" in updates and updates["email"] != target.email:
        dup = await db.execute(select(User).where(User.email == updates["email"], User.id != target.id))
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Ya existe un usuario con ese email")

    if "rut" in updates and updates["rut"] != target.rut:
        dup = await db.execute(select(User).where(User.rut == updates["rut"], User.id != target.id))
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Ya existe un usuario con ese RUT")

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


@router.post("/{user_id}/photo", response_model=UserOut)
async def upload_user_photo(
    user_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sube o reemplaza la foto de perfil de un usuario — solo un Jefe, para cualquiera (ver update_user)."""
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if current_user.role.value != "jefe":
        raise HTTPException(
            status_code=403, detail="Solo un Jefe puede editar usuarios — Encargado y Mecánico solo pueden verlos"
        )

    file_bytes = await file.read()
    valid, mime_type = validate_image_magic_bytes(file_bytes)
    if not valid or mime_type == "image/svg+xml":
        raise HTTPException(status_code=400, detail="Archivo inválido (solo PNG, JPG o WebP)")
    if len(file_bytes) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"El archivo supera los {settings.MAX_UPLOAD_SIZE_MB}MB permitidos")

    ext = mime_type.split("/")[-1].replace("jpeg", "jpg")
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    photo_path = AVATAR_DIR / f"user_{user_id}.{ext}"
    with open(photo_path, "wb") as f:
        f.write(file_bytes)

    target.avatar_url = f"/static/uploads/avatars/user_{user_id}.{ext}"
    await log_action(
        db,
        user_id=current_user.id,
        action="user.photo_update",
        entity_type="user",
        entity_id=target.id,
        ip_address=_client_ip(request),
    )
    await db.commit()
    await db.refresh(target)
    return target


@router.post("/{user_id}/color-photo", response_model=UserOut)
async def upload_color_photo(
    user_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Sube una foto de la pintura/spray con la que se marcan físicamente las
    herramientas y la caja de un Mecánico, y extrae de ahí un color
    identificador automáticamente (mismo motor que usa el logo de la
    empresa para armar la paleta de branding — ver
    brand_service.extract_dominant_colors). El color queda precargado
    en identifying_color; si la foto salió con mala luz y el color no
    quedó bien, se puede ajustar a mano después con PUT /users/{id}
    (campo identifying_color). Solo un Jefe puede hacer esto, para
    cualquier usuario — mismo permiso que la foto de perfil.
    """
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if current_user.role.value != "jefe":
        raise HTTPException(
            status_code=403, detail="Solo un Jefe puede editar usuarios — Encargado y Mecánico solo pueden verlos"
        )

    file_bytes = await file.read()
    valid, mime_type = validate_image_magic_bytes(file_bytes)
    if not valid or mime_type == "image/svg+xml":
        raise HTTPException(status_code=400, detail="Archivo inválido (solo PNG, JPG o WebP)")
    if len(file_bytes) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"El archivo supera los {settings.MAX_UPLOAD_SIZE_MB}MB permitidos")

    dominant = extract_dominant_colors(file_bytes)
    if not dominant:
        raise HTTPException(
            status_code=400,
            detail="No se pudo detectar un color en esa foto — probá con más luz y encuadrando bien la pintura",
        )

    ext = mime_type.split("/")[-1].replace("jpeg", "jpg")
    COLOR_PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    photo_path = COLOR_PHOTO_DIR / f"user_{user_id}.{ext}"
    with open(photo_path, "wb") as f:
        f.write(file_bytes)

    target.identifying_color_photo_url = f"/static/uploads/color_photos/user_{user_id}.{ext}"
    target.identifying_color = dominant[0]
    await log_action(
        db,
        user_id=current_user.id,
        action="user.color_photo_update",
        entity_type="user",
        entity_id=target.id,
        detail=f"Color extraído: {dominant[0]}",
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
