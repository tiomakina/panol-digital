"""
Servicio de Auditoría — registra acciones sensibles para trazabilidad forense.
Diseñado por Diego (Security).
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def log_action(
    db: AsyncSession,
    *,
    user_id: int | None,
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    detail: str | None = None,
    ip_address: str | None = None,
) -> None:
    """
    Registra una entrada de auditoría. No hace commit propio — se apoya en el
    commit de la transacción del endpoint que la invoca, para que quede
    atómica junto con el cambio que audita.
    """
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail,
            ip_address=ip_address,
        )
    )
