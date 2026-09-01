"""
Lógica compartida para enviar una herramienta a mantenimiento — la usan
tanto el endpoint dedicado (POST /api/v1/maintenance) como el flujo de
auditoría de cajas (POST /api/v1/toolbox-audits/.../send-to-maintenance),
para no duplicar la validación de estado, la salida de la caja y el
asiento de auditoría.
"""
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.maintenance import MaintenanceRecord, MaintenanceStatus
from app.models.tool import Tool, ToolStatus
from app.models.toolbox import ToolboxItem
from app.models.user import User
from app.services.audit_service import log_action


async def send_tool_to_maintenance(
    db: AsyncSession,
    *,
    tool: Tool,
    provider: str | None,
    reason: str,
    user: User,
    ip_address: str | None,
    extra_detail: str | None = None,
) -> MaintenanceRecord:
    """
    Valida que la herramienta pueda mandarse a mantenimiento, la saca de su
    caja si estaba en una, crea el registro y deja el asiento de auditoría.
    No hace commit — eso queda a cargo de quien llama (así el caller puede
    sumar sus propios cambios a la misma transacción, ej. marcar el item
    de una auditoría de caja).
    """
    # mantenimiento_solicitada: el caso de una herramienta con una solicitud
    # de un Mecánico (ver POST .../request-maintenance) que un Encargado/Jefe
    # está confirmando recién ahora — tiene que poder convertirse en un
    # MaintenanceRecord real igual que si viniera "disponible" o "en_caja".
    if tool.status not in (ToolStatus.disponible, ToolStatus.en_caja, ToolStatus.mantenimiento_solicitada):
        raise HTTPException(
            status_code=400,
            detail="Solo se puede enviar a mantenimiento una herramienta disponible, en una caja de "
            "herramientas, o con una mantención solicitada",
        )

    removed_from_toolbox = False
    if tool.status in (ToolStatus.en_caja, ToolStatus.mantenimiento_solicitada):
        item_result = await db.execute(select(ToolboxItem).where(ToolboxItem.tool_id == tool.id))
        item = item_result.scalar_one_or_none()
        if item:
            await db.delete(item)
            removed_from_toolbox = True

    record = MaintenanceRecord(
        tool_id=tool.id,
        provider=provider,
        reason=reason,
        status=MaintenanceStatus.en_proceso,
        sent_date=date.today(),
        created_by_id=user.id,
    )
    db.add(record)
    tool.status = ToolStatus.mantenimiento
    await db.flush()

    detail = f"Herramienta '{tool.name}' enviada a mantenimiento. Motivo: {reason}."
    if provider:
        detail += f" Proveedor: {provider}."
    if removed_from_toolbox:
        detail += " Se sacó de su caja de herramientas."
    if extra_detail:
        detail += f" {extra_detail}"

    await log_action(
        db,
        user_id=user.id,
        action="tool.send_to_maintenance",
        entity_type="tool",
        entity_id=tool.id,
        detail=detail,
        ip_address=ip_address,
    )

    await db.flush()
    return record
