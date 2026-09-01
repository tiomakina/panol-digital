"""
API de Herramientas — CRUD completo con fotos y generación/lectura de código QR.
Endpoint: /api/v1/tools/
"""
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.tool import Tool, ToolStatus
from app.models.user import User
from app.schemas.maintenance import DecommissionInput
from app.schemas.tool import ToolCreate, ToolOut, ToolUpdate
from app.services.audit_service import log_action
from app.services.brand_service import validate_document_magic_bytes, validate_image_magic_bytes
from app.services.csv_service import example_csv_bytes, parse_and_import_tools_csv, tools_to_csv
from app.services.depreciation import calculate_current_value
from app.services.qr_service import decode_qr_payload, generate_tool_qr

router = APIRouter(prefix="/tools", tags=["Herramientas"])

PHOTO_DIR = Path(settings.UPLOAD_DIR) / "tools"
PURCHASE_DOC_DIR = Path(settings.UPLOAD_DIR) / "purchase_docs"


def _to_out(tool: Tool, viewer: User) -> ToolOut:
    """
    viewer determina si se muestran los valores económicos (costo de
    compra, valor de rescate, valor actual/depreciado) — solo el Jefe los
    ve. No alcanza con ocultarlos en el frontend: si el dato sigue viniendo
    en el JSON, cualquiera puede leerlo abriendo el panel de red del
    navegador, así que se los saca acá antes de responder.
    """
    data = ToolOut.model_validate(tool)
    data.current_value = calculate_current_value(tool)
    if viewer.role.value != "jefe":
        data.purchase_cost = None
        data.salvage_value = None
        data.current_value = None
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
    return [_to_out(t, user) for t in tools]


@router.get("/scan/{payload:path}", response_model=ToolOut)
async def scan_qr(payload: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """Resuelve una herramienta a partir del contenido leído por el escáner QR de la cámara."""
    tool_id = decode_qr_payload(payload)
    if tool_id is None:
        raise HTTPException(status_code=400, detail="Código QR no reconocido")
    tool = await db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Herramienta no encontrada")
    return _to_out(tool, user)


@router.get("/export")
async def export_tools(db: AsyncSession = Depends(get_db), user: User = Depends(require_role("encargado"))):
    """
    Descarga el inventario completo como CSV (compatible con Excel). Un
    Mecánico no puede exportar (ni la opción se muestra en la UI). Para
    quien sí puede pero no es Jefe (Encargado), el CSV enmascara costo de
    compra y valor de rescate — igual que la API JSON (_to_out) — porque
    si no, exportar era una forma de esquivar esa restricción y ver los
    valores económicos igual.
    """
    result = await db.execute(select(Tool).order_by(Tool.name))
    csv_bytes = tools_to_csv(result.scalars().all(), mask_costs=user.role.value != "jefe")
    filename = f"herramientas_{date.today().isoformat()}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/import/example")
async def download_example_csv(user: User = Depends(get_current_user)):
    """Plantilla CSV descargable con las columnas esperadas y un par de filas de ejemplo."""
    return Response(
        content=example_csv_bytes(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="herramientas_ejemplo.csv"'},
    )


@router.post("/import")
async def import_tools(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    """
    Importa herramientas desde un CSV (mismas columnas que exporta /export).
    Matchea por número de serie: si ya existe, actualiza; si no, crea una
    nueva. No aborta ante una fila inválida — la salta y la reporta.
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="El archivo tiene que ser un .csv")

    file_bytes = await file.read()
    if len(file_bytes) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"El archivo supera los {settings.MAX_UPLOAD_SIZE_MB}MB permitidos")

    result = await parse_and_import_tools_csv(db, file_bytes)

    await log_action(
        db,
        user_id=user.id,
        action="tool.bulk_import",
        entity_type="tool",
        entity_id=None,
        detail=(
            f"Importación masiva de herramientas: {result.created} creadas, {result.updated} actualizadas, "
            f"{len(result.errors)} con error."
        ),
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    return {
        "created": result.created,
        "updated": result.updated,
        "errors": [{"row": e.row, "detail": e.detail} for e in result.errors],
    }


@router.get("/{tool_id}", response_model=ToolOut)
async def get_tool(tool_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    tool = await db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Herramienta no encontrada")
    return _to_out(tool, user)


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
    return _to_out(tool, user)


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
    return _to_out(tool, user)


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
    return _to_out(tool, user)


@router.post("/{tool_id}/purchase-document", response_model=ToolOut)
async def upload_purchase_document(
    tool_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    """Sube o reemplaza el comprobante de compra (boleta/factura) — imagen o PDF."""
    tool = await db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Herramienta no encontrada")

    file_bytes = await file.read()
    valid, mime_type = validate_document_magic_bytes(file_bytes)
    if not valid or mime_type == "image/svg+xml":
        raise HTTPException(status_code=400, detail="Archivo inválido (solo PNG, JPG, WebP o PDF)")
    if len(file_bytes) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"El archivo supera los {settings.MAX_UPLOAD_SIZE_MB}MB permitidos")

    ext = mime_type.split("/")[-1].replace("jpeg", "jpg")
    PURCHASE_DOC_DIR.mkdir(parents=True, exist_ok=True)
    doc_path = PURCHASE_DOC_DIR / f"tool_{tool_id}.{ext}"
    with open(doc_path, "wb") as f:
        f.write(file_bytes)

    tool.purchase_document_url = f"/static/uploads/purchase_docs/tool_{tool_id}.{ext}"
    await db.commit()
    await db.refresh(tool)
    return _to_out(tool, user)


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(
    tool_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("jefe")),
):
    """Elimina una herramienta del inventario (bloqueado si está actualmente prestada)."""
    tool = await db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Herramienta no encontrada")
    if tool.status == ToolStatus.prestado:
        raise HTTPException(status_code=400, detail="No se puede eliminar una herramienta actualmente prestada")

    await log_action(
        db,
        user_id=user.id,
        action="tool.delete",
        entity_type="tool",
        entity_id=tool.id,
        detail=f"Herramienta eliminada: {tool.name}",
        ip_address=request.client.host if request.client else None,
    )
    await db.delete(tool)
    await db.commit()


@router.post("/{tool_id}/decommission", response_model=ToolOut)
async def decommission_tool(
    tool_id: int,
    payload: DecommissionInput,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("jefe")),
):
    """
    Da de baja definitivamente una herramienta (no confundir con eliminarla
    del sistema: la baja deja el registro, solo cambia su estado). Requiere
    un motivo y quién autoriza — ambos quedan en la auditoría.
    """
    tool = await db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Herramienta no encontrada")
    if tool.status == ToolStatus.prestado:
        raise HTTPException(status_code=400, detail="No se puede dar de baja una herramienta actualmente prestada")

    authorizer = await db.get(User, payload.authorized_by_id)
    if not authorizer or not authorizer.is_active:
        raise HTTPException(status_code=404, detail="Quien autoriza no existe o está inactivo")

    tool.status = ToolStatus.baja
    tool.decommission_reason = payload.reason
    tool.decommission_authorized_by_id = payload.authorized_by_id
    tool.decommission_date = date.today()

    await log_action(
        db,
        user_id=user.id,
        action="tool.decommission",
        entity_type="tool",
        entity_id=tool.id,
        detail=f"Baja de '{tool.name}'. Motivo: {payload.reason}. Autorizó: {authorizer.full_name}.",
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(tool)
    return _to_out(tool, user)
