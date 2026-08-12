"""
API de Cajas de Herramientas — agrupa herramientas para prestarlas/gestionarlas en conjunto.
Endpoint: /api/v1/toolboxes/
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.tool import Tool
from app.models.toolbox import Toolbox, ToolboxItem
from app.models.user import User
from app.schemas.toolbox import ToolboxCreate, ToolboxOut, ToolboxUpdate
from app.services.qr_service import generate_toolbox_qr

router = APIRouter(prefix="/toolboxes", tags=["Cajas de Herramientas"])


async def _get_toolbox_or_404(db: AsyncSession, toolbox_id: int) -> Toolbox:
    toolbox = await db.get(Toolbox, toolbox_id)
    if not toolbox:
        raise HTTPException(status_code=404, detail="Caja de herramientas no encontrada")
    return toolbox


@router.get("", response_model=list[ToolboxOut])
async def list_toolboxes(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Toolbox).order_by(Toolbox.name))
    return result.scalars().all()


@router.get("/{toolbox_id}", response_model=ToolboxOut)
async def get_toolbox(
    toolbox_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    return await _get_toolbox_or_404(db, toolbox_id)


@router.post("", response_model=ToolboxOut, status_code=status.HTTP_201_CREATED)
async def create_toolbox(
    payload: ToolboxCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    """Crea una caja de herramientas vacía y genera su código QR."""
    toolbox = Toolbox(**payload.model_dump())
    db.add(toolbox)
    await db.flush()

    base_url = str(request.base_url).rstrip("/")
    toolbox.qr_code_url = generate_toolbox_qr(toolbox.id, base_url)

    await db.commit()
    await db.refresh(toolbox)
    return toolbox


@router.put("/{toolbox_id}", response_model=ToolboxOut)
async def update_toolbox(
    toolbox_id: int,
    payload: ToolboxUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    toolbox = await _get_toolbox_or_404(db, toolbox_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(toolbox, field, value)

    await db.commit()
    await db.refresh(toolbox)
    return toolbox


@router.delete("/{toolbox_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_toolbox(
    toolbox_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(require_role("jefe"))
):
    """Elimina la caja (las herramientas que contenía quedan sueltas, no se borran)."""
    toolbox = await _get_toolbox_or_404(db, toolbox_id)
    await db.delete(toolbox)
    await db.commit()


@router.post("/{toolbox_id}/tools", response_model=ToolboxOut, status_code=status.HTTP_201_CREATED)
async def add_tool_to_toolbox(
    toolbox_id: int,
    tool_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    """Agrega una herramienta a la caja. Una herramienta solo puede estar en una caja a la vez."""
    toolbox = await _get_toolbox_or_404(db, toolbox_id)

    tool = await db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Herramienta no encontrada")

    existing = await db.execute(select(ToolboxItem).where(ToolboxItem.tool_id == tool_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Esa herramienta ya está en otra caja")

    db.add(ToolboxItem(toolbox_id=toolbox.id, tool_id=tool_id))
    await db.commit()
    await db.refresh(toolbox)
    return toolbox


@router.delete("/{toolbox_id}/tools/{tool_id}", response_model=ToolboxOut)
async def remove_tool_from_toolbox(
    toolbox_id: int,
    tool_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    toolbox = await _get_toolbox_or_404(db, toolbox_id)

    result = await db.execute(
        select(ToolboxItem).where(ToolboxItem.toolbox_id == toolbox_id, ToolboxItem.tool_id == tool_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Esa herramienta no está en esta caja")

    await db.delete(item)
    await db.commit()
    await db.refresh(toolbox)
    return toolbox
