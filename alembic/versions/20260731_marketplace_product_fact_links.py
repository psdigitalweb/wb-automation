"""link WB review and content facts to marketplace products

Revision ID: 20260731_marketplace_fact_links
Revises: 20260731_marketplace_identity
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260731_marketplace_fact_links"
down_revision: Union[str, None] = "20260731_marketplace_identity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES = (
    "wb_feedback_snapshots",
    "wb_product_content_versions",
    "wb_product_main_photo_assets",
    "wb_product_main_photo_periods",
)


def _backfill(table_name: str) -> None:
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


def upgrade() -> None:
    for table_name in _TABLES:
        op.add_column(
            table_name,
            sa.Column("marketplace_product_id", sa.BigInteger(), nullable=True),
        )
        _backfill(table_name)
        op.create_foreign_key(
            f"fk_{table_name}_project_marketplace_product",
            table_name,
            "marketplace_products",
            ["project_id", "marketplace_product_id"],
            ["project_id", "id"],
        )
        op.create_index(
            f"ix_{table_name}_project_marketplace_product",
            table_name,
            ["project_id", "marketplace_product_id"],
        )


def downgrade() -> None:
    for table_name in reversed(_TABLES):
        op.drop_index(
            f"ix_{table_name}_project_marketplace_product",
            table_name=table_name,
        )
        op.drop_constraint(
            f"fk_{table_name}_project_marketplace_product",
            table_name,
            type_="foreignkey",
        )
        op.drop_column(table_name, "marketplace_product_id")
