"""remove email unique constraint from users

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-09 19:00:00.000000

Diseño corregido:
- El email NO es único, ni por tenant ni globalmente.
  Múltiples usuarios de la misma empresa pueden compartir una cuenta de
  correo (empresas con pocas casillas de email) o un número de teléfono.
- El RUT sigue siendo el único identificador del usuario (único por tenant).

Elimina el constraint uq_users_email_tenant de la tabla users.
La migración es idempotente: usa DO $$ IF NOT EXISTS $$ para no fallar
si el constraint ya fue eliminado manualmente.
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Eliminar constraint de unicidad de email — idempotente
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_users_email_tenant'
            ) THEN
                ALTER TABLE users DROP CONSTRAINT uq_users_email_tenant;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    # Recrear el constraint si se hace rollback
    # Nota: puede fallar si ya hay emails duplicados en la BD — en ese caso
    # se debe limpiar la data antes de hacer downgrade.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_users_email_tenant'
            ) THEN
                ALTER TABLE users ADD CONSTRAINT uq_users_email_tenant UNIQUE (email, tenant_id);
            END IF;
        END
        $$;
        """
    )
