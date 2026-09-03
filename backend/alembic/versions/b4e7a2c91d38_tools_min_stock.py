"""tools: agregar columna min_stock para alerta de stock mínimo

Revision ID: b4e7a2c91d38
Revises: 3a1f72d8e9c4
Create Date: 2026-09-03 00:00:00.000000
"""
from typing import Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b4e7a2c91d38'
down_revision: Union[str, None] = '3a1f72d8e9c4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # nullable=True porque el valor None significa "sin alerta configurada"
    op.add_column(
        'tools',
        sa.Column('min_stock', sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('tools', 'min_stock')
