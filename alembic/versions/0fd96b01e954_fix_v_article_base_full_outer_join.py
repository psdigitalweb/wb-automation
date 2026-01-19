"""fix v_article_base full outer join

Revision ID: 0fd96b01e954
Revises: c2d3e4f5a6b7
Create Date: 2026-01-16 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0fd96b01e954'
down_revision: Union[str, None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if required tables exist before creating VIEW
    from sqlalchemy import inspect
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    required_tables = ['supplier_stock_snapshots', 'price_snapshots', 'frontend_catalog_price_snapshots', 'rrp_snapshots']
    missing_tables = [t for t in required_tables if t not in existing_tables]
    
    if missing_tables:
        print(f"Skipping v_article_base view creation: missing tables {missing_tables}")
        return
    
    # Fix v_article_base to use UNION for better data linking
    # First drop the view, then recreate it
    op.execute("DROP VIEW IF EXISTS v_article_base;")
    op.execute("""
        CREATE OR REPLACE VIEW v_article_base AS
        WITH 
        -- Latest supplier stock aggregated by nm_id + barcode
        supplier_aggregated AS (
            SELECT 
                nm_id,
                barcode,
                MAX(supplier_article) AS supplier_article,
                SUM(COALESCE(quantity_full, quantity, 0)) AS supplier_qty_total,
                MAX(last_change_date) AS supplier_updated_at
            FROM supplier_stock_snapshots
            WHERE nm_id IS NOT NULL
            GROUP BY nm_id, barcode
        ),
        latest_supplier AS (
            SELECT 
                nm_id,
                barcode,
                supplier_article,
                -- Normalize supplier_article: take part after '/' and trim
                CASE 
                    WHEN supplier_article LIKE '%/%' THEN TRIM(SPLIT_PART(supplier_article, '/', 2))
                    ELSE TRIM(supplier_article)
                END AS supplier_article_norm,
                supplier_qty_total,
                supplier_updated_at
            FROM supplier_aggregated
        ),
        -- Latest RRP from XML/1C
        latest_rrp AS (
            SELECT DISTINCT ON (vendor_code_norm, barcode)
                vendor_code_norm,
                barcode,
                rrp_price,
                rrp_stock,
                snapshot_at AS rrp_updated_at
            FROM rrp_snapshots
            WHERE vendor_code_norm IS NOT NULL
            ORDER BY vendor_code_norm, barcode, snapshot_at DESC
        ),
        -- Latest frontend prices (showcase price and SPP)
        latest_front AS (
            SELECT DISTINCT ON (nm_id)
                nm_id,
                price_product AS wb_showcase_price,
                discount_calc_percent AS wb_spp_discount,
                snapshot_at AS front_updated_at
            FROM frontend_catalog_price_snapshots
            WHERE nm_id IS NOT NULL
            ORDER BY nm_id, snapshot_at DESC
        ),
        -- Latest WB API prices (our discount)
        latest_wb_price AS (
            SELECT DISTINCT ON (nm_id)
                nm_id,
                wb_price,
                wb_discount AS wb_our_discount,
                created_at AS wb_price_updated_at
            FROM price_snapshots
            WHERE nm_id IS NOT NULL
            ORDER BY nm_id, created_at DESC
        ),
        -- Base: объединяем supplier stocks и RRP через UNION для правильного связывания
        -- Используем UNION вместо FULL OUTER JOIN, так как PostgreSQL не поддерживает FULL JOIN с OR условием
        base AS (
            -- Записи из supplier stocks
            SELECT DISTINCT
                s.nm_id::bigint AS nm_id,
                s.barcode::text AS barcode,
                -- vendor_code_norm priority: rrp > supplier_article_norm
                COALESCE(
                    r.vendor_code_norm,
                    s.supplier_article_norm
                )::text AS vendor_code_norm,
                s.supplier_qty_total::bigint AS supplier_qty_total,
                s.supplier_updated_at::timestamp with time zone AS supplier_updated_at
            FROM latest_supplier s
            LEFT JOIN latest_rrp r ON (
                r.barcode = s.barcode 
                OR r.vendor_code_norm = s.supplier_article_norm
            )
            UNION
            -- Записи из RRP, которых нет в supplier stocks
            SELECT DISTINCT
                NULL::bigint AS nm_id,
                r.barcode::text AS barcode,
                r.vendor_code_norm::text AS vendor_code_norm,
                NULL::bigint AS supplier_qty_total,
                NULL::timestamp with time zone AS supplier_updated_at
            FROM latest_rrp r
            WHERE NOT EXISTS (
                SELECT 1 FROM latest_supplier s 
                WHERE (s.barcode = r.barcode OR s.supplier_article_norm = r.vendor_code_norm)
            )
        )
        SELECT 
            base.vendor_code_norm AS "Артикул",
            COALESCE(base.nm_id, front.nm_id, wb_price.nm_id) AS "NMid",
            base.barcode AS "ШК",
            rrp.rrp_price AS "Наша цена (РРЦ)",
            front.wb_showcase_price AS "Цена на витрине",
            wb_price.wb_our_discount AS "Скидка наша",
            front.wb_spp_discount AS "СПП",
            base.supplier_qty_total AS "Остаток WB",
            rrp.rrp_stock AS "Остаток 1С",
            base.supplier_updated_at AS "Обновлено WB",
            rrp.rrp_updated_at AS "Обновлено 1С",
            front.front_updated_at AS "Обновлено фронт",
            wb_price.wb_price_updated_at AS "Обновлено WB API"
        FROM base
        LEFT JOIN latest_rrp rrp ON (
            rrp.barcode = base.barcode 
            OR rrp.vendor_code_norm = base.vendor_code_norm
        )
        LEFT JOIN latest_front front ON front.nm_id = base.nm_id
        LEFT JOIN latest_wb_price wb_price ON wb_price.nm_id = base.nm_id;
    """)


def downgrade() -> None:
    # Revert to previous version (will be handled by previous migration)
    pass
