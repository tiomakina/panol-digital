"""mantenimiento solicitada por mecánico

Revision ID: 696e95076ec8
Revises: 3aa54bc75b72
Create Date: 2026-08-17 15:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '696e95076ec8'
down_revision: Union[str, None] = '3aa54bc75b72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Mismo patrón que 62deabb16e55 (agregar 'en_caja'): Postgres no deja
    # usar un valor de ENUM recién agregado dentro de la misma transacción
    # en la que se agregó, y "alembic upgrade head" corre todo en una sola
    # transacción — autocommit_block() hace el ALTER TYPE en su propia
    # transacción real, así el resto de esta misma migración (que no llega
    # a usar el valor nuevo, pero sí las que vengan después) queda tranquilo.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE toolstatus ADD VALUE IF NOT EXISTS 'mantenimiento_solicitada'")

    # Quién solicitó la mantención desde la caja (rol Mecánico) y cuándo —
    # separado de MaintenanceRecord porque en este punto todavía no hay un
    # registro real de mantenimiento: es solo un aviso a Encargado/Jefe
    # para que lo confirmen y recién ahí se cree el MaintenanceRecord (ver
    # POST /api/v1/toolboxes/{id}/tools/{tool_id}/request-maintenance).
    op.add_column('tools', sa.Column('maintenance_requested_by_id', sa.Integer(), nullable=True))
    op.add_column('tools', sa.Column('maintenance_requested_at', sa.DateTime(), nullable=True))
    op.add_column('tools', sa.Column('maintenance_requested_reason', sa.Text(), nullable=True))
    op.create_foreign_key(
        'fk_tools_maintenance_requested_by_id', 'tools', 'users',
        ['maintenance_requested_by_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_tools_maintenance_requested_by_id', 'tools', type_='foreignkey')
    op.drop_column('tools', 'maintenance_requested_reason')
    op.drop_column('tools', 'maintenance_requested_at')
    op.drop_column('tools', 'maintenance_requested_by_id')

    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE tools SET status = 'mantenimiento' WHERE status = 'mantenimiento_solicitada'"
    ))
    op.execute("ALTER TYPE toolstatus RENAME TO toolstatus_old")
    op.execute(
        "CREATE TYPE toolstatus AS ENUM "
        "('disponible', 'prestado', 'mantenimiento', 'baja', 'en_caja')"
    )
    op.execute(
        "ALTER TABLE tools ALTER COLUMN status TYPE toolstatus "
        "USING status::text::toolstatus"
    )
    op.execute("DROP TYPE toolstatus_old")
