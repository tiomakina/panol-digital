"""
TenantMixin — columna tenant_id para aislamiento multi-empresa.

Todos los modelos que almacenan datos de negocio heredan de este mixin.
La columna tenant_id guarda el alias del cliente (ej: 'vms-ingenieria')
como texto simple — no es una FK a otra tabla para evitar joins adicionales
y mantener la flexibilidad de renombrar tenants sin cascada.

El filtro automático (via SQLAlchemy do_orm_execute) en database.py
agrega WHERE tenant_id = :tenant a todas las consultas ORM que usen un
modelo con este mixin, a menos que el execute lleve la opción
skip_tenant_filter=True.
"""
from sqlalchemy import String, Index
from sqlalchemy.orm import Mapped, mapped_column


class TenantMixin:
    """
    Mixin de aislamiento de datos por empresa cliente.

    Uso:
        class Tool(TenantMixin, Base):
            __tablename__ = "tools"
            ...
    """
    tenant_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="vms-ingenieria",  # valor por defecto solo para compatibilidad durante la migración
        index=True,
    )
