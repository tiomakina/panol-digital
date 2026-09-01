"""color identificador de mecánico

Revision ID: 793dd8b279d3
Revises: bc93665e646e
Create Date: 2026-08-17 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '793dd8b279d3'
down_revision: Union[str, None] = 'bc93665e646e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ambas columnas nullable: es un dato opcional (no todos los mecánicos
    # van a tener sus herramientas marcadas con color desde el día uno) y
    # aplica sobre todo a usuarios con rol Mecánico, no a todos.
    op.add_column('users', sa.Column('identifying_color', sa.String(length=7), nullable=True))
    op.add_column('users', sa.Column('identifying_color_photo_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'identifying_color_photo_url')
    op.drop_column('users', 'identifying_color')
