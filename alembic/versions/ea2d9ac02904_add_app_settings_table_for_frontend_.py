"""add app_settings table for frontend prices config

Revision ID: ea2d9ac02904
Revises: 2a8757976d5a
Create Date: 2026-01-13 19:19:38.991161

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ea2d9ac02904'
down_revision: Union[str, None] = '2a8757976d5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create app_settings table for storing application settings
    op.create_table(
        'app_settings',
        sa.Column('key', sa.Text(), nullable=False),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('key')
    )
    
    # Insert default settings for frontend prices
    op.execute("""
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (
            'frontend_prices.brand_base_url',
            '{"url": "https://catalog.wb.ru/brands/v4/catalog?ab_testing=false&appType=1&brand=41189&curr=rub&dest=-1255987&lang=ru&page=1&sort=popular&spp=30&uclusters=1"}'::jsonb,
            now()
        )
        ON CONFLICT (key) DO NOTHING
    """)
    
    op.execute("""
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (
            'frontend_prices.sleep_ms',
            '{"value": 800}'::jsonb,
            now()
        )
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    # Drop table
    op.drop_table('app_settings')
