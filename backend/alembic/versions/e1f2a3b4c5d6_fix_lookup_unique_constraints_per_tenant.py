"""fix lookup unique constraints per tenant

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-09-09 17:00:00.000000

Corrige el constraint de unicidad en las tablas maestras (brands, categories,
locations, providers). La migración original creó un índice unique solo sobre
'name', sin incluir 'tenant_id'. Esto impide que dos tenants distintos tengan
una marca con el mismo nombre (ej. "Bosch").

Fix: eliminar los índices únicos por nombre solo y crear UniqueConstraints
compuestos sobre (name, tenant_id), que es la semántica correcta multi-tenant.

Nota: usa SQL condicional (DO $$ ... END $$) para ser idempotente — si los
constraints ya fueron creados manualmente, esta migración los detecta y los
omite sin fallar.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _idempotent_unique_constraint(table: str, constraint: str, columns: list[str]) -> None:
    """Crea el constraint solo si no existe ya (soporta re-runs y fixes manuales previos)."""
    cols = ", ".join(columns)
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = '{constraint}'
            ) THEN
                ALTER TABLE {table}
                    ADD CONSTRAINT {constraint} UNIQUE ({cols});
            END IF;
        END
        $$;
        """
    )


def _idempotent_nonunique_index(index: str, table: str, column: str) -> None:
    """Crea el índice no-único solo si no existe ya."""
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE indexname = '{index}' AND tablename = '{table}'
            ) THEN
                CREATE INDEX {index} ON {table} ({column});
            END IF;
        END
        $$;
        """
    )


def upgrade() -> None:
    # Eliminar índices únicos por nombre solo (si existen)
    for tbl in ("brands", "categories", "locations", "providers"):
        op.drop_index(f"ix_{tbl}_name", table_name=tbl, if_exists=True)

    # Crear constraints compuestos (name, tenant_id) — idempotente
    _idempotent_unique_constraint("brands",     "uq_brands_name_tenant",     ["name", "tenant_id"])
    _idempotent_unique_constraint("categories", "uq_categories_name_tenant", ["name", "tenant_id"])
    _idempotent_unique_constraint("locations",  "uq_locations_name_tenant",  ["name", "tenant_id"])
    _idempotent_unique_constraint("providers",  "uq_providers_name_tenant",  ["name", "tenant_id"])

    # Recrear índices no-únicos para búsquedas por nombre — idempotente
    _idempotent_nonunique_index("ix_brands_name",     "brands",     "name")
    _idempotent_nonunique_index("ix_categories_name", "categories", "name")
    _idempotent_nonunique_index("ix_locations_name",  "locations",  "name")
    _idempotent_nonunique_index("ix_providers_name",  "providers",  "name")


def downgrade() -> None:
    for tbl, cname in [
        ("providers",  "uq_providers_name_tenant"),
        ("locations",  "uq_locations_name_tenant"),
        ("categories", "uq_categories_name_tenant"),
        ("brands",     "uq_brands_name_tenant"),
    ]:
        op.drop_constraint(cname, tbl, type_="unique")
        op.drop_index(f"ix_{tbl}_name", table_name=tbl)
        op.create_index(f"ix_{tbl}_name", tbl, ["name"], unique=True)
