"""add product details fields: subjectID, description, dimensions, characteristics, createdAt, needKiz

Revision ID: add_product_details
Revises: e1dcde5e611e
Create Date: 2026-01-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'add_product_details'
down_revision: Union[str, None] = 'optimize_v_article_base'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add fields for storing product details from WB API
    op.add_column('products', sa.Column('subject_id', sa.Integer(), nullable=True))
    op.add_column('products', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('dimensions', postgresql.JSONB(), nullable=True))
    op.add_column('products', sa.Column('characteristics', postgresql.JSONB(), nullable=True))
    op.add_column('products', sa.Column('created_at_api', sa.DateTime(timezone=True), nullable=True))
    op.add_column('products', sa.Column('need_kiz', sa.Boolean(), nullable=True))
    
    # Create index on subject_id for filtering
    op.create_index('idx_products_subject_id', 'products', ['subject_id'])


def downgrade() -> None:
    op.drop_index('idx_products_subject_id', table_name='products')
    op.drop_column('products', 'need_kiz')
    op.drop_column('products', 'created_at_api')
    op.drop_column('products', 'characteristics')
    op.drop_column('products', 'dimensions')
    op.drop_column('products', 'description')
    op.drop_column('products', 'subject_id')

