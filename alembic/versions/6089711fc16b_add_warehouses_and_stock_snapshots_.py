"""add warehouses and stock snapshots tables

Revision ID: 6089711fc16b
Revises: 0f69aa9a434f
Create Date: 2026-01-13 11:54:44.105976

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6089711fc16b'
down_revision: Union[str, None] = '0f69aa9a434f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create wb_warehouses table (warehouse/office directory)
    op.create_table('wb_warehouses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('wb_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('city', sa.Text(), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('type', sa.Text(), nullable=True),
        sa.Column('raw', sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_wb_warehouses_wb_id', 'wb_warehouses', ['wb_id'], unique=True)
    op.create_index('ix_wb_warehouses_name', 'wb_warehouses', ['name'])
    
    # Create stock_snapshots table (stock facts)
    op.create_table('stock_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nm_id', sa.Integer(), nullable=False),
        sa.Column('warehouse_wb_id', sa.Integer(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('snapshot_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('raw', sa.dialects.postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_stock_snapshots_nm_id', 'stock_snapshots', ['nm_id'])
    op.create_index('ix_stock_snapshots_snapshot_at', 'stock_snapshots', ['snapshot_at'])
    op.create_index('ix_stock_snapshots_nm_id_snapshot_at', 'stock_snapshots', ['nm_id', sa.text('snapshot_at DESC')])
    op.create_index('ix_stock_snapshots_warehouse_snapshot_at', 'stock_snapshots', ['warehouse_wb_id', sa.text('snapshot_at DESC')])


def downgrade() -> None:
    op.drop_index('ix_stock_snapshots_warehouse_snapshot_at', table_name='stock_snapshots')
    op.drop_index('ix_stock_snapshots_nm_id_snapshot_at', table_name='stock_snapshots')
    op.drop_index('ix_stock_snapshots_snapshot_at', table_name='stock_snapshots')
    op.drop_index('ix_stock_snapshots_nm_id', table_name='stock_snapshots')
    op.drop_table('stock_snapshots')
    op.drop_index('ix_wb_warehouses_name', table_name='wb_warehouses')
    op.drop_index('ix_wb_warehouses_wb_id', table_name='wb_warehouses')
    op.drop_table('wb_warehouses')
