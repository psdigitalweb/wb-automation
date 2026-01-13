"""add supplier_stock_snapshots table for WB Statistics API

Revision ID: fc62982c8480
Revises: a0afa471d2a0
Create Date: 2026-01-13 13:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'fc62982c8480'
down_revision: Union[str, None] = 'a0afa471d2a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create supplier_stock_snapshots table for WB Statistics API reports
    op.create_table('supplier_stock_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('snapshot_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('last_change_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('warehouse_name', sa.Text(), nullable=True),
        sa.Column('nm_id', sa.BigInteger(), nullable=False),
        sa.Column('supplier_article', sa.Text(), nullable=True),
        sa.Column('barcode', sa.Text(), nullable=True),
        sa.Column('tech_size', sa.Text(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('quantity_full', sa.Integer(), nullable=True),
        sa.Column('in_way_to_client', sa.Integer(), nullable=True),
        sa.Column('in_way_from_client', sa.Integer(), nullable=True),
        sa.Column('is_supply', sa.Boolean(), nullable=True),
        sa.Column('is_realization', sa.Boolean(), nullable=True),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('discount', sa.Integer(), nullable=True),
        sa.Column('raw', postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Indexes for efficient queries
    op.create_index('ix_supplier_stock_snapshots_nm_warehouse_date', 
                    'supplier_stock_snapshots', 
                    ['nm_id', 'warehouse_name', sa.text('last_change_date DESC')])
    op.create_index('ix_supplier_stock_snapshots_last_change_date', 
                    'supplier_stock_snapshots', 
                    [sa.text('last_change_date DESC')])
    op.create_index('ix_supplier_stock_snapshots_snapshot_at', 
                    'supplier_stock_snapshots', 
                    [sa.text('snapshot_at DESC')])
    
    # Unique constraint to prevent duplicates on re-runs
    # Based on last_change_date, nm_id, barcode, warehouse_name
    op.create_index('ix_supplier_stock_snapshots_unique', 
                    'supplier_stock_snapshots', 
                    ['last_change_date', 'nm_id', 'barcode', 'warehouse_name'], 
                    unique=True)


def downgrade() -> None:
    op.drop_index('ix_supplier_stock_snapshots_unique', table_name='supplier_stock_snapshots')
    op.drop_index('ix_supplier_stock_snapshots_snapshot_at', table_name='supplier_stock_snapshots')
    op.drop_index('ix_supplier_stock_snapshots_last_change_date', table_name='supplier_stock_snapshots')
    op.drop_index('ix_supplier_stock_snapshots_nm_warehouse_date', table_name='supplier_stock_snapshots')
    op.drop_table('supplier_stock_snapshots')
