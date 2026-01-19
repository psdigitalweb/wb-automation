"""add articles-base performance indexes and products.vendor_code_norm

Revision ID: f1a2b3c4d5e6
Revises: d1f2a3b4c5d6
Create Date: 2026-01-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "d1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add stored/generated vendor_code_norm to products to make filtering/joining fast and indexable.
    op.execute(
        """
        ALTER TABLE products
        ADD COLUMN IF NOT EXISTS vendor_code_norm TEXT
        GENERATED ALWAYS AS (
            CASE
                WHEN vendor_code IS NULL THEN NULL
                ELSE NULLIF(regexp_replace(trim(both '/' from vendor_code), '^.*/', ''), '')
            END
        ) STORED;
        """
    )

    # Core indexes for project-scoped article base endpoint
    op.execute("CREATE INDEX IF NOT EXISTS ix_products_project_vendor_code_norm ON products (project_id, vendor_code_norm);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_products_project_nm_id ON products (project_id, nm_id);")

    # Latest WB prices lookups: DISTINCT ON (nm_id) ORDER BY created_at DESC
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_price_snapshots_project_nm_created_at "
        "ON price_snapshots (project_id, nm_id, created_at DESC);"
    )

    # Latest WB stock run (max snapshot_at) + aggregation by nm_id
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_stock_snapshots_project_snapshot_at "
        "ON stock_snapshots (project_id, snapshot_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_stock_snapshots_project_nm_snapshot_at "
        "ON stock_snapshots (project_id, nm_id, snapshot_at DESC);"
    )

    # Latest RRP XML run (max snapshot_at) + grouping by vendor_code_norm
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rrp_snapshots_project_snapshot_at_desc "
        "ON rrp_snapshots (project_id, snapshot_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rrp_snapshots_project_vendor_snapshot_at "
        "ON rrp_snapshots (project_id, vendor_code_norm, snapshot_at DESC);"
    )

    # Frontend catalog prices: run_at by (query_type, query_value), then join by nm_id
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_front_prices_brand_run "
        "ON frontend_catalog_price_snapshots (query_type, query_value, snapshot_at DESC, nm_id);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_front_prices_brand_run;")
    op.execute("DROP INDEX IF EXISTS ix_rrp_snapshots_project_vendor_snapshot_at;")
    op.execute("DROP INDEX IF EXISTS ix_rrp_snapshots_project_snapshot_at_desc;")
    op.execute("DROP INDEX IF EXISTS ix_stock_snapshots_project_nm_snapshot_at;")
    op.execute("DROP INDEX IF EXISTS ix_stock_snapshots_project_snapshot_at;")
    op.execute("DROP INDEX IF EXISTS ix_price_snapshots_project_nm_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_products_project_nm_id;")
    op.execute("DROP INDEX IF EXISTS ix_products_project_vendor_code_norm;")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS vendor_code_norm;")

