"""
API de Cajas de Herramientas — agrupa herramientas para prestarlas/gestionarlas en conjunto.
Endpoint: /api/v1/toolboxes/
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.models.tool import Tool, ToolStatus
from app.models.toolbox import Toolbox, ToolboxItem
from app.models.user import User, UserRole
from app.schemas.tool import RequestMaintenanceInput
from app.schemas.toolbox import ToolboxCreate, ToolboxOut, ToolboxUpdate
from app.services.audit_service import log_action
from app.services.notification_service import send_email
from app.services.qr_service import generate_toolbox_qr

router = APIRouter(prefix="/toolboxes", tags=["Cajas de Herramientas"])


async def _get_toolbox_or_404(db: AsyncSession, toolbox_id: int) -> Toolbox:
    toolbox = await db.get(Toolbox, toolbox_id)
    if not toolbox:
        raise HTTPException(status_code=404, detail="Caja de herramientas no encontrada")
    return toolbox


async def _validate_responsible(db: AsyncSession, responsible_user_id: int | None) -> None:
    if responsible_user_id is None:
        return
    responsible = await db.get(User, responsible_user_id)
    if not responsible or not responsible.is_active:
        raise HTTPException(status_code=404, detail="Responsable no encontrado o inactivo")


def _require_own_toolbox_if_mecanico(toolbox: Toolbox, user: User) -> None:
    """
    Un Mecánico solo puede ver/operar la caja de la que es responsable —
    Encargado y Jefe ven cualquiera. Se usa tanto para el detalle como
    para "solicitar mantención".
    """
    if user.role.value == "mecanico" and toolbox.responsible_user_id != user.id:
        raise HTTPException(status_code=403, detail="Esta caja no está asignada a tu usuario")


def _to_out(toolbox: Toolbox, viewer: User) -> ToolboxOut:
    """
    Igual que en Herramientas (tools.py::_to_out): quien no es Jefe no ve
    costo de compra ni valor de rescate. Acá hacía falta el mismo
    enmascarado porque ToolboxItemOut anida el ToolOut completo de cada
    herramienta — sin esto, Cajas era una forma de ver esos valores
    esquivando la restricción que ya aplica en Herramientas.
    """
    data = ToolboxOut.model_validate(toolbox)
    if viewer.role.value != "jefe":
        for item in data.items:
            if item.tool:
                item.tool.purchase_cost = None
                item.tool.salvage_value = None
    return data


@router.get("", response_model=list[ToolboxOut])
async def list_toolboxes(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Toolbox).order_by(Toolbox.name)
    # Un Mecánico solo ve la(s) caja(s) de la(s) que es responsable — el
    # resto del directorio de cajas no le corresponde (a diferencia de
    # Encargado/Jefe, que ven todas para poder administrarlas).
    if user.role.value == "mecanico":
        stmt = stmt.where(Toolbox.responsible_user_id == user.id)
    result = await db.execute(stmt)
    return [_to_out(t, user) for t in result.scalars().all()]


@router.get("/{toolbox_id}", response_model=ToolboxOut)
async def get_toolbox(
    toolbox_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
):
    toolbox = await _get_toolbox_or_404(db, toolbox_id)
    _require_own_toolbox_if_mecanico(toolbox, user)
    return _to_out(toolbox, user)


@router.post("", response_model=ToolboxOut, status_code=status.HTTP_201_CREATED)
async def create_toolbox(
    payload: ToolboxCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    """Crea una caja de herramientas vacía y genera su código QR."""
    await _validate_responsible(db, payload.responsible_user_id)
    toolbox = Toolbox(**payload.model_dump())
    db.add(toolbox)
    await db.flush()

    base_url = str(request.base_url).rstrip("/")
    toolbox.qr_code_url = generate_toolbox_qr(toolbox.id, base_url)

    await db.commit()
    await db.refresh(toolbox)
    return _to_out(toolbox, user)


@router.put("/{toolbox_id}", response_model=ToolboxOut)
async def update_toolbox(
    toolbox_id: int,
    payload: ToolboxUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("encargado")),
):
    toolbox = await _get_toolbox_or_404(db, toolbox_id)
    fields = payload.model_dump(exclude_unset=True)
    if "responsible_user_id" in fields:
        await _validate_responsible(db, fields["responsible_user_id"])
    for field, value in fields.items():
        setattr(toolbox, field, value)

    await db.commit()
    await db.refresh(toolbox)
    return _to_out(toolbox, user)


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
    if tool.status != ToolStatus.disponible:
        raise HTTPException(status_code=400, detail="La herramienta no está disponible")

    existing = await db.execute(select(ToolboxItem).where(ToolboxItem.tool_id == tool_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Esa herramienta ya está en otra caja")

    db.add(ToolboxItem(toolbox_id=toolbox.id, tool_id=tool_id))
    tool.status = ToolStatus.en_caja
    await db.commit()
    await db.refresh(toolbox)
    return _to_out(toolbox, user)


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

    tool = await db.get(Tool, tool_id)
    if tool and tool.status == ToolStatus.en_caja:
        tool.status = ToolStatus.disponible

    await db.delete(item)
    await db.commit()
    await db.refresh(toolbox)
    return _to_out(toolbox, user)


@router.post("/{toolbox_id}/tools/{tool_id}/request-maintenance", response_model=ToolboxOut)
async def request_tool_maintenance(
    toolbox_id: int,
    tool_id: int,
    payload: RequestMaintenanceInput,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("mecanico")),
):
    """
    Un Mecánico pide mantención para una herramienta de su caja asignada —
    a diferencia de "Enviar a mantenimiento" (Encargado/Jefe, crea el
    MaintenanceRecord de una), esto solo deja la herramienta en
    "mantención solicitada" y avisa por email a Encargado y Jefe; son
    ellos quienes confirman desde Mantenimiento/Herramientas. Encargado y
    Jefe también pueden llamar este endpoint (por si prefieren dejar
    constancia de quién lo pidió), pero para ellos ya existe el flujo
    directo de siempre.
    """
    toolbox = await _get_toolbox_or_404(db, toolbox_id)
    _require_own_toolbox_if_mecanico(toolbox, user)

    item_result = await db.execute(
        select(ToolboxItem).where(ToolboxItem.toolbox_id == toolbox_id, ToolboxItem.tool_id == tool_id)
    )
    if not item_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Esa herramienta no está en esta caja")

    tool = await db.get(Tool, tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Herramienta no encontrada")
    if tool.status != ToolStatus.en_caja:
        raise HTTPException(status_code=400, detail="Esta herramienta ya tiene una solicitud o gestión en curso")

    tool.status = ToolStatus.mantenimiento_solicitada
    # Se asigna la RELACIÓN (no solo el _id) para que tool.maintenance_requested_by
    # quede poblado en el objeto ya en memoria — si solo se setea el _id, el
    # atributo de relación (cargado lazy="joined" desde antes de este cambio)
    # queda desactualizado hasta que algo fuerce un refresh desde la base.
    tool.maintenance_requested_by = user
    tool.maintenance_requested_at = datetime.utcnow()
    tool.maintenance_requested_reason = payload.reason

    await log_action(
        db,
        user_id=user.id,
        action="tool.maintenance_requested",
        entity_type="tool",
        entity_id=tool.id,
        detail=(
            f"{user.full_name} solicitó mantención para '{tool.name}' desde la caja '{toolbox.name}'."
            + (f" Motivo: {payload.reason}." if payload.reason else "")
        ),
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    await db.refresh(toolbox)

    # Aviso por email a Encargado y Jefe — mejor esfuerzo: send_email ya
    # no rompe nada si SMTP no está configurado (devuelve False en
    # silencio, ver notification_service.py), así que no hace falta
    # try/except acá para no arriesgar la respuesta HTTP por un canal
    # opcional.
    recipients = await db.execute(
        select(User).where(User.role.in_([UserRole.encargado, UserRole.jefe]), User.is_active.is_(True))
    )
    subject = f"Mantención solicitada: {tool.name}"
    body = (
        f"{user.full_name} solicitó mantención para \"{tool.name}\" desde la caja \"{toolbox.name}\".\n"
        + (f"Motivo: {payload.reason}\n" if payload.reason else "")
        + "Podés confirmarla desde Herramientas o Mantenimiento en Pañol 360."
    )
    for recipient in recipients.scalars().all():
        await send_email(recipient.email, subject, body)

    return _to_out(toolbox, user)
