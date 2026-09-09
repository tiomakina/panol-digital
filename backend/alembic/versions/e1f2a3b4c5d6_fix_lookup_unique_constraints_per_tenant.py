"""fix lookup unique constraints per tenant

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-09-09 17:00:00.000000

Corrige el constraint de unicidad en las tablas maestras (brands, categories,
locations, providers). La migración original creó un índice unique solo sobre
'name', sin incluir 'tenant_id'. Esto impide que dos tenants distintos tengan
una marca con el mismo nombre (ej. "Bosch").

Fix: eliminar los índices únicos por nombre solo y crear UniqueConstraints
compuestos sobre (name, tenant_id), que es la semántica correcta multi-tenant.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # brands
    op.drop_index('ix_brands_name', table_name='brands', if_exists=True)
    op.create_unique_constraint('uq_brands_name_tenant', 'brands', ['name', 'tenant_id'])
    op.create_index('ix_brands_name', 'brands', ['name'], unique=False)

    # categories
    op.drop_index('ix_categories_name', table_name='categories', if_exists=True)
    op.create_unique_constraint('uq_categories_name_tenant', 'categories', ['name', 'tenant_id'])
    op.create_index('ix_categories_name', 'categories', ['name'], unique=False)

    # locations
    op.drop_index('ix_locations_name', table_name='locations', if_exists=True)
    op.create_unique_constraint('uq_locations_name_tenant', 'locations', ['name', 'tenant_id'])
    op.create_index('ix_locations_name', 'locations', ['name'], unique=False)

    # providers
    op.drop_index('ix_providers_name', table_name='providers', if_exists=True)
    op.create_unique_constraint('uq_providers_name_tenant', 'providers', ['name', 'tenant_id'])
    op.create_index('ix_providers_name', 'providers', ['name'], unique=False)


def downgrade() -> None:
    op.drop_constraint('uq_providers_name_tenant', 'providers', type_='unique')
    op.drop_index('ix_providers_name', table_name='providers')
    op.create_index('ix_providers_name', 'providers', ['name'], unique=True)

    op.drop_constraint('uq_locations_name_tenant', 'locations', type_='unique')
    op.drop_index('ix_locations_name', table_name='locations')
    op.create_index('ix_locations_name', 'locations', ['name'], unique=True)

    op.drop_constraint('uq_categories_name_tenant', 'categories', type_='unique')
    op.drop_index('ix_categories_name', table_name='categories')
    op.create_index('ix_categories_name', 'categories', ['name'], unique=True)

    op.drop_constraint('uq_brands_name_tenant', 'brands', type_='unique')
    op.drop_index('ix_brands_name', table_name='brands')
    op.create_index('ix_brands_name', 'brands', ['name'], unique=True)
