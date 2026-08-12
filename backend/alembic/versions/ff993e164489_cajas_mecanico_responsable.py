"""cajas: mecanico responsable

Revision ID: ff993e164489
Revises: c2b598057a80
Create Date: 2026-08-12 18:25:00.231229

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ff993e164489'
down_revision: Union[str, None] = 'c2b598057a80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('toolboxes', sa.Column('responsible_user_id', sa.Integer(), nullable=True))
    # Nombre explícito de la constraint — con None, el downgrade autogenerado
    # no tiene forma de encontrar la FK para borrarla (op.drop_constraint
    # necesita el nombre, no lo puede inferir).
    op.create_foreign_key(
        'fk_toolboxes_responsible_user_id_users', 'toolboxes', 'users', ['responsible_user_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint('fk_toolboxes_responsible_user_id_users', 'toolboxes', type_='foreignkey')
    op.drop_column('toolboxes', 'responsible_user_id')
