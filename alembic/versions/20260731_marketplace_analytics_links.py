"""link WB analytics facts to marketplace products

Revision ID: 20260731_market_analytics
Revises: 20260731_market_fin_links
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260731_market_analytics"
down_revision: Union[str, None] = "20260731_market_fin_links"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLES = (
    ("wb_card_stats_daily", "wb_card_stats"),
    ("wb_search_query_terms", "wb_search_terms"),
    ("wb_search_query_daily", "wb_search_daily"),
    ("wb_funnel_report_rows", "wb_funnel_rows"),
    ("wb_funnel_ctr_daily", "wb_funnel_ctr"),
    ("wb_search_report_products", "wb_search_products"),
    ("wb_search_report_keywords_cache", "wb_search_keywords"),
)


def upgrade() -> None:
    for table_name, short_name in _TABLES:
        op.add_column(table_name, sa.Column("marketplace_product_id", sa.BigInteger(), nullable=True))
        op.execute(
            sa.text(
                f"""
                UPDATE {table_name} fact
                SET marketplace_product_id = identity.marketplace_product_id
                FROM (
                    SELECT mp.project_id, mp.marketplace_item_id,
                           MIN(mp.id) AS marketplace_product_id
                    FROM marketplace_products mp
                    JOIN project_marketplaces pm
                      ON pm.id = mp.project_marketplace_id
                     AND pm.project_id = mp.project_id
                    JOIN marketplaces m ON m.id = pm.marketplace_id
                    WHERE m.code = 'wildberries'
                    GROUP BY mp.project_id, mp.marketplace_item_id
                    HAVING COUNT(*) = 1
                ) identity
                WHERE fact.project_id = identity.project_id
                  AND fact.nm_id::text = identity.marketplace_item_id
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

    op.execute(
        """
        CREATE VIEW v_wb_product_source AS
        WITH canonical_candidates AS (
            SELECT
                mp.*,
                COUNT(*) OVER (
                    PARTITION BY mp.project_id, mp.marketplace_item_id
                ) AS identity_count
            FROM marketplace_products mp
            JOIN project_marketplaces pm
              ON pm.id = mp.project_marketplace_id
             AND pm.project_id = mp.project_id
            JOIN marketplaces m ON m.id = pm.marketplace_id
            WHERE m.code = 'wildberries'
              AND mp.marketplace_item_id ~ '^[0-9]+$'
        ), canonical AS (
            SELECT * FROM canonical_candidates WHERE identity_count = 1
        ), canonical_source AS (
            SELECT
                p.id,
                c.marketplace_item_id::bigint AS nm_id,
                COALESCE(c.marketplace_sku, p.vendor_code) AS vendor_code,
                p.category,
                COALESCE(c.title, p.title) AS title,
                COALESCE(p.brand, c.attributes->>'brand') AS brand,
                COALESCE(p.subject_name, c.attributes->>'subject_name') AS subject_name,
                p.price_u,
                p.sale_price_u,
                p.rating,
                p.feedbacks,
                p.sizes,
                p.colors,
                p.pics,
                p.raw,
                COALESCE(c.updated_at, p.updated_at) AS updated_at,
                COALESCE(c.first_seen_at, p.first_seen_at) AS first_seen_at,
                COALESCE(
                    p.subject_id,
                    CASE WHEN c.attributes->>'subject_id' ~ '^[0-9]+$'
                         THEN (c.attributes->>'subject_id')::integer ELSE NULL END
                ) AS subject_id,
                p.description,
                p.dimensions,
                p.characteristics,
                p.created_at_api,
                p.need_kiz,
                c.project_id,
                COALESCE(
                    p.vendor_code_norm,
                    NULLIF(regexp_replace(trim(both '/' from c.marketplace_sku), '^.*/', ''), '')
                ) AS vendor_code_norm,
                p.content_hash,
                p.content_version,
                p.content_changed_at,
                p.content_last_seen_at,
                p.wb_content_updated_at,
                p.main_photo_asset_hash,
                c.id AS marketplace_product_id
            FROM canonical c
            LEFT JOIN products p
              ON p.project_id = c.project_id
             AND p.nm_id::text = c.marketplace_item_id
        )
        SELECT * FROM canonical_source
        UNION ALL
        SELECT
            p.id,
            p.nm_id,
            p.vendor_code,
            p.category,
            p.title,
            p.brand,
            p.subject_name,
            p.price_u,
            p.sale_price_u,
            p.rating,
            p.feedbacks,
            p.sizes,
            p.colors,
            p.pics,
            p.raw,
            p.updated_at,
            p.first_seen_at,
            p.subject_id,
            p.description,
            p.dimensions,
            p.characteristics,
            p.created_at_api,
            p.need_kiz,
            p.project_id,
            p.vendor_code_norm,
            p.content_hash,
            p.content_version,
            p.content_changed_at,
            p.content_last_seen_at,
            p.wb_content_updated_at,
            p.main_photo_asset_hash,
            NULL::bigint AS marketplace_product_id
        FROM products p
        WHERE NOT EXISTS (
            SELECT 1 FROM canonical_source c
            WHERE c.project_id = p.project_id AND c.nm_id = p.nm_id
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_wb_product_source")
    for table_name, short_name in reversed(_TABLES):
        op.drop_index(f"ix_{short_name}_marketplace_product", table_name=table_name)
        op.drop_constraint(
            f"fk_{short_name}_marketplace_product",
            table_name,
            type_="foreignkey",
        )
        op.drop_column(table_name, "marketplace_product_id")
