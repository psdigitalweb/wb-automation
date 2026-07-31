"""Read-only discounts preview from wb_finance_report_lines.payload (sales only).

Does NOT touch sku_pnl_builder, wb_sku_pnl_snapshots, or event_mapping.
Only aggregates raw payload for AdminPrice, SellerDiscount, WBRealizedPrice analytics.

Model:
  retail_price = наша цена в админке
  sale_percent = наша скидка
  seller_final_price = retail_price * (1 - sale_percent/100)
  wb_realized_price = retail_amount / qty
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection


def get_discounts_preview(
    conn: Connection,
    project_id: int,
    period_from: date,
    period_to: date,
    internal_sku: Optional[str] = None,
    nm_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Get discounts preview aggregation from sales rows in wb_finance_report_lines.

    Reads raw payload only. No changes to wb_financial_events or wb_sku_pnl_snapshots.

    Args:
        conn: DB connection
        project_id: Project ID
        period_from: Period start
        period_to: Period end
        internal_sku: Filter by internal SKU (via products.vendor_code_norm)
        nm_id: Filter by nm_id (alternative to internal_sku)

    Returns:
        Dict with aggregates and sample_rows.
    """
    params: Dict[str, Any] = {
        "project_id": project_id,
        "period_from": period_from,
        "period_to": period_to,
    }
    if nm_id is not None:
        params["nm_id_filter"] = nm_id
        nm_filter_sql = "AND (COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$' AND (COALESCE(r.payload->>'nm_id', r.payload->>'nmId')::bigint) = :nm_id_filter)"
    elif internal_sku:
        params["internal_sku"] = internal_sku.strip()
        nm_filter_sql = """
        AND (COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$')
        AND (COALESCE(r.payload->>'nm_id', r.payload->>'nmId')::bigint) IN (
            SELECT nm_id FROM products
            WHERE project_id = :project_id
              AND nm_id IS NOT NULL
              AND (
                vendor_code_norm = :internal_sku
                OR vendor_code_norm LIKE '%/' || :internal_sku
                OR regexp_replace(trim(both '/' from vendor_code_norm), '^.*/', '') = :internal_sku
              )
        )
        """
    else:
        nm_filter_sql = "AND (COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$')"

    # Sales filter: supplier_oper_name='Продажа' (exclude returns)
    sales_filter = """
        AND COALESCE(r.payload->>'supplier_oper_name', r.payload->>'supplierOperName') = 'Продажа'
        AND COALESCE(r.payload->>'doc_type_name', r.payload->>'docTypeName') != 'Возврат'
    """

    agg_sql = text(f"""
        WITH sales_raw AS (
            SELECT
                r.report_id,
                r.line_id,
                COALESCE(
                    (r.payload->>'sale_dt')::date,
                    (r.payload->>'saleDt')::date,
                    (r.payload->>'rr_dt')::date,
                    rf.period_to
                ) AS sale_dt,
                GREATEST(
                    NULLIF((r.payload->>'quantity')::int, 0),
                    NULLIF((r.payload->>'qty')::int, 0),
                    1
                ) AS qty,
                (r.payload->>'retail_price')::numeric AS retail_price,
                (r.payload->>'retail_amount')::numeric AS retail_amount,
                COALESCE(
                    (r.payload->>'sale_percent')::numeric,
                    (r.payload->>'salePercent')::numeric,
                    0
                ) AS sale_percent
            FROM wb_finance_report_lines r
            JOIN wb_finance_reports rf ON rf.project_id = r.project_id
                AND rf.report_id = r.report_id
                AND rf.marketplace_code = 'wildberries'
            WHERE r.project_id = :project_id
              AND rf.period_from <= :period_to
              AND rf.period_to >= :period_from
              {nm_filter_sql}
              {sales_filter}
        )
        SELECT
            COALESCE(SUM(qty), 0)::bigint AS total_qty,
            COALESCE(SUM(retail_amount), 0)::numeric AS sum_retail_amount,
            SUM(retail_price * qty)::numeric AS sum_weighted_retail_price,
            SUM((retail_price * (1 - (sale_percent / 100))) * qty)::numeric AS sum_weighted_seller_final,
            SUM(sale_percent * qty)::numeric AS sum_weighted_sale_percent
        FROM sales_raw
    """)

    samples_sql = text(f"""
        WITH sales_raw AS (
            SELECT
                r.report_id,
                r.line_id,
                COALESCE(
                    (r.payload->>'sale_dt')::date,
                    (r.payload->>'saleDt')::date,
                    (r.payload->>'rr_dt')::date,
                    rf.period_to
                ) AS sale_dt,
                GREATEST(
                    NULLIF((r.payload->>'quantity')::int, 0),
                    NULLIF((r.payload->>'qty')::int, 0),
                    1
                ) AS qty,
                (r.payload->>'retail_price')::numeric AS retail_price,
                (r.payload->>'retail_amount')::numeric AS retail_amount,
                COALESCE(
                    (r.payload->>'sale_percent')::numeric,
                    (r.payload->>'salePercent')::numeric,
                    0
                ) AS sale_percent
            FROM wb_finance_report_lines r
            JOIN wb_finance_reports rf ON rf.project_id = r.project_id
                AND rf.report_id = r.report_id
                AND rf.marketplace_code = 'wildberries'
            WHERE r.project_id = :project_id
              AND rf.period_from <= :period_to
              AND rf.period_to >= :period_from
              {nm_filter_sql}
              {sales_filter}
        )
        SELECT report_id, line_id, sale_dt, qty, retail_price, sale_percent, retail_amount
        FROM sales_raw
        ORDER BY sale_dt DESC NULLS LAST, report_id, line_id
        LIMIT 10
    """)

    agg_row = conn.execute(agg_sql, params).mappings().first()
    sample_rows = conn.execute(samples_sql, params).mappings().all()

    if not agg_row or (agg_row.get("total_qty") or 0) == 0:
        return {
            "total_qty": 0,
            "admin_price_unit": None,
            "seller_discount_pct": None,
            "seller_final_price_unit": None,
            "wb_realized_price_unit": None,
            "wb_spp_discount_unit": None,
            "wb_spp_pct": None,
            "sample_rows": [dict(r) for r in sample_rows],
        }

    total_qty = int(agg_row["total_qty"] or 0)
    sum_retail_amount = Decimal(str(agg_row["sum_retail_amount"] or 0))
    sum_weighted_retail_price = Decimal(str(agg_row["sum_weighted_retail_price"] or 0))
    sum_weighted_seller_final = Decimal(str(agg_row["sum_weighted_seller_final"] or 0))
    sum_weighted_sale_percent = Decimal(str(agg_row["sum_weighted_sale_percent"] or 0))

    admin_price_unit = sum_weighted_retail_price / total_qty if total_qty else None
    seller_discount_pct = sum_weighted_sale_percent / total_qty if total_qty else None
    seller_final_price_unit = sum_weighted_seller_final / total_qty if total_qty else None
    wb_realized_price_unit = sum_retail_amount / total_qty if total_qty else None

    wb_spp_discount_unit = None
    wb_spp_pct = None
    if seller_final_price_unit is not None and seller_final_price_unit > 0:
        diff = seller_final_price_unit - (wb_realized_price_unit or Decimal(0))
        wb_spp_discount_unit = max(diff, Decimal(0))
        wb_spp_pct = float(wb_spp_discount_unit / seller_final_price_unit * 100) if seller_final_price_unit else None

    return {
        "total_qty": total_qty,
        "admin_price_unit": float(admin_price_unit) if admin_price_unit is not None else None,
        "seller_discount_pct": float(seller_discount_pct) if seller_discount_pct is not None else None,
        "seller_final_price_unit": float(seller_final_price_unit) if seller_final_price_unit is not None else None,
        "wb_realized_price_unit": float(wb_realized_price_unit) if wb_realized_price_unit is not None else None,
        "wb_spp_discount_unit": float(wb_spp_discount_unit) if wb_spp_discount_unit is not None else None,
        "wb_spp_pct": wb_spp_pct,
        "sample_rows": [
            {
                "report_id": int(r["report_id"]) if r.get("report_id") is not None else None,
                "line_id": int(r["line_id"]) if r.get("line_id") is not None else None,
                "sale_dt": r["sale_dt"].isoformat() if hasattr(r.get("sale_dt"), "isoformat") else str(r.get("sale_dt")),
                "qty": int(r["qty"]) if r.get("qty") is not None else None,
                "retail_price": float(r["retail_price"]) if r.get("retail_price") is not None else None,
                "sale_percent": float(r["sale_percent"]) if r.get("sale_percent") is not None else None,
                "retail_amount": float(r["retail_amount"]) if r.get("retail_amount") is not None else None,
            }
            for r in sample_rows
        ],
    }
