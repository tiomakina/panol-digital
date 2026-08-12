"""
API de Auditoría/Inventario de Cajas de Herramientas.
Endpoint: /api/v1/toolbox-audits/

Flujo: se abre una auditoría para una caja (arma un checklist con las
herramientas que tenía en ese momento), el mecánico va revisando cada
una (bueno / dañado / faltante, con observación si no es "bueno"), puede
mandar directo a mantenimiento la que lo necesite, y al final se cierra
la auditoría.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.tool import Tool
from app.models.toolbox import Toolbox, ToolboxItem
from app.models.toolbox_audit import AuditItemCondition, ToolboxAudit, ToolboxAuditItem, ToolboxAuditStatus
from app.models.user import User
from app.schemas.toolbox_audit import (
    SendItemToMaintenanceInput,
    ToolboxAuditCreate,
    ToolboxAuditItemOut,
    ToolboxAuditItemUpdate,
    ToolboxAuditOut,
)
from app.services.audit_service import log_action
from app.services.maintenance_service import send_tool_to_maintenance

router = APIRouter(prefix="/toolbox-audits", tags=["Auditoría de Cajas"])


async def _get_audit_or_404(db: AsyncSession, audit_id: int) -> ToolboxAudit:
    audit = await db.get(ToolboxAudit, audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Auditoría no encontrada")
    return audit


async def _get_item_or_404(db: AsyncSession, audit_id: int, item_id: int) -> ToolboxAuditItem:
    result = await db.execute(
        select(ToolboxAuditItem).where(ToolboxAuditItem.id == item_id, ToolboxAuditItem.audit_id == audit_id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item de auditoría no encontrado")
    return item


@router.get("", response_model=list[ToolboxAuditOut])
async def list_audits(
    toolbox_id: int | None = None, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    stmt = select(ToolboxAudit).order_by(ToolboxAudit.audit_date.desc(), ToolboxAudit.id.desc())
    if toolbox_id:
        stmt = stmt.where(ToolboxAudit.toolbox_id == toolbox_id)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{audit_id}", response_model=ToolboxAuditOut)
async def get_audit(audit_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await _get_audit_or_404(db, audit_id)


@router.post("", response_model=ToolboxAuditOut, status_code=status.HTTP_201_CREATED)
async def create_audit(
    payload: ToolboxAuditCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("mecanico")),
):
    """Abre una auditoría nueva con un item por cada herramienta que la caja tiene en este momento."""
    toolbox = await db.get(Toolbox, payload.toolbox_id)
    if not toolbox:
        raise HTTPException(status_code=404, detail="Caja de herramientas no encontrada")

    existing_open = await db.execute(
        select(ToolboxAudit).where(
            ToolboxAudit.toolbox_id == toolbox.id, ToolboxAudit.status == ToolboxAuditStatus.en_progreso
        )
    )
    if existing_open.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Esta caja ya tiene una auditoría en progreso")

    audit = ToolboxAudit(toolbox_id=toolbox.id, performed_by_id=user.id, notes=payload.notes)
    db.add(audit)
    await db.flush()

    items_result = await db.execute(select(ToolboxItem).where(ToolboxItem.toolbox_id == toolbox.id))
    for item in items_result.scalars().all():
        db.add(ToolboxAuditItem(audit_id=audit.id, tool_id=item.tool_id))

    await log_action(
        db,
        user_id=user.id,
        action="toolbox.audit_start",
        entity_type="toolbox",
        entity_id=toolbox.id,
        detail=f"Auditoría iniciada para la caja '{toolbox.name}'.",
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(audit)
    return audit


@router.put("/{audit_id}/items/{item_id}", response_model=ToolboxAuditItemOut)
async def update_audit_item(
    audit_id: int,
    item_id: int,
    payload: ToolboxAuditItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("mecanico")),
):
    """Registra el resultado de revisar una herramienta del checklist."""
    audit = await _get_audit_or_404(db, audit_id)
    if audit.status != ToolboxAuditStatus.en_progreso:
        raise HTTPException(status_code=400, detail="Esta auditoría ya está cerrada")

    item = await _get_item_or_404(db, audit_id, item_id)

    if payload.condition != AuditItemCondition.bueno and not (payload.observation or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Si la herramienta no está en buen estado hay que dejar una observación que lo justifique",
        )

    item.condition = payload.condition
    item.observation = payload.observation
    item.reviewed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(item)
    return item


@router.post("/{audit_id}/items/{item_id}/send-to-maintenance", response_model=ToolboxAuditItemOut)
async def send_audit_item_to_maintenance(
    audit_id: int,
    item_id: int,
    payload: SendItemToMaintenanceInput,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("mecanico")),
):
    """
    Manda directo a mantenimiento una herramienta encontrada dañada durante
    la auditoría — la saca de la caja (vía el mismo flujo que el módulo de
    Mantenimiento) y lo marca en el checklist.
    """
    audit = await _get_audit_or_404(db, audit_id)
    if audit.status != ToolboxAuditStatus.en_progreso:
        raise HTTPException(status_code=400, detail="Esta auditoría ya está cerrada")

    item = await _get_item_or_404(db, audit_id, item_id)
    if item.sent_to_maintenance:
        raise HTTPException(status_code=400, detail="Esta herramienta ya fue enviada a mantenimiento")

    tool = await db.get(Tool, item.tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Herramienta no encontrada")

    reason = payload.reason or item.observation
    if not reason:
        raise HTTPException(status_code=400, detail="Hace falta un motivo (o una observación cargada) para enviarla")

    await send_tool_to_maintenance(
        db,
        tool=tool,
        provider=payload.provider,
        reason=reason,
        user=user,
        ip_address=request.client.host if request.client else None,
        extra_detail=f"Enviada desde la auditoría #{audit.id} de la caja.",
    )

    item.condition = AuditItemCondition.dañado
    if not item.observation:
        item.observation = reason
    item.sent_to_maintenance = True
    item.reviewed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(item)
    return item


@router.post("/{audit_id}/complete", response_model=ToolboxAuditOut)
async def complete_audit(
    audit_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("mecanico")),
):
    """Cierra la auditoría — exige que cada herramienta del checklist ya haya sido revisada."""
    audit = await _get_audit_or_404(db, audit_id)
    if audit.status != ToolboxAuditStatus.en_progreso:
        raise HTTPException(status_code=400, detail="Esta auditoría ya está cerrada")

    pending = [item for item in audit.items if item.condition is None]
    if pending:
        raise HTTPException(
            status_code=400,
            detail=f"Todavía faltan {len(pending)} herramienta(s) por revisar antes de cerrar la auditoría",
        )

    audit.status = ToolboxAuditStatus.completado
    audit.completed_at = datetime.utcnow()

    toolbox = await db.get(Toolbox, audit.toolbox_id)
    await log_action(
        db,
        user_id=user.id,
        action="toolbox.audit_complete",
        entity_type="toolbox",
        entity_id=audit.toolbox_id,
        detail=(
            f"Auditoría #{audit.id} de la caja '{toolbox.name if toolbox else audit.toolbox_id}' cerrada — "
            f"{len(audit.items)} herramienta(s) revisadas."
        ),
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(audit)
    return audit
