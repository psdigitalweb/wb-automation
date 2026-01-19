"""add project_id to data tables (products, stock_snapshots, price_snapshots)

Revision ID: add_project_id_to_data
Revises: optimize_v_article_base
Create Date: 2026-01-16 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_project_id_to_data'
down_revision: Union[str, None] = 'add_marketplaces_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if tables exist
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    # Add project_id to products table if it exists
    if 'products' in existing_tables:
        # Check if column already exists
        existing_columns = [col['name'] for col in inspector.get_columns('products')]
        if 'project_id' not in existing_columns:
            op.add_column('products', sa.Column('project_id', sa.Integer(), nullable=True))
            op.create_foreign_key(
                'fk_products_project_id',
                'products', 'projects',
                ['project_id'], ['id'],
                ondelete='CASCADE'
            )
            op.create_index('idx_products_project_id', 'products', ['project_id'])
    
    # Add project_id to stock_snapshots table if it exists
    if 'stock_snapshots' in existing_tables:
        existing_columns = [col['name'] for col in inspector.get_columns('stock_snapshots')]
        if 'project_id' not in existing_columns:
            op.add_column('stock_snapshots', sa.Column('project_id', sa.Integer(), nullable=True))
            op.create_foreign_key(
                'fk_stock_snapshots_project_id',
                'stock_snapshots', 'projects',
                ['project_id'], ['id'],
                ondelete='CASCADE'
            )
            op.create_index('idx_stock_snapshots_project_id', 'stock_snapshots', ['project_id'])
    
    # Add project_id to price_snapshots table if it exists
    if 'price_snapshots' in existing_tables:
        existing_columns = [col['name'] for col in inspector.get_columns('price_snapshots')]
        if 'project_id' not in existing_columns:
            op.add_column('price_snapshots', sa.Column('project_id', sa.Integer(), nullable=True))
            op.create_foreign_key(
                'fk_price_snapshots_project_id',
                'price_snapshots', 'projects',
                ['project_id'], ['id'],
                ondelete='CASCADE'
            )
            op.create_index('idx_price_snapshots_project_id', 'price_snapshots', ['project_id'])


def downgrade() -> None:
    # Remove project_id columns and indexes
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    if 'price_snapshots' in existing_tables:
        existing_columns = [col['name'] for col in inspector.get_columns('price_snapshots')]
        if 'project_id' in existing_columns:
            op.drop_index('idx_price_snapshots_project_id', table_name='price_snapshots')
            op.drop_constraint('fk_price_snapshots_project_id', 'price_snapshots', type_='foreignkey')
            op.drop_column('price_snapshots', 'project_id')
    
    if 'stock_snapshots' in existing_tables:
        existing_columns = [col['name'] for col in inspector.get_columns('stock_snapshots')]
        if 'project_id' in existing_columns:
            op.drop_index('idx_stock_snapshots_project_id', table_name='stock_snapshots')
            op.drop_constraint('fk_stock_snapshots_project_id', 'stock_snapshots', type_='foreignkey')
            op.drop_column('stock_snapshots', 'project_id')
    
    if 'products' in existing_tables:
        existing_columns = [col['name'] for col in inspector.get_columns('products')]
        if 'project_id' in existing_columns:
            op.drop_index('idx_products_project_id', table_name='products')
            op.drop_constraint('fk_products_project_id', 'products', type_='foreignkey')
            op.drop_column('products', 'project_id')

