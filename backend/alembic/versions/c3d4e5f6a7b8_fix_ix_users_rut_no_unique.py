"""fix: ix_users_rut deja de ser UNIQUE global (multi-tenant permite mismo RUT en distintos tenants)

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-09-09 00:00:00.000000

Problema:
  La migración bc93665e646e creó el índice ix_users_rut con unique=True
  sobre la columna rut sola. La migración a1b2c3d4e5f6 (multi-tenant) eliminó
  el CONSTRAINT users_rut_key pero NO este índice UNIQUE.

  Resultado: intentar agregar el mismo RUT a un segundo tenant lanza
  IntegrityError → HTTP 500, aunque la constraint correcta (uq_users_rut_tenant)
  que permite el mismo RUT en distintos tenants ya existe.

Fix:
  1. Eliminar ix_users_rut (UNIQUE en rut solo).
  2. Recrearlo como NON-UNIQUE para preservar la utilidad del índice
     en búsquedas por RUT (la unicidad real está garantizada por
     uq_users_rut_tenant que cubre rut + tenant_id).

Esta migración es IDEMPOTENTE: usa IF EXISTS / IF NOT EXISTS.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Eliminar el índice único global en rut (si todavía existe)
    conn.execute(text("DROP INDEX IF EXISTS ix_users_rut"))

    # 2. Crear índice no-único para búsquedas por rut sin tenant
    #    (la unicidad por tenant ya está cubierta por uq_users_rut_tenant)
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_users_rut ON users (rut)"
    ))


def downgrade() -> None:
    conn = op.get_bind()

    # Restaurar el índice único original (solo si no hay RUTs duplicados
    # entre tenants — de lo contrario fallará)
    conn.execute(text("DROP INDEX IF EXISTS ix_users_rut"))
    conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_rut ON users (rut)"
    ))
