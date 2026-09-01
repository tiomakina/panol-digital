"""
API de tablas maestras — Marca, Categoría, Ubicación, Proveedor.
Endpoint: /api/v1/lookups/{brands,categories,locations,providers}

Estas tablas solo alimentan los desplegables del formulario de herramientas
(Tool.brand/category/location/supplier siguen siendo texto libre — ver el
docstring de app/models/lookup.py). Por eso el CRUD es deliberadamente
simple: no hay relación FK que proteger al borrar un registro.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.lookup import Brand, Category, Location, Provider
from app.models.user import User
from app.schemas.lookup import (
    LookupCreate,
    LookupOut,
    LookupUpdate,
    ProviderCreate,
    ProviderOut,
    ProviderUpdate,
)

router = APIRouter(prefix="/lookups", tags=["Tablas maestras"])


def _register_lookup_routes(path: str, model, tag_name: str) -> None:
    """
    Registra el CRUD estándar (list/create/update/delete) de una tabla
    maestra simple (solo id + name). Provider se registra aparte porque
    tiene un campo extra (contact_info).
    """

    @router.get(f"/{path}", response_model=list[LookupOut], name=f"list_{path}")
    async def list_items(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
        result = await db.execute(select(model).order_by(model.name))
        return result.scalars().all()

    @router.post(f"/{path}", response_model=LookupOut, status_code=status.HTTP_201_CREATED, name=f"create_{path}")
    async def create_item(
        payload: LookupCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_role("encargado"))
    ):
        item = model(name=payload.name.strip())
        db.add(item)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=400, detail=f"'{payload.name}' ya existe en {tag_name}")
        await db.refresh(item)
        return item

    @router.put(f"/{path}/{{item_id}}", response_model=LookupOut, name=f"update_{path}")
    async def update_item(
        item_id: int,
        payload: LookupUpdate,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_role("encargado")),
    ):
        item = await db.get(model, item_id)
        if not item:
            raise HTTPException(status_code=404, detail=f"No encontrado en {tag_name}")
        if payload.name is not None:
            item.name = payload.name.strip()
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status_code=400, detail=f"'{payload.name}' ya existe en {tag_name}")
        await db.refresh(item)
        return item

    @router.delete(f"/{path}/{{item_id}}", status_code=status.HTTP_204_NO_CONTENT, name=f"delete_{path}")
    async def delete_item(
        item_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_role("encargado"))
    ):
        item = await db.get(model, item_id)
        if not item:
            raise HTTPException(status_code=404, detail=f"No encontrado en {tag_name}")
        await db.delete(item)
        await db.commit()


_register_lookup_routes("brands", Brand, "Marcas")
_register_lookup_routes("categories", Category, "Categorías")
_register_lookup_routes("locations", Location, "Ubicaciones")


# Proveedores tiene un campo extra (contact_info), así que va aparte en vez
# de forzarlo dentro del factory genérico de arriba.
@router.get("/providers", response_model=list[ProviderOut])
async def list_providers(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Provider).order_by(Provider.name))
    return result.scalars().all()


@router.post("/providers", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
async def create_provider(
    payload: ProviderCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_role("encargado"))
):
    provider = Provider(
        name=payload.name.strip(), rut=payload.rut, contact_name=payload.contact_name,
        phone=payload.phone, email=payload.email, address=payload.address,
    )
    db.add(provider)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"'{payload.name}' ya existe en Proveedores")
    await db.refresh(provider)
    return provider


@router.put("/providers/{item_id}", response_model=ProviderOut)
async def update_provider(
    item_id: int,
    payload: ProviderUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    provider = await db.get(Provider, item_id)
    if not provider:
        raise HTTPException(status_code=404, detail="No encontrado en Proveedores")
    if payload.name is not None:
        provider.name = payload.name.strip()
    if payload.rut is not None:
        provider.rut = payload.rut
    if payload.contact_name is not None:
        provider.contact_name = payload.contact_name
    if payload.phone is not None:
        provider.phone = payload.phone
    if payload.email is not None:
        provider.email = payload.email
    if payload.address is not None:
        provider.address = payload.address
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"'{payload.name}' ya existe en Proveedores")
    await db.refresh(provider)
    return provider


@router.delete("/providers/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    item_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_role("encargado"))
):
    provider = await db.get(Provider, item_id)
    if not provider:
        raise HTTPException(status_code=404, detail="No encontrado en Proveedores")
    await db.delete(provider)
    await db.commit()
