"""tool status: agregar en_caja

Revision ID: 62deabb16e55
Revises: 7bd02cee9ddd
Create Date: 2026-08-12 19:15:04.269200

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '62deabb16e55'
down_revision: Union[str, None] = '7bd02cee9ddd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres no deja usar un valor de ENUM recién agregado dentro de la
    # misma transacción en la que se agregó — y env.py corre TODAS las
    # migraciones pendientes de "alembic upgrade head" en una única
    # transacción (context.begin_transaction() envuelve todo
    # run_migrations()), no una por archivo. autocommit_block() hace un
    # COMMIT real antes del ALTER TYPE y arranca una transacción nueva
    # después, así que la siguiente migración (el backfill) ya puede usar
    # 'en_caja' sin problema.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE toolstatus ADD VALUE IF NOT EXISTS 'en_caja'")


def downgrade() -> None:
    # Postgres no soporta "quitar" un valor de un ENUM directamente. El
    # camino estándar es: pasar las filas que usan el valor a otro válido,
    # renombrar el tipo viejo, crear uno nuevo con los valores originales,
    # migrar la columna al tipo nuevo y borrar el tipo viejo.
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE tools SET status = 'disponible' WHERE status = 'en_caja'"))

    op.execute("ALTER TYPE toolstatus RENAME TO toolstatus_old")
    op.execute("CREATE TYPE toolstatus AS ENUM ('disponible', 'prestado', 'mantenimiento', 'baja')")
    op.execute(
        "ALTER TABLE tools ALTER COLUMN status TYPE toolstatus "
        "USING status::text::toolstatus"
    )
    op.execute("DROP TYPE toolstatus_old")
