"""add system_marketplace_settings table

Revision ID: add_system_marketplace_settings
Revises: add_marketplaces_tables
Create Date: 2026-01-20 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'add_system_marketplace_settings'
down_revision: Union[str, None] = 'add_marketplaces_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if table exists
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    # Create system_marketplace_settings table if it doesn't exist
    if 'system_marketplace_settings' not in existing_tables:
        op.create_table(
            'system_marketplace_settings',
            sa.Column('marketplace_code', sa.String(length=50), nullable=False),
            sa.Column('is_globally_enabled', sa.Boolean(), nullable=False, server_default='TRUE'),
            sa.Column('is_visible', sa.Boolean(), nullable=False, server_default='TRUE'),
            sa.Column('sort_order', sa.Integer(), nullable=False, server_default='100'),
            sa.Column('settings_json', postgresql.JSONB(), nullable=False, server_default='{}'),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('marketplace_code')
        )
        
        # Create index on sort_order for efficient ordering
        op.create_index('idx_system_marketplace_settings_sort_order', 'system_marketplace_settings', ['sort_order'])


def downgrade() -> None:
    op.drop_index('idx_system_marketplace_settings_sort_order', table_name='system_marketplace_settings')
    op.drop_table('system_marketplace_settings')
