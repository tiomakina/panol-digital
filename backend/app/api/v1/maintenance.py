"""
API de Mantenimiento — enviar una herramienta a un proveedor externo,
hacerle seguimiento con la foto del comprobante físico, y resolverlo.
Endpoint: /api/v1/maintenance/
"""
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.maintenance import MaintenanceDocument, MaintenanceRecord, MaintenanceStatus
from app.models.tool import Tool, ToolStatus
from app.models.user import User
from app.schemas.maintenance import MaintenanceCreate, MaintenanceOut, MaintenanceResolve
from app.services.audit_service import log_action
from app.services.brand_service import validate_document_magic_bytes
from app.services.maintenance_service import send_tool_to_maintenance

router = APIRouter(prefix="/maintenance", tags=["Mantenimiento"])

DOCUMENT_DIR = Path(settings.UPLOAD_DIR) / "maintenance"


async def _get_record_or_404(db: AsyncSession, record_id: int) -> MaintenanceRecord:
    record = await db.get(MaintenanceRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Registro de mantenimiento no encontrado")
    return record


@router.get("", response_model=list[MaintenanceOut])
async def list_maintenance(
    status_filter: MaintenanceStatus | None = Query(None, alias="status"),
    tool_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(MaintenanceRecord).order_by(MaintenanceRecord.sent_date.desc(), MaintenanceRecord.id.desc())
    if status_filter:
        stmt = stmt.where(MaintenanceRecord.status == status_filter)
    if tool_id:
        stmt = stmt.where(MaintenanceRecord.tool_id == tool_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{record_id}", response_model=MaintenanceOut)
async def get_maintenance(record_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await _get_record_or_404(db, record_id)


@router.post("", response_model=MaintenanceOut, status_code=status.HTTP_201_CREATED)
async def send_to_maintenance(
    payload: MaintenanceCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    """
    Envía una herramienta a mantenimiento con un proveedor. Si la
    herramienta estaba dentro de una caja de herramientas, se la saca de
    ahí (no puede estar "en préstamo conjunto" y en el service técnico al
    mismo tiempo) — eso también queda en la auditoría.
    """
    tool = await db.get(Tool, payload.tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Herramienta no encontrada")

    record = await send_tool_to_maintenance(
        db,
        tool=tool,
        provider=payload.provider,
        reason=payload.reason,
        user=user,
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(record)
    return record


@router.post("/{record_id}/document", response_model=MaintenanceOut)
async def upload_maintenance_document(
    record_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    """
    Suma un comprobante al registro (orden de trabajo, cotización, factura)
    — no reemplaza los anteriores, un mismo mantenimiento puede tener
    varios. Acepta imagen (PNG/JPG/WebP) o PDF.
    """
    record = await _get_record_or_404(db, record_id)

    file_bytes = await file.read()
    valid, mime_type = validate_document_magic_bytes(file_bytes)
    if not valid or mime_type == "image/svg+xml":
        raise HTTPException(status_code=400, detail="Archivo inválido (solo PNG, JPG, WebP o PDF)")
    if len(file_bytes) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"El archivo supera los {settings.MAX_UPLOAD_SIZE_MB}MB permitidos")

    document = MaintenanceDocument(
        maintenance_record_id=record_id, file_url="", original_filename=file.filename,
        mime_type=mime_type, uploaded_by_id=user.id,
    )
    db.add(document)
    await db.flush()

    ext = mime_type.split("/")[-1].replace("jpeg", "jpg")
    DOCUMENT_DIR.mkdir(parents=True, exist_ok=True)
    doc_path = DOCUMENT_DIR / f"maintenance_{record_id}_{document.id}.{ext}"
    with open(doc_path, "wb") as f:
        f.write(file_bytes)
    document.file_url = f"/static/uploads/maintenance/maintenance_{record_id}_{document.id}.{ext}"

    await db.commit()
    await db.refresh(record)
    return record


@router.delete("/{record_id}/document/{document_id}", response_model=MaintenanceOut)
async def delete_maintenance_document(
    record_id: int,
    document_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    """Elimina un comprobante subido por error (no borra los demás del mismo registro)."""
    record = await _get_record_or_404(db, record_id)
    document = await db.get(MaintenanceDocument, document_id)
    if not document or document.maintenance_record_id != record_id:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    file_path = DOCUMENT_DIR / Path(document.file_url).name
    file_path.unlink(missing_ok=True)

    await db.delete(document)
    await db.commit()
    await db.refresh(record)
    return record


@router.post("/{record_id}/resolve", response_model=MaintenanceOut)
async def resolve_maintenance(
    record_id: int,
    payload: MaintenanceResolve,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    """
    Cierra un registro de mantenimiento. Si se resolvió, la herramienta
    vuelve a estar disponible (si estaba en una caja, hay que reasignarla
    a mano — al sacarla del service perdió esa referencia a propósito).
    Si no tuvo solución, la herramienta se queda en estado "mantenimiento"
    hasta que alguien la dé de baja explícitamente con motivo y autorización
    (ver POST /tools/{id}/decommission).
    """
    record = await _get_record_or_404(db, record_id)
    if record.status != MaintenanceStatus.en_proceso:
        raise HTTPException(status_code=400, detail="Este registro ya fue cerrado")

    record.status = payload.status
    record.resolution_notes = payload.resolution_notes
    record.resolved_date = date.today()

    tool = await db.get(Tool, record.tool_id)
    if tool and payload.status == MaintenanceStatus.resuelto:
        tool.status = ToolStatus.disponible

    await log_action(
        db,
        user_id=user.id,
        action="tool.maintenance_resolve",
        entity_type="tool",
        entity_id=record.tool_id,
        detail=(
            f"Mantenimiento de '{tool.name if tool else record.tool_id}' cerrado como "
            f"{payload.status.value}."
        ),
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(record)
    return record
