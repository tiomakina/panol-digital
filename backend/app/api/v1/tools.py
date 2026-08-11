"""
API de Herramientas — CRUD completo con fotos y generación/lectura de código QR.
Endpoint: /api/v1/tools/
"""
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.tool import Tool, ToolStatus
from app.models.user import User
from app.schemas.tool import ToolCreate, ToolOut, ToolUpdate
from app.services.brand_service import validate_image_magic_bytes
from app.services.depreciation import calculate_current_value
from app.services.qr_service import decode_qr_payload, generate_tool_qr

router = APIRouter(prefix="/tools", tags=["Herramientas"])

PHOTO_DIR = Path(settings.UPLOAD_DIR) / "tools"


def _to_out(tool: Tool) -> ToolOut:
    data = ToolOut.model_validate(tool)
    data.current_value = calculate_current_value(tool)
    return data


@router.get("", response_model=list[ToolOut])
async def list_tools(
    status_filter: ToolStatus | None = Query(None, alias="status"),
    category: str | None = None,
    search: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lista herramientas con filtros opcionales de estado, categoría y búsqueda libre."""
    stmt = select(Tool)
    if status_filter:
        stmt = stmt.where(Tool.status == status_filter)
    if category:
        stmt = stmt.where(Tool.category == category)
    if search:
        like = f"%{search}%"
        stmt = stmt.where((Tool.name.ilike(like)) | (Tool.serial_number.ilike(like)) | (Tool.brand.ilike(like)))
    stmt = stmt.order_by(Tool.name).offset(skip).limit(limit)

    result = await db.execute(stmt)
    tools = result.scalars().all()
    return [_to_out(t) for t in tools]


@router.get("/scan/{payload:path}", response_model=ToolOut)
async def scan_qr(payload: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Resuelve una herramienta a partir del contenido leído por el escáner QR de la cámara."""
    tool_id = decode_qr_payload(payload)
    if tool_id is None:
        raise HTTPException(status_code=400, detail="Código QR no reconocido")
    tool = await db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Herramienta no encontrada")
    return _to_out(tool)


@router.get("/{tool_id}", response_model=ToolOut)
async def get_tool(tool_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    tool = await db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Herramienta no encontrada")
    return _to_out(tool)


@router.post("", response_model=ToolOut, status_code=status.HTTP_201_CREATED)
async def create_tool(
    payload: ToolCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    """Crea una herramienta en el inventario y genera automáticamente su código QR."""
    if payload.serial_number:
        existing = await db.execute(select(Tool).where(Tool.serial_number == payload.serial_number))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Ya existe una herramienta con ese número de serie")

    tool = Tool(**payload.model_dump())
    db.add(tool)
    await db.flush()  # asigna tool.id sin cerrar la transacción

    base_url = str(request.base_url).rstrip("/")
    tool.qr_code_url = generate_tool_qr(tool.id, base_url)

    await db.commit()
    await db.refresh(tool)
    return _to_out(tool)


@router.put("/{tool_id}", response_model=ToolOut)
async def update_tool(
    tool_id: int,
    payload: ToolUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    tool = await db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Herramienta no encontrada")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(tool, field, value)

    await db.commit()
    await db.refresh(tool)
    return _to_out(tool)


@router.post("/{tool_id}/photo", response_model=ToolOut)
async def upload_tool_photo(
    tool_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    """Sube o reemplaza la foto de una herramienta, validando el tipo real del archivo (magic bytes)."""
    tool = await db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Herramienta no encontrada")

    file_bytes = await file.read()
    valid, mime_type = validate_image_magic_bytes(file_bytes)
    if not valid or mime_type == "image/svg+xml":
        raise HTTPException(status_code=400, detail="Archivo inválido (solo PNG, JPG o WebP)")
    if len(file_bytes) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"El archivo supera los {settings.MAX_UPLOAD_SIZE_MB}MB permitidos")

    ext = mime_type.split("/")[-1].replace("jpeg", "jpg")
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    photo_path = PHOTO_DIR / f"tool_{tool_id}.{ext}"
    with open(photo_path, "wb") as f:
        f.write(file_bytes)

    tool.photo_url = f"/static/uploads/tools/tool_{tool_id}.{ext}"
    await db.commit()
    await db.refresh(tool)
    return _to_out(tool)


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(
    tool_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("jefe")),
):
    """Elimina una herramienta del inventario (bloqueado si está actualmente prestada)."""
    tool = await db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Herramienta no encontrada")
    if tool.status == ToolStatus.prestado:
        raise HTTPException(status_code=400, detail="No se puede eliminar una herramienta actualmente prestada")

    await db.delete(tool)
    await db.commit()
