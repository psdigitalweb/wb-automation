"""link WB inventory and price facts to marketplace products

Revision ID: 20260731_market_inv_price
Revises: 20260731_marketplace_fact_links
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260731_market_inv_price"
down_revision: Union[str, None] = "20260731_marketplace_fact_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PROJECT_TABLES = (
    "price_snapshots",
    "stock_snapshots",
    "wb_current_metrics",
    "wb_showcase_product_presence",
    "wb_showcase_price_snapshots",
    "wb_fbo_stock_daily_snapshots",
    "wb_spp_events",
)


def _add_product_link(table_name: str) -> None:
    short_name = {
        "price_snapshots": "price_snapshots",
        "stock_snapshots": "stock_snapshots",
        "wb_current_metrics": "wb_current_metrics",
        "wb_showcase_product_presence": "wb_showcase_presence",
        "wb_showcase_price_snapshots": "wb_showcase_prices",
        "wb_fbo_stock_daily_snapshots": "wb_fbo_daily",
        "wb_spp_events": "wb_spp_events",
    }[table_name]
    op.add_column(table_name, sa.Column("marketplace_product_id", sa.BigInteger(), nullable=True))
    op.execute(
        sa.text(
            f"""
            UPDATE {table_name} fact
            SET marketplace_product_id = mp.id
            FROM marketplace_products mp
            JOIN project_marketplaces pm
              ON pm.id = mp.project_marketplace_id
             AND pm.project_id = mp.project_id
            JOIN marketplaces m ON m.id = pm.marketplace_id
            WHERE fact.project_id = mp.project_id
              AND m.code = 'wildberries'
              AND mp.marketplace_item_id = fact.nm_id::text
              AND fact.marketplace_product_id IS NULL
            """
        )
    )
    op.create_foreign_key(
        f"fk_{short_name}_marketplace_product",
        table_name,
        "marketplace_products",
        ["project_id", "marketplace_product_id"],
        ["project_id", "id"],
    )
    op.create_index(
        f"ix_{short_name}_marketplace_product",
        table_name,
        ["project_id", "marketplace_product_id"],
    )


def upgrade() -> None:
    for table_name in _PROJECT_TABLES:
        _add_product_link(table_name)

    op.add_column("supplier_stock_snapshots", sa.Column("project_id", sa.Integer(), nullable=True))
    op.add_column(
        "supplier_stock_snapshots",
        sa.Column("marketplace_product_id", sa.BigInteger(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            WITH unique_products AS (
                SELECT
                    mp.marketplace_item_id,
                    MIN(mp.project_id) AS project_id,
                    MIN(mp.id) AS marketplace_product_id
                FROM marketplace_products mp
                JOIN project_marketplaces pm
                  ON pm.id = mp.project_marketplace_id
                 AND pm.project_id = mp.project_id
                JOIN marketplaces m ON m.id = pm.marketplace_id
                WHERE m.code = 'wildberries'
                GROUP BY mp.marketplace_item_id
                HAVING COUNT(DISTINCT mp.project_id) = 1
            )
            UPDATE supplier_stock_snapshots fact
            SET project_id = product.project_id,
                marketplace_product_id = product.marketplace_product_id
            FROM unique_products product
            WHERE product.marketplace_item_id = fact.nm_id::text
              AND fact.project_id IS NULL
            """
        )
    )
    op.create_foreign_key(
        "fk_supplier_stocks_project",
        "supplier_stock_snapshots",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_supplier_stocks_marketplace_product",
        "supplier_stock_snapshots",
        "marketplace_products",
        ["project_id", "marketplace_product_id"],
        ["project_id", "id"],
    )
    op.drop_index("ix_supplier_stock_snapshots_unique", table_name="supplier_stock_snapshots")
    op.create_index(
        "ix_supplier_stocks_project_unique",
        "supplier_stock_snapshots",
        ["project_id", "last_change_date", "nm_id", "barcode", "warehouse_name"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )
    op.create_index(
        "ix_supplier_stocks_marketplace_product",
        "supplier_stock_snapshots",
        ["project_id", "marketplace_product_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_supplier_stocks_marketplace_product", table_name="supplier_stock_snapshots")
    op.drop_index("ix_supplier_stocks_project_unique", table_name="supplier_stock_snapshots")
    op.create_index(
        "ix_supplier_stock_snapshots_unique",
        "supplier_stock_snapshots",
        ["last_change_date", "nm_id", "barcode", "warehouse_name"],
        unique=True,
    )
    op.drop_constraint(
        "fk_supplier_stocks_marketplace_product",
        "supplier_stock_snapshots",
        type_="foreignkey",
    )
    op.drop_constraint("fk_supplier_stocks_project", "supplier_stock_snapshots", type_="foreignkey")
    op.drop_column("supplier_stock_snapshots", "marketplace_product_id")
    op.drop_column("supplier_stock_snapshots", "project_id")

    short_names = {
        "price_snapshots": "price_snapshots",
        "stock_snapshots": "stock_snapshots",
        "wb_current_metrics": "wb_current_metrics",
        "wb_showcase_product_presence": "wb_showcase_presence",
        "wb_showcase_price_snapshots": "wb_showcase_prices",
        "wb_fbo_stock_daily_snapshots": "wb_fbo_daily",
        "wb_spp_events": "wb_spp_events",
    }
    for table_name in reversed(_PROJECT_TABLES):
        short_name = short_names[table_name]
        op.drop_index(f"ix_{short_name}_marketplace_product", table_name=table_name)
        op.drop_constraint(
            f"fk_{short_name}_marketplace_product",
            table_name,
            type_="foreignkey",
        )
        op.drop_column(table_name, "marketplace_product_id")
