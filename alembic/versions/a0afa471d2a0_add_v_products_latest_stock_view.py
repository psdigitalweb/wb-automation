"""add v_products_latest_stock view

Revision ID: a0afa471d2a0
Revises: 6089711fc16b
Create Date: 2026-01-13 11:56:22.278314

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a0afa471d2a0'
down_revision: Union[str, None] = '6089711fc16b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create or replace view for latest stock per nm_id
    # Sums quantities across warehouses for the latest snapshot time per nm_id
    op.execute("""
        CREATE OR REPLACE VIEW v_products_latest_stock AS
        WITH latest_snapshots AS (
            SELECT DISTINCT ON (nm_id)
                nm_id,
                snapshot_at
            FROM stock_snapshots
            ORDER BY nm_id, snapshot_at DESC
        )
        SELECT 
            ls.nm_id,
            COALESCE(SUM(ss.quantity), 0) AS total_quantity,
            ls.snapshot_at AS stock_at
        FROM latest_snapshots ls
        LEFT JOIN stock_snapshots ss ON ls.nm_id = ss.nm_id AND ls.snapshot_at = ss.snapshot_at
        GROUP BY ls.nm_id, ls.snapshot_at;
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_products_latest_stock;")
