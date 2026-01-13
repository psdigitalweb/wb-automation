"""add v_products_latest_price view

Revision ID: 0f69aa9a434f
Revises: e1dcde5e611e
Create Date: 2026-01-13 11:46:19.336558

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f69aa9a434f'
down_revision: Union[str, None] = 'e1dcde5e611e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create or replace view for latest prices per nm_id
    # Using DISTINCT ON for efficient latest record selection
    op.execute("""
        CREATE OR REPLACE VIEW v_products_latest_price AS
        SELECT DISTINCT ON (nm_id)
            nm_id,
            wb_price,
            wb_discount,
            spp,
            customer_price,
            rrc,
            created_at AS price_at
        FROM price_snapshots
        ORDER BY nm_id, created_at DESC;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_products_latest_price;")
