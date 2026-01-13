"""add frontend_catalog_price_snapshots table

Revision ID: 2a8757976d5a
Revises: 213c70612608
Create Date: 2026-01-13 18:52:45.266816

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '2a8757976d5a'
down_revision: Union[str, None] = '213c70612608'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create frontend_catalog_price_snapshots table for storing public catalog prices
    op.create_table(
        'frontend_catalog_price_snapshots',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('snapshot_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('source', sa.Text(), server_default='catalog_wb', nullable=False),
        sa.Column('query_type', sa.Text(), server_default='brand', nullable=False),
        sa.Column('query_value', sa.Text(), nullable=False),
        sa.Column('page', sa.Integer(), nullable=False),
        sa.Column('nm_id', sa.BigInteger(), nullable=False),
        sa.Column('vendor_code', sa.Text(), nullable=True),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('price_basic', sa.Numeric(12, 2), nullable=True),
        sa.Column('price_product', sa.Numeric(12, 2), nullable=True),
        sa.Column('sale_percent', sa.Integer(), nullable=True),
        sa.Column('discount_calc_percent', sa.Integer(), nullable=True),
        sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_front_price_snapshots_snapshot_at', 'frontend_catalog_price_snapshots', ['snapshot_at'], postgresql_ops={'snapshot_at': 'DESC'})
    op.create_index('ix_front_price_snapshots_nm_id_snapshot_at', 'frontend_catalog_price_snapshots', ['nm_id', 'snapshot_at'], postgresql_ops={'snapshot_at': 'DESC'})
    op.create_index('ix_front_price_snapshots_query', 'frontend_catalog_price_snapshots', ['query_type', 'query_value', 'snapshot_at'], postgresql_ops={'snapshot_at': 'DESC'})


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_front_price_snapshots_query', table_name='frontend_catalog_price_snapshots')
    op.drop_index('ix_front_price_snapshots_nm_id_snapshot_at', table_name='frontend_catalog_price_snapshots')
    op.drop_index('ix_front_price_snapshots_snapshot_at', table_name='frontend_catalog_price_snapshots')
    
    # Drop table
    op.drop_table('frontend_catalog_price_snapshots')
