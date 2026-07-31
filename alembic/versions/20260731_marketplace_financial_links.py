"""link product-scoped financial facts to marketplace products

Revision ID: 20260731_market_fin_links
Revises: 20260731_market_inv_price
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260731_market_fin_links"
down_revision: Union[str, None] = "20260731_market_inv_price"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_product_link(table_name: str, short_name: str) -> None:
    op.add_column(table_name, sa.Column("marketplace_product_id", sa.BigInteger(), nullable=True))
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
    # This table is intentionally handled without a synchronous backfill or
    # index build: production finance history is large, and either operation
    # would turn an otherwise additive deploy into a long blocking migration.
    # New/rebuilt rows dual-write the identity; old rows keep their nm_id
    # compatibility path until an online backfill is scheduled.
    op.add_column(
        "wb_financial_events",
        sa.Column("marketplace_product_id", sa.BigInteger(), nullable=True),
    )
    op.execute(
        """
        ALTER TABLE wb_financial_events
        ADD CONSTRAINT fk_wb_financial_events_marketplace_product
        FOREIGN KEY (project_id, marketplace_product_id)
        REFERENCES marketplace_products (project_id, id)
        NOT VALID
        """
    )
    _add_product_link("additional_cost_entries", "additional_costs")
    op.add_column("additional_cost_entries", sa.Column("marketplace_item_id", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE additional_cost_entries
        SET marketplace_item_id = nm_id::text
        WHERE scope = 'product'
          AND nm_id IS NOT NULL
          AND marketplace_item_id IS NULL
        """
    )
    op.drop_constraint(
        "ck_additional_cost_entries_scope_project",
        "additional_cost_entries",
        type_="check",
    )
    op.drop_constraint(
        "ck_additional_cost_entries_scope_marketplace",
        "additional_cost_entries",
        type_="check",
    )
    op.drop_constraint(
        "ck_additional_cost_entries_scope_product",
        "additional_cost_entries",
        type_="check",
    )
    op.create_check_constraint(
        "ck_additional_cost_entries_scope_project",
        "additional_cost_entries",
        sa.text(
            "(scope != 'project') OR (marketplace_code IS NULL AND internal_sku IS NULL "
            "AND nm_id IS NULL AND marketplace_item_id IS NULL)"
        ),
    )
    op.create_check_constraint(
        "ck_additional_cost_entries_scope_marketplace",
        "additional_cost_entries",
        sa.text(
            "(scope != 'marketplace') OR (marketplace_code IS NOT NULL AND internal_sku IS NULL "
            "AND nm_id IS NULL AND marketplace_item_id IS NULL)"
        ),
    )
    op.create_check_constraint(
        "ck_additional_cost_entries_scope_product",
        "additional_cost_entries",
        sa.text(
            "(scope != 'product') OR (internal_sku IS NOT NULL OR "
            "(marketplace_code IS NOT NULL AND marketplace_item_id IS NOT NULL))"
        ),
    )
    op.execute(
        sa.text(
            """
            WITH unique_identity AS (
                SELECT
                    mp.project_id,
                    m.code AS marketplace_code,
                    mp.marketplace_item_id,
                    MIN(mp.id) AS marketplace_product_id
                FROM marketplace_products mp
                JOIN project_marketplaces pm
                  ON pm.id = mp.project_marketplace_id
                 AND pm.project_id = mp.project_id
                JOIN marketplaces m ON m.id = pm.marketplace_id
                GROUP BY mp.project_id, m.code, mp.marketplace_item_id
                HAVING COUNT(*) = 1
            )
            UPDATE additional_cost_entries fact
            SET marketplace_product_id = identity.marketplace_product_id
            FROM unique_identity identity
            WHERE fact.project_id = identity.project_id
              AND fact.scope = 'product'
              AND lower(COALESCE(fact.marketplace_code, 'wildberries')) = identity.marketplace_code
              AND COALESCE(fact.marketplace_item_id, fact.nm_id::text) = identity.marketplace_item_id
              AND fact.marketplace_product_id IS NULL
            """
        )
    )


def downgrade() -> None:
    # The column check also makes local development databases recoverable if an
    # earlier draft of this not-yet-released revision was applied.
    has_marketplace_item_id = any(
        column["name"] == "marketplace_item_id"
        for column in sa.inspect(op.get_bind()).get_columns("additional_cost_entries")
    )
    if has_marketplace_item_id:
        op.drop_constraint(
            "ck_additional_cost_entries_scope_product",
            "additional_cost_entries",
            type_="check",
        )
        op.drop_constraint(
            "ck_additional_cost_entries_scope_marketplace",
            "additional_cost_entries",
            type_="check",
        )
        op.drop_constraint(
            "ck_additional_cost_entries_scope_project",
            "additional_cost_entries",
            type_="check",
        )
        op.execute(
            """
            UPDATE additional_cost_entries
            SET internal_sku = marketplace_item_id
            WHERE scope = 'product'
              AND internal_sku IS NULL
              AND marketplace_item_id IS NOT NULL
            """
        )
        op.create_check_constraint(
            "ck_additional_cost_entries_scope_project",
            "additional_cost_entries",
            sa.text("(scope != 'project') OR (marketplace_code IS NULL AND internal_sku IS NULL AND nm_id IS NULL)"),
        )
        op.create_check_constraint(
            "ck_additional_cost_entries_scope_marketplace",
            "additional_cost_entries",
            sa.text("(scope != 'marketplace') OR (marketplace_code IS NOT NULL AND internal_sku IS NULL AND nm_id IS NULL)"),
        )
        op.create_check_constraint(
            "ck_additional_cost_entries_scope_product",
            "additional_cost_entries",
            sa.text("(scope != 'product') OR (internal_sku IS NOT NULL)"),
        )
        op.drop_column("additional_cost_entries", "marketplace_item_id")
    op.drop_index("ix_additional_costs_marketplace_product", table_name="additional_cost_entries")
    op.drop_constraint(
        "fk_additional_costs_marketplace_product",
        "additional_cost_entries",
        type_="foreignkey",
    )
    op.drop_column("additional_cost_entries", "marketplace_product_id")

    op.drop_constraint(
        "fk_wb_financial_events_marketplace_product",
        "wb_financial_events",
        type_="foreignkey",
    )
    op.drop_column("wb_financial_events", "marketplace_product_id")
