"""backfill stable internal catalog and marketplace product mappings

Revision ID: 20260731_product_mapping_sync
Revises: 20260731_market_analytics
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260731_product_mapping_sync"
down_revision: Union[str, None] = "20260731_market_analytics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_marketplace_product_mappings_project_status",
        "marketplace_product_mappings",
        ["project_id", "mapping_status"],
    )
    op.execute(
        """
        CREATE INDEX ix_internal_catalog_products_project_sku_normalized
        ON internal_catalog_products (project_id, lower(btrim(internal_sku)))
        """
    )
    op.execute(
        """
        CREATE INDEX ix_marketplace_products_project_sku_normalized
        ON marketplace_products (
            project_id,
            lower(NULLIF(regexp_replace(trim(both '/' from marketplace_sku), '^.*/', ''), ''))
        )
        WHERE marketplace_sku IS NOT NULL
        """
    )

    # This is an idempotent data migration. Runtime catalog and marketplace
    # ingests call the same reconciliation service for all future changes.
    from app.services.product_mapping_sync import reconcile_all_project_product_mappings

    reconcile_all_project_product_mappings(op.get_bind())


def downgrade() -> None:
    # Mapping rows are business data and are intentionally preserved.
    op.drop_index(
        "ix_marketplace_products_project_sku_normalized",
        table_name="marketplace_products",
    )
    op.drop_index(
        "ix_internal_catalog_products_project_sku_normalized",
        table_name="internal_catalog_products",
    )
    op.drop_index(
        "ix_marketplace_product_mappings_project_status",
        table_name="marketplace_product_mappings",
    )
