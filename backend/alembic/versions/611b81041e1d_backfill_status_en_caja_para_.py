"""backfill status en_caja para herramientas ya en cajas

Revision ID: 611b81041e1d
Revises: 62deabb16e55
Create Date: 2026-08-12 19:15:21.803200

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '611b81041e1d'
down_revision: Union[str, None] = '62deabb16e55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Va en una migración separada de la que agrega el valor 'en_caja' al
    # ENUM porque Postgres no deja usar un valor de ENUM recién agregado
    # dentro de la misma transacción en la que se lo agregó.
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE tools SET status = 'en_caja' "
        "WHERE status = 'disponible' "
        "AND id IN (SELECT tool_id FROM toolbox_items)"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE tools SET status = 'disponible' "
        "WHERE status = 'en_caja' "
        "AND id IN (SELECT tool_id FROM toolbox_items)"
    ))
