"""add brand to products

Revision ID: e1dcde5e611e
Revises: a77217f699d1
Create Date: 2026-01-13 11:08:22.711063

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1dcde5e611e'
down_revision: Union[str, None] = 'a77217f699d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add all columns required by db_products.ensure_schema
    op.add_column('products', sa.Column('title', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('brand', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('subject_name', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('price_u', sa.BigInteger(), nullable=True))
    op.add_column('products', sa.Column('sale_price_u', sa.BigInteger(), nullable=True))
    op.add_column('products', sa.Column('rating', sa.Numeric(precision=3, scale=2), nullable=True))
    op.add_column('products', sa.Column('feedbacks', sa.Integer(), nullable=True))
    op.add_column('products', sa.Column('sizes', sa.dialects.postgresql.JSONB(), nullable=True))
    op.add_column('products', sa.Column('colors', sa.dialects.postgresql.JSONB(), nullable=True))
    op.add_column('products', sa.Column('pics', sa.dialects.postgresql.JSONB(), nullable=True))
    op.add_column('products', sa.Column('raw', sa.dialects.postgresql.JSONB(), nullable=True))
    op.add_column('products', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.add_column('products', sa.Column('first_seen_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    
    # Create indexes for brand and subject_name
    op.create_index('idx_products_brand', 'products', ['brand'])
    op.create_index('idx_products_subject', 'products', ['subject_name'])


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('idx_products_subject', table_name='products')
    op.drop_index('idx_products_brand', table_name='products')
    
    # Drop columns
    op.drop_column('products', 'first_seen_at')
    op.drop_column('products', 'updated_at')
    op.drop_column('products', 'raw')
    op.drop_column('products', 'pics')
    op.drop_column('products', 'colors')
    op.drop_column('products', 'sizes')
    op.drop_column('products', 'feedbacks')
    op.drop_column('products', 'rating')
    op.drop_column('products', 'sale_price_u')
    op.drop_column('products', 'price_u')
    op.drop_column('products', 'subject_name')
    op.drop_column('products', 'brand')
    op.drop_column('products', 'title')
