"""loans: agregar columna reminder_sent para recordatorio pre-vencimiento

Revision ID: 3a1f72d8e9c4
Revises: ff993e164489
Create Date: 2026-09-03 00:00:00.000000
"""
from typing import Union
from alembic import op
import sqlalchemy as sa

revision: str = '3a1f72d8e9c4'
down_revision: Union[str, None] = 'ff993e164489'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Columna con default=False para que no afecte filas existentes
    op.add_column(
        'loans',
        sa.Column('reminder_sent', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('loans', 'reminder_sent')
