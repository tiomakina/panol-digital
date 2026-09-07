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

La migración es IDEMPOTENTE: usa IF NOT EXISTS / IF EXISTS para que pueda
reintentarse sin error si una ejecución anterior quedó incompleta.

En downgrade se elimina la columna en cada tabla (operación destructiva — los datos
de tenant quedan sin registro, pero la estructura vuelve al estado mono-tenant).

Tablas afectadas:
  users, tools, loans, toolboxes, toolbox_audits, maintenance_records,
  brand_configs, brands (lookup), categories, locations, providers, audit_logs
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

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
    conn = op.get_bind()

    for table in TABLES:
        # 1. Agrega la columna como nullable — IF NOT EXISTS evita error si ya existe
        conn.execute(text(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(100)"
        ))

        # 2. Backfill: todos los registros existentes pertenecen a vms-ingenieria
        conn.execute(text(
            f"UPDATE {table} SET tenant_id = :tenant WHERE tenant_id IS NULL"
        ).bindparams(tenant=DEFAULT_TENANT))

        # 3. NOT NULL (idempotente: si ya es NOT NULL PostgreSQL lo ignora silenciosamente)
        conn.execute(text(
            f"ALTER TABLE {table} ALTER COLUMN tenant_id SET NOT NULL"
        ))

        # 4. Índice — IF NOT EXISTS evita error si ya existe
        conn.execute(text(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id ON {table} (tenant_id)"
        ))

    # 5. Las tablas maestras tenían unique=True en 'name' globalmente.
    #    Con multi-tenant la unicidad debe ser POR tenant.
    LOOKUP_TABLES = {
        "brands": "brands_name_key",
        "categories": "categories_name_key",
        "locations": "locations_name_key",
        "providers": "providers_name_key",
    }
    for table, old_unique in LOOKUP_TABLES.items():
        # Eliminar el índice único global si todavía existe
        conn.execute(text(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_schema = current_schema()
                      AND constraint_name   = '{old_unique}'
                      AND table_name        = '{table}'
                      AND constraint_type   = 'UNIQUE'
                ) THEN
                    ALTER TABLE {table} DROP CONSTRAINT {old_unique};
                END IF;
            END $$;
        """))

        # Crear constraint único compuesto si no existe todavía
        conn.execute(text(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_schema = current_schema()
                      AND constraint_name   = 'uq_{table}_name_tenant'
                      AND table_name        = '{table}'
                      AND constraint_type   = 'UNIQUE'
                ) THEN
                    ALTER TABLE {table}
                        ADD CONSTRAINT uq_{table}_name_tenant UNIQUE (name, tenant_id);
                END IF;
            END $$;
        """))

    # 6. User.rut y User.email también deben ser únicos por tenant
    for old_constraint, new_constraint, columns in [
        ("users_rut_key",   "uq_users_rut_tenant",   "rut, tenant_id"),
        ("users_email_key", "uq_users_email_tenant", "email, tenant_id"),
    ]:
        conn.execute(text(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_schema = current_schema()
                      AND constraint_name   = '{old_constraint}'
                      AND table_name        = 'users'
                      AND constraint_type   = 'UNIQUE'
                ) THEN
                    ALTER TABLE users DROP CONSTRAINT {old_constraint};
                END IF;
            END $$;
        """))
        conn.execute(text(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_schema = current_schema()
                      AND constraint_name   = '{new_constraint}'
                      AND table_name        = 'users'
                      AND constraint_type   = 'UNIQUE'
                ) THEN
                    ALTER TABLE users ADD CONSTRAINT {new_constraint} UNIQUE ({columns});
                END IF;
            END $$;
        """))


def downgrade() -> None:
    conn = op.get_bind()

    # Restaurar restricciones únicas globales en users
    for new_constraint, old_constraint, column in [
        ("uq_users_email_tenant", "users_email_key", "email"),
        ("uq_users_rut_tenant",   "users_rut_key",   "rut"),
    ]:
        conn.execute(text(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_schema = current_schema()
                      AND constraint_name   = '{new_constraint}'
                      AND table_name        = 'users'
                ) THEN
                    ALTER TABLE users DROP CONSTRAINT {new_constraint};
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_schema = current_schema()
                      AND constraint_name   = '{old_constraint}'
                      AND table_name        = 'users'
                ) THEN
                    ALTER TABLE users ADD CONSTRAINT {old_constraint} UNIQUE ({column});
                END IF;
            END $$;
        """))

    # Restaurar restricciones únicas globales en tablas maestras
    LOOKUP_TABLES = {
        "brands": "brands_name_key",
        "categories": "categories_name_key",
        "locations": "locations_name_key",
        "providers": "providers_name_key",
    }
    for table, old_unique in LOOKUP_TABLES.items():
        conn.execute(text(f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_schema = current_schema()
                      AND constraint_name   = 'uq_{table}_name_tenant'
                      AND table_name        = '{table}'
                ) THEN
                    ALTER TABLE {table} DROP CONSTRAINT uq_{table}_name_tenant;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE constraint_schema = current_schema()
                      AND constraint_name   = '{old_unique}'
                      AND table_name        = '{table}'
                ) THEN
                    ALTER TABLE {table} ADD CONSTRAINT {old_unique} UNIQUE (name);
                END IF;
            END $$;
        """))

    # Eliminar índices y columnas tenant_id
    for table in reversed(TABLES):
        conn.execute(text(
            f"DROP INDEX IF EXISTS ix_{table}_tenant_id"
        ))
        conn.execute(text(
            f"ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id"
        ))
