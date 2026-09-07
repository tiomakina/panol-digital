"""multi-tenant: agregar tenant_id a todas las tablas de negocio

Revision ID: a1b2c3d4e5f6
Revises: b4e7a2c91d38
Create Date: 2026-09-07 10:00:00.000000

Esta migración es el corazón del aislamiento de datos multi-empresa (Fase 2).

Estrategia de migración:
1. Agrega tenant_id como columna NULLABLE en cada tabla (para no romper datos existentes).
2. Rellena TODOS los registros existentes con el tenant por defecto 'vms-ingenieria',
   ya que toda la data actual pertenece a ese cliente.
3. Altera la columna a NOT NULL + agrega un índice para las consultas filtradas.

En downgrade se elimina la columna en cada tabla (operación destructiva — los datos
de tenant quedan sin registro, pero la estructura vuelve al estado mono-tenant).

Tablas afectadas:
  users, tools, loans, toolboxes, toolbox_audits, maintenance_records,
  brand_configs, brands (lookup), categories, locations, providers, audit_logs
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'b4e7a2c91d38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tablas que reciben la columna tenant_id (todas las de negocio excepto
# las child-tables accedidas solo via FK: toolbox_items, toolbox_audit_items,
# maintenance_documents — su aislamiento es implícito via la tabla padre).
TABLES = [
    "users",
    "tools",
    "loans",
    "toolboxes",
    "toolbox_audits",
    "maintenance_records",
    "brand_configs",
    "brands",
    "categories",
    "locations",
    "providers",
    "audit_logs",
]

# Tenant por defecto para backfill — toda la data existente es de este cliente.
DEFAULT_TENANT = "vms-ingenieria"


def upgrade() -> None:
    for table in TABLES:
        # 1. Agrega la columna como nullable para no romper datos existentes
        op.add_column(table, sa.Column("tenant_id", sa.String(100), nullable=True))

        # 2. Backfill: todos los registros existentes pertenecen a vms-ingenieria
        op.execute(
            f"UPDATE {table} SET tenant_id = '{DEFAULT_TENANT}' WHERE tenant_id IS NULL"  # noqa: S608
        )

        # 3. Pone la columna como NOT NULL ahora que todos los registros tienen valor
        op.alter_column(table, "tenant_id", nullable=False)

        # 4. Crea índice simple para acelerar las consultas filtradas por tenant
        op.create_index(
            f"ix_{table}_tenant_id",
            table,
            ["tenant_id"],
        )

    # 5. Las tablas maestras tenían unique=True en 'name' globalmente.
    #    Con multi-tenant la unicidad debe ser POR tenant: eliminamos el
    #    índice único global y creamos uno compuesto (name, tenant_id).
    LOOKUP_TABLES = {
        "brands": "brands_name_key",
        "categories": "categories_name_key",
        "locations": "locations_name_key",
        "providers": "providers_name_key",
    }
    for table, old_unique in LOOKUP_TABLES.items():
        # Eliminar el índice único global (PostgreSQL lo nombra así por defecto)
        try:
            op.drop_constraint(old_unique, table, type_="unique")
        except Exception:
            pass  # Si ya no existe, ignorar

        # Crear restricción única compuesta (name, tenant_id)
        op.create_unique_constraint(
            f"uq_{table}_name_tenant",
            table,
            ["name", "tenant_id"],
        )

    # 6. User.rut y User.email también deben ser únicos por tenant
    #    (el mismo RUT puede ser admin de dos empresas distintas).
    #    Eliminamos los índices únicos globales y creamos compuestos.
    try:
        op.drop_constraint("users_rut_key", "users", type_="unique")
    except Exception:
        pass
    op.create_unique_constraint("uq_users_rut_tenant", "users", ["rut", "tenant_id"])

    try:
        op.drop_constraint("users_email_key", "users", type_="unique")
    except Exception:
        pass
    op.create_unique_constraint("uq_users_email_tenant", "users", ["email", "tenant_id"])


def downgrade() -> None:
    # Restaurar restricciones únicas globales en users
    op.drop_constraint("uq_users_email_tenant", "users", type_="unique")
    op.create_unique_constraint("users_email_key", "users", ["email"])
    op.drop_constraint("uq_users_rut_tenant", "users", type_="unique")
    op.create_unique_constraint("users_rut_key", "users", ["rut"])

    # Restaurar restricciones únicas globales en tablas maestras
    LOOKUP_TABLES = {
        "brands": "brands_name_key",
        "categories": "categories_name_key",
        "locations": "locations_name_key",
        "providers": "providers_name_key",
    }
    for table, old_unique in LOOKUP_TABLES.items():
        op.drop_constraint(f"uq_{table}_name_tenant", table, type_="unique")
        op.create_unique_constraint(old_unique, table, ["name"])

    for table in reversed(TABLES):
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_column(table, "tenant_id")
