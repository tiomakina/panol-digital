"""fix: ix_users_email deja de ser UNIQUE global (mismo patrón que ix_users_rut en c3d4e5f6a7b8)

Revision ID: d1e2f3a4b5c6
Revises: c3d4e5f6a7b8
Create Date: 2026-09-08 10:00:00.000000

Problema:
  La migración inicial 09446c2b8c7b creó ix_users_email con unique=True
  sobre la columna email sola (índice global, sin tenant_id).

  La migración a1b2c3d4e5f6 (multi-tenant) agregó el constraint compuesto
  uq_users_email_tenant (email + tenant_id) y eliminó users_email_key,
  pero NO tocó ix_users_email.

  Resultado: intentar asignar el mismo email a un usuario de un segundo
  tenant lanza IntegrityError en el COMMIT, aunque el SELECT previo (filtrado
  por tenant vía RLS) no detecte el duplicado.

  Error observado en producción:
    sqlalchemy.exc.IntegrityError: duplicate key value violates unique constraint
    "ix_users_email" — Key (email)=(vmoraless@gmail.com) already exists.

Fix:
  1. Eliminar ix_users_email (UNIQUE en email solo).
  2. Recrearlo como NON-UNIQUE para preservar la utilidad del índice
     en búsquedas por email (la unicidad real está garantizada por
     uq_users_email_tenant que cubre email + tenant_id).

Esta migración es IDEMPOTENTE: usa IF EXISTS / IF NOT EXISTS.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Eliminar el índice único global en email (si todavía existe)
    conn.execute(text("DROP INDEX IF EXISTS ix_users_email"))

    # 2. Crear índice no-único para búsquedas por email sin tenant
    #    (la unicidad por tenant ya está cubierta por uq_users_email_tenant)
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_users_email ON users (email)"
    ))


def downgrade() -> None:
    conn = op.get_bind()

    # Restaurar el índice único original (solo si no hay emails duplicados
    # entre tenants — de lo contrario fallará)
    conn.execute(text("DROP INDEX IF EXISTS ix_users_email"))
    conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)"
    ))
