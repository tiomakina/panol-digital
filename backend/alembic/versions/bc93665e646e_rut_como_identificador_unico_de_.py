"""rut como identificador único de usuario

Revision ID: bc93665e646e
Revises: 696e95076ec8
Create Date: 2026-08-17 16:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bc93665e646e'
down_revision: Union[str, None] = '696e95076ec8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _check_digit(number: int) -> str:
    """
    Dígito verificador módulo 11, duplicado a propósito de
    app/core/rut.py:compute_check_digit — las migraciones no importan
    código vivo de la app (así no quedan atadas a cambios futuros ahí).
    """
    total = 0
    factor = 2
    for digit in reversed(str(number)):
        total += int(digit) * factor
        factor = 2 if factor == 7 else factor + 1
    remainder = 11 - (total % 11)
    if remainder == 11:
        return "0"
    if remainder == 10:
        return "K"
    return str(remainder)


def upgrade() -> None:
    op.add_column('users', sa.Column('rut', sa.String(length=12), nullable=True))

    # Backfill para instalaciones que ya tenían usuarios antes de este
    # cambio: cada uno recibe un RUT ficticio pero válido (dígito
    # verificador real) derivado de su id, en un rango que no choca con
    # RUTs reales (9 dígitos con prefijo 90000000), solo para no dejar la
    # columna NULL — un Jefe puede corregirlo después desde Usuarios con
    # el RUT real de cada persona. Nuevas instalaciones (sin usuarios
    # todavía) no pasan por este loop.
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id FROM users ORDER BY id")).fetchall()
    for (user_id,) in rows:
        number = 90_000_000 + user_id
        rut = f"{number}-{_check_digit(number)}"
        bind.execute(sa.text("UPDATE users SET rut = :rut WHERE id = :id"), {"rut": rut, "id": user_id})

    op.alter_column('users', 'rut', existing_type=sa.String(length=12), nullable=False)
    op.create_index(op.f('ix_users_rut'), 'users', ['rut'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_users_rut'), table_name='users')
    op.drop_column('users', 'rut')
