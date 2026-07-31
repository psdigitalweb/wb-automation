"""Read-only Unit PnL from wb_finance_report_lines.

Aggregates by nm_id. Scope: report_id OR rr_dt_from/rr_dt_to.
Sign applied only to retail_amount and ppvz_for_pay.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union

from sqlalchemy import text
from sqlalchemy.engine import Connection


@dataclass
class ReportScope:
    mode: str = "report"
    report_id: int = 0


@dataclass
class PeriodScope:
    mode: str = "period"
    rr_dt_from: Optional[date] = None
    rr_dt_to: Optional[date] = None


def prorate_amount_by_overlap(
    amount: object,
    entry_from: date,
    entry_to: date,
    scope_from: date,
    scope_to: date,
) -> Decimal:
    """Prorate an amount by inclusive day overlap."""
    amount_d = Decimal(str(amount or 0))
    if entry_to < entry_from:
        return Decimal("0")
    overlap_from = max(entry_from, scope_from)
    overlap_to = min(entry_to, scope_to)
    if overlap_to < overlap_from:
        return Decimal("0")
    overlap_days = (overlap_to - overlap_from).days + 1
    entry_days = (entry_to - entry_from).days + 1
    if entry_days <= 0:
        return Decimal("0")
    return amount_d * Decimal(overlap_days) / Decimal(entry_days)


def compute_extended_unit_metrics(
    *,
    fact_price_avg: object,
    wb_total_cost_per_unit: object,
    cogs_per_unit: object,
    packaging_cost_per_unit: object,
    additional_costs_per_unit: object,
    sales_cnt: object,
) -> Dict[str, Optional[float]]:
    """Compute full unit-economics metrics for Unit PnL."""
    from app.services.wb_financial.sku_pnl_metrics import _to_decimal

    avg = _to_decimal(fact_price_avg)
    wb_u = _to_decimal(wb_total_cost_per_unit)
    cogs = _to_decimal(cogs_per_unit)
    packaging = _to_decimal(packaging_cost_per_unit)
    additional = _to_decimal(additional_costs_per_unit) or Decimal("0")
    qty = int(sales_cnt or 0)

    full_profit_unit = None
    if avg is not None and wb_u is not None and cogs is not None and packaging is not None:
        full_profit_unit = avg - wb_u - cogs - packaging - additional

    full_margin = None
    if full_profit_unit is not None and avg is not None and avg != 0:
        full_margin = (full_profit_unit / avg) * Decimal("100")

    full_profit_total = None
    if full_profit_unit is not None and qty > 0:
        full_profit_total = full_profit_unit * Decimal(qty)

    return {
        "full_profit_per_unit": float(full_profit_unit) if full_profit_unit is not None else None,
        "full_profit_total": float(full_profit_total) if full_profit_total is not None else None,
        "full_margin_pct_of_revenue": float(full_margin) if full_margin is not None else None,
    }


def compute_wb_take_signed(
    *,
    commission_vv_signed: object = 0,
    acquiring: object = 0,
    logistics_cost: object = 0,
    storage_cost: object = 0,
    acceptance_cost: object = 0,
    other_withholdings: object = 0,
    penalties: object = 0,
) -> float:
    """Compute signed total WB take; negative rows reduce the total."""
    return float(
        Decimal(str(commission_vv_signed or 0))
        + Decimal(str(acquiring or 0))
        + Decimal(str(logistics_cost or 0))
        + Decimal(str(storage_cost or 0))
        + Decimal(str(acceptance_cost or 0))
        + Decimal(str(other_withholdings or 0))
        + Decimal(str(penalties or 0))
    )


def _compute_unit_pnl_tax_header(
    conn: Connection,
    project_id: int,
    *,
    transfer_for_goods: object,
    wb_total_signed: object,
    cogs_cost_total: object,
) -> Dict[str, Any]:
    row = conn.execute(
        text(
            """
            SELECT model_code, params_json
            FROM tax_profiles
            WHERE project_id = :project_id
            LIMIT 1
            """
        ),
        {"project_id": project_id},
    ).mappings().first()
    if not row:
        return {
            "tax_model_code": None,
            "tax_base": 0.0,
            "tax_vat_amount": 0.0,
            "tax_expense_total": 0.0,
        }

    model_code = str(row.get("model_code") or "")
    params = row.get("params_json") or {}
    if model_code != "wb_transfer_minus_vat_wb_cogs_tax":
        return {
            "tax_model_code": model_code,
            "tax_base": 0.0,
            "tax_vat_amount": 0.0,
            "tax_expense_total": 0.0,
        }

    vat_rate = Decimal(str(params.get("vat_rate", "0")))
    tax_rate = Decimal(str(params.get("tax_rate", "0")))
    transfer = Decimal(str(transfer_for_goods or 0))
    wb_take = Decimal(str(wb_total_signed or 0))
    cogs = Decimal(str(cogs_cost_total or 0))

    vat_amount = transfer * vat_rate
    tax_base = transfer - vat_amount - wb_take - cogs
    taxable_base = max(Decimal("0"), tax_base)
    profit_tax_amount = taxable_base * tax_rate

    return {
        "tax_model_code": model_code,
        "tax_base": float(tax_base),
        "tax_vat_amount": float(vat_amount),
        "tax_profit_amount": float(profit_tax_amount),
        "tax_expense_total": float(profit_tax_amount),
        "tax_rate": float(tax_rate),
        "tax_vat_rate": float(vat_rate),
    }


def _to_camel(snake: str) -> str:
    """Convert snake_case to camelCase."""
    parts = snake.split("_")
    return parts[0].lower() + "".join(p.title() for p in parts[1:])


def _coalesce_num(*keys: str) -> str:
    """Build COALESCE for payload keys (snake_case, camelCase)."""
    parts = []
    for k in keys:
        camel = _to_camel(k)
        expr = f"NULLIF(TRIM(COALESCE(r.payload->>'{k}', r.payload->>'{camel}')), '')::numeric"
        parts.append(expr)
    return f"COALESCE({', '.join(parts)}, 0)"


def _build_scope_filter(
    scope: Union[ReportScope, PeriodScope],
    params: Dict[str, Any],
    table_alias: str = "r",
) -> str:
    """Build WHERE fragment for scope. Mutates params."""
    if scope.mode == "report":
        params["report_id"] = scope.report_id
        return f"{table_alias}.project_id = :project_id AND {table_alias}.report_id = :report_id"
    else:
        params["rr_dt_from"] = scope.rr_dt_from
        params["rr_dt_to"] = scope.rr_dt_to
        return (
            f"{table_alias}.project_id = :project_id "
            f"AND (COALESCE({table_alias}.payload->>'rr_dt', {table_alias}.payload->>'rrDt'))::date "
            f"BETWEEN :rr_dt_from AND :rr_dt_to"
        )


def _build_from_clause(scope: Union[ReportScope, PeriodScope]) -> str:
    """For report mode join wb_finance_reports; for period mode only lines."""
    if scope.mode == "report":
        return """
            FROM wb_finance_report_lines r
            JOIN wb_finance_reports rf ON rf.project_id = r.project_id
                AND rf.report_id = r.report_id
                AND rf.marketplace_code = 'wildberries'
        """
    return "FROM wb_finance_report_lines r"


def get_wb_unit_pnl_table(
    conn: Connection,
    project_id: int,
    scope: Union[ReportScope, PeriodScope],
    limit: int = 50,
    offset: int = 0,
    sort: str = "total_to_pay",
    order: str = "desc",
    q: Optional[str] = None,
    subject_id: Optional[int] = None,
    filter_header: bool = False,
) -> Dict[str, Any]:
    """Get Unit PnL table aggregated by nm_id.

    Returns: rows_total, items[], header_totals, debug
    """
    params: Dict[str, Any] = {"project_id": project_id, "limit": limit, "offset": offset}
    scope_filter = _build_scope_filter(scope, params)
    from_clause = _build_from_clause(scope)

    scope_where = f"WHERE {scope_filter}"

    # Coalesce helpers
    v_retail = _coalesce_num("retail_amount")
    v_transfer = _coalesce_num("ppvz_for_pay")
    v_delivery = _coalesce_num("delivery_rub")
    v_storage = _coalesce_num("storage_fee")
    v_acceptance = _coalesce_num("acceptance")
    v_deduction = _coalesce_num("deduction")
    v_penalty = _coalesce_num("penalty")
    v_cashback = _coalesce_num("cashback_discount")
    v_ppvz_vw = _coalesce_num("ppvz_vw")
    v_ppvz_vw_nds = _coalesce_num("ppvz_vw_nds")
    v_acquiring = _coalesce_num("acquiring_fee")

    sign_expr = """CASE
        WHEN COALESCE(r.payload->>'doc_type_name', r.payload->>'docTypeName') ILIKE '%возврат%'
          OR COALESCE(r.payload->>'supplier_oper_name', r.payload->>'supplierOperName') ILIKE '%возврат%'
        THEN -1
        ELSE 1
    END"""

    # retail_price, ppvz_spp_prc - nullable
    v_retail_price = "NULLIF(TRIM(COALESCE(r.payload->>'retail_price', r.payload->>'retailPrice')), '')::numeric"
    v_ppvz_spp_prc = "NULLIF(TRIM(COALESCE(r.payload->>'ppvz_spp_prc', r.payload->>'ppvzSppPrc')), '')::numeric"

    # delivery_amount, return_amount - for logistics qty fallback
    v_delivery_amount = "NULLIF(TRIM(COALESCE(r.payload->>'delivery_amount', r.payload->>'deliveryAmount')), '')::numeric"
    v_return_amount = "NULLIF(TRIM(COALESCE(r.payload->>'return_amount', r.payload->>'returnAmount')), '')::numeric"

    # bonus_type_name for fallback
    bonus_type_expr = "COALESCE(r.payload->>'bonus_type_name', r.payload->>'bonusTypeName')"
    is_logistics_expr = """(
        COALESCE(r.payload->>'supplier_oper_name', r.payload->>'supplierOperName') = 'Логистика'
        OR COALESCE(r.payload->>'supplier_oper_name', r.payload->>'supplierOperName') ILIKE '%логистик%'
    )"""
    is_delivery_bonus = f"({bonus_type_expr} LIKE 'К клиенту%')"
    is_return_bonus = f"""(
        {bonus_type_expr} LIKE 'От клиента%'
        OR {bonus_type_expr} LIKE 'Возврат % (К продавцу)%'
        OR {bonus_type_expr} IN ('Возврат брака (К продавцу)', 'Возврат неопознанного товара (К продавцу)')
    )"""

    # Search filter
    search_sql = ""
    if q and q.strip():
        q_clean = q.strip()
        params["q_pattern"] = f"%{q_clean}%"
        search_sql = """
            AND (
                p.title ILIKE :q_pattern
                OR p.vendor_code ILIKE :q_pattern
                OR p.vendor_code_norm ILIKE :q_pattern
                OR sc.nm_id::text = :q_exact
            )
        """
        params["q_exact"] = q_clean

    # Category (WB subject) filter
    category_sql = ""
    if subject_id is not None:
        params["subject_id"] = subject_id
        category_sql = " AND p.subject_id = :subject_id"

    # Whitelist: frontend sort key -> SQL expression (must exist in SELECT or be valid in ORDER BY context)
    # sold_units = net_sales_cnt (Продано, шт)
    # wb_pct_of_sale = (wb_total_cost_per_unit / fact_price_avg) * 100
    # margin_pct_of_revenue = proxy: (fact_price_avg - wb_total_cost_per_unit) / fact_price_avg * 100 (before COGS)
    sort_cols = {
        "sale_amount": "sale_amount",
        "transfer_amount": "transfer_amount",
        "total_to_pay": "total_to_pay",
        "net_sales_cnt": "net_sales_cnt",
        "sold_units": "net_sales_cnt",  # alias for Продано, шт
        "nm_id": "nm_id",
        "wb_total_cost_per_unit": "wb_total_cost_per_unit",
        "margin_pct_of_revenue": (
            "CASE WHEN sc.fact_price_avg > 0 AND sc.sales_cnt > 0 "
            "THEN ((sc.fact_price_avg - (sc.wb_total_signed / sc.sales_cnt)) / sc.fact_price_avg) * 100 "
            "ELSE NULL END"
        ),
        "wb_pct_of_sale": (
            "CASE WHEN sc.fact_price_avg > 0 AND sc.sales_cnt > 0 "
            "THEN ((sc.wb_total_signed / sc.sales_cnt) / sc.fact_price_avg) * 100 "
            "ELSE NULL END"
        ),
    }
    sort_col = sort_cols.get(sort, "total_to_pay")
    dir_sql = "DESC" if order.lower() == "desc" else "ASC"
    order_clause = f"ORDER BY {sort_col} {dir_sql} NULLS LAST, nm_id ASC"

    sql = text(f"""
        WITH base_lines AS (
            SELECT
                r.project_id,
                r.report_id,
                r.line_id,
                CASE WHEN COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$'
                    THEN (COALESCE(r.payload->>'nm_id', r.payload->>'nmId')::bigint)
                    ELSE NULL
                END AS nm_id,
                ({sign_expr})::int AS sign_val,
                CASE WHEN ({sign_expr}) = -1 THEN true ELSE false END AS is_return,
                {v_retail} AS retail_amount,
                {v_transfer} AS ppvz_for_pay,
                {v_delivery} AS delivery_rub,
                {v_storage} AS storage_fee,
                {v_acceptance} AS acceptance,
                {v_deduction} AS deduction,
                {v_penalty} AS penalty,
                {v_cashback} AS cashback_discount,
                {v_ppvz_vw} AS ppvz_vw,
                {v_ppvz_vw_nds} AS ppvz_vw_nds,
                {v_acquiring} AS acquiring_fee,
                {v_retail_price} AS retail_price,
                {v_ppvz_spp_prc} AS ppvz_spp_prc,
                {v_delivery_amount} AS delivery_amount,
                {v_return_amount} AS return_amount,
                {is_logistics_expr} AS is_logistics,
                {is_delivery_bonus} AS is_delivery_bonus,
                {is_return_bonus} AS is_return_bonus
            {from_clause}
            {scope_where}
              AND (COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$')
        ),
        sku_agg AS (
            SELECT
                nm_id,
                SUM(sign_val * retail_amount) AS sale_amount,
                SUM(sign_val * ppvz_for_pay) AS transfer_amount,
                SUM(COALESCE(ppvz_vw, 0) + COALESCE(ppvz_vw_nds, 0)) AS commission_vv_signed,
                SUM(COALESCE(acquiring_fee, 0)) AS acquiring,
                SUM(delivery_rub) AS logistics_cost,
                SUM(storage_fee) AS storage_cost,
                SUM(acceptance) AS acceptance_cost,
                SUM(deduction) AS other_withholdings,
                SUM(penalty) AS penalties,
                SUM(cashback_discount) AS loyalty_comp_display,
                COUNT(*) FILTER (WHERE retail_amount > 0) AS sales_cnt,
                COUNT(*) FILTER (WHERE is_return AND retail_amount != 0) AS returns_cnt,
                AVG(retail_price) FILTER (WHERE retail_price IS NOT NULL AND retail_price > 0) AS wb_price_avg,
                AVG(ppvz_spp_prc) FILTER (WHERE ppvz_spp_prc IS NOT NULL AND ppvz_spp_prc > 0) AS spp_avg,
                AVG(sign_val * retail_amount) FILTER (WHERE retail_amount IS NOT NULL AND retail_amount != 0) AS fact_price_avg,
                COUNT(*) FILTER (WHERE retail_price IS NOT NULL AND retail_price > 0) AS retail_price_nonzero_rows,
                COUNT(*) FILTER (WHERE ppvz_spp_prc IS NOT NULL AND ppvz_spp_prc > 0) AS spp_nonzero_rows,
                COUNT(*) FILTER (WHERE retail_amount IS NOT NULL AND retail_amount != 0) AS retail_amount_nonzero_rows,
                CASE WHEN COUNT(delivery_amount) FILTER (WHERE is_logistics) > 0
                    THEN SUM(delivery_amount) FILTER (WHERE is_logistics)
                    ELSE (COUNT(*) FILTER (WHERE is_logistics AND is_delivery_bonus))::numeric
                END AS deliveries_qty,
                CASE WHEN COUNT(return_amount) FILTER (WHERE is_logistics) > 0
                    THEN SUM(return_amount) FILTER (WHERE is_logistics)
                    ELSE (COUNT(*) FILTER (WHERE is_logistics AND is_return_bonus))::numeric
                END AS returns_log_qty
            FROM base_lines
            WHERE nm_id IS NOT NULL
            GROUP BY nm_id
        ),
        allocation_totals AS (
            SELECT
                COALESCE(SUM(
                    COALESCE(commission_vv_signed, 0)
                    + COALESCE(acquiring, 0)
                    + logistics_cost
                    + storage_cost
                    + acceptance_cost
                    + other_withholdings
                    + penalties
                ) FILTER (WHERE nm_id = 0), 0) AS common_wb_total,
                COALESCE(SUM(GREATEST(sale_amount, 0)) FILTER (WHERE nm_id <> 0), 0) AS positive_sale_total
            FROM sku_agg
        ),
        sku_computed AS (
            SELECT
                sa.*,
                (sales_cnt - returns_cnt)::int AS net_sales_cnt,
                (
                    COALESCE(commission_vv_signed, 0)
                    + COALESCE(acquiring, 0)
                    + logistics_cost
                    + storage_cost
                    + acceptance_cost
                    + other_withholdings
                    + penalties
                ) AS wb_own_total_signed,
                CASE
                    WHEN sa.nm_id <> 0
                      AND at.positive_sale_total > 0
                      AND GREATEST(sa.sale_amount, 0) > 0
                    THEN at.common_wb_total * GREATEST(sa.sale_amount, 0) / at.positive_sale_total
                    ELSE 0
                END AS wb_common_allocated_total,
                (
                    transfer_amount
                    - logistics_cost
                    - storage_cost
                    - acceptance_cost
                    - other_withholdings
                    - penalties
                    - CASE
                        WHEN sa.nm_id <> 0
                          AND at.positive_sale_total > 0
                          AND GREATEST(sa.sale_amount, 0) > 0
                        THEN at.common_wb_total * GREATEST(sa.sale_amount, 0) / at.positive_sale_total
                        ELSE 0
                      END
                ) AS total_to_pay,
                (
                    COALESCE(commission_vv_signed, 0)
                    + COALESCE(acquiring, 0)
                    + logistics_cost
                    + storage_cost
                    + acceptance_cost
                    + other_withholdings
                    + penalties
                    + CASE
                        WHEN sa.nm_id <> 0
                          AND at.positive_sale_total > 0
                          AND GREATEST(sa.sale_amount, 0) > 0
                        THEN at.common_wb_total * GREATEST(sa.sale_amount, 0) / at.positive_sale_total
                        ELSE 0
                      END
                ) AS wb_total_signed,
                (logistics_cost + storage_cost + acceptance_cost + other_withholdings + penalties) AS wb_total_cost,
                CASE WHEN COALESCE(deliveries_qty, 0) > 0
                    THEN (deliveries_qty - COALESCE(returns_log_qty, 0)) / NULLIF(deliveries_qty, 0)
                    ELSE NULL
                END AS buyout_rate
            FROM sku_agg sa
            CROSS JOIN allocation_totals at
        ),
        header_totals AS (
            SELECT
                COUNT(*)::bigint AS rows_total,
                SUM(sign_val * retail_amount) AS sum_sale_signed,
                SUM(retail_amount) AS sum_retail_raw,
                SUM(sign_val * ppvz_for_pay) AS sum_transfer_signed,
                SUM(ppvz_for_pay) AS sum_transfer_raw,
                SUM(CASE WHEN deduction > 0 THEN deduction ELSE 0 END) AS deduction_pos_sum,
                SUM(CASE WHEN deduction < 0 THEN deduction ELSE 0 END) AS deduction_neg_sum,
                SUM(CASE WHEN penalty > 0 THEN penalty ELSE 0 END) AS penalty_pos_sum,
                SUM(CASE WHEN penalty < 0 THEN penalty ELSE 0 END) AS penalty_neg_sum
            FROM base_lines
        )
        SELECT
            sc.nm_id,
            sc.sale_amount,
            sc.transfer_amount,
            sc.logistics_cost,
            sc.storage_cost,
            sc.acceptance_cost,
            sc.other_withholdings,
            sc.penalties,
            sc.loyalty_comp_display,
            sc.total_to_pay,
            sc.sales_cnt,
            sc.returns_cnt,
            sc.net_sales_cnt,
            sc.deliveries_qty,
            sc.returns_log_qty,
            sc.buyout_rate,
            sc.wb_price_avg,
            sc.spp_avg,
            sc.fact_price_avg,
            sc.retail_price_nonzero_rows,
            sc.spp_nonzero_rows,
            sc.retail_amount_nonzero_rows,
            sc.commission_vv_signed,
            sc.acquiring,
            sc.wb_own_total_signed,
            sc.wb_common_allocated_total,
            sc.wb_total_signed,
            CASE WHEN sc.sales_cnt > 0
                THEN sc.wb_total_signed / sc.sales_cnt
                ELSE NULL
            END AS wb_total_cost_per_unit,
            p.title,
            p.pics,
            p.vendor_code,
            p.vendor_code_norm,
            ht.rows_total,
            ht.sum_retail_raw,
            ht.sum_sale_signed,
            ht.sum_transfer_raw,
            ht.sum_transfer_signed,
            ht.deduction_pos_sum,
            ht.deduction_neg_sum,
            ht.penalty_pos_sum,
            ht.penalty_neg_sum
        FROM sku_computed sc
        LEFT JOIN v_wb_product_source p ON p.project_id = :project_id AND p.nm_id = sc.nm_id
        CROSS JOIN header_totals ht
        WHERE sc.nm_id <> 0
        {search_sql}
        {category_sql}
        {order_clause}
        LIMIT :limit OFFSET :offset
    """)

    # Count: join products when search or category filter is used
    if subject_id is not None and q and q.strip():
        count_from = f"""
            sku_agg AS (
                SELECT nm_id FROM base_lines WHERE nm_id IS NOT NULL AND nm_id <> 0 GROUP BY nm_id
            ),
            with_filter AS (
                SELECT sa.nm_id
                FROM sku_agg sa
                INNER JOIN v_wb_product_source p ON p.project_id = :project_id AND p.nm_id = sa.nm_id AND p.subject_id = :subject_id
                WHERE (p.title ILIKE :q_pattern
                   OR p.vendor_code ILIKE :q_pattern
                   OR p.vendor_code_norm ILIKE :q_pattern
                   OR sa.nm_id::text = :q_exact)
            )
            SELECT COUNT(*) AS cnt FROM with_filter"""
    elif subject_id is not None:
        count_from = f"""
            sku_agg AS (
                SELECT nm_id FROM base_lines WHERE nm_id IS NOT NULL AND nm_id <> 0 GROUP BY nm_id
            ),
            with_filter AS (
                SELECT sa.nm_id
                FROM sku_agg sa
                INNER JOIN v_wb_product_source p ON p.project_id = :project_id AND p.nm_id = sa.nm_id AND p.subject_id = :subject_id
            )
            SELECT COUNT(*) AS cnt FROM with_filter"""
    elif q and q.strip():
        count_from = f"""
            sku_agg AS (
                SELECT nm_id FROM base_lines WHERE nm_id IS NOT NULL AND nm_id <> 0 GROUP BY nm_id
            ),
            with_filter AS (
                SELECT sa.nm_id
                FROM sku_agg sa
                LEFT JOIN v_wb_product_source p ON p.project_id = :project_id AND p.nm_id = sa.nm_id
                WHERE p.title ILIKE :q_pattern
                   OR p.vendor_code ILIKE :q_pattern
                   OR p.vendor_code_norm ILIKE :q_pattern
                   OR sa.nm_id::text = :q_exact
            )
            SELECT COUNT(*) AS cnt FROM with_filter"""
    else:
        count_from = """
            sku_agg AS (
                SELECT nm_id FROM base_lines WHERE nm_id IS NOT NULL AND nm_id <> 0 GROUP BY nm_id
            )
            SELECT COUNT(*) AS cnt FROM sku_agg"""

    # scope_lines_total: always count of ALL report lines in scope (no filters)
    scope_lines_sql = text(f"""
        SELECT COUNT(*)::bigint AS lines_total
        {from_clause}
        {scope_where}
    """)
    scope_lines_row = conn.execute(scope_lines_sql, params).mappings().first()
    scope_lines_total = int(scope_lines_row["lines_total"] or 0) if scope_lines_row else 0

    count_sql = text(f"""
        WITH base_lines AS (
            SELECT
                CASE WHEN COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$'
                    THEN (COALESCE(r.payload->>'nm_id', r.payload->>'nmId')::bigint)
                    ELSE NULL
                END AS nm_id
            {from_clause}
            {scope_where}
              AND (COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$')
        ),
        {count_from}
    """)

    rows = conn.execute(sql, params).mappings().all()
    count_row = conn.execute(count_sql, params).mappings().first()
    total_count = int(count_row["cnt"] or 0) if count_row else 0

    if not rows:
        header = {
            "lines_total": scope_lines_total,
            "scope_lines_total": scope_lines_total,
            "skus_total": total_count,
            "rows_total": total_count,
            "filter_header": filter_header,
            "sale": 0.0,
            "transfer_for_goods": 0.0,
            "logistics_cost": 0.0,
            "storage_cost": 0.0,
            "acceptance_cost": 0.0,
            "other_withholdings": 0.0,
            "penalties": 0.0,
            "loyalty_comp_display": 0.0,
            "commission_vv_signed": 0.0,
            "acquiring": 0.0,
            "wb_total_signed": 0.0,
            "wb_total_pct_of_revenue": 0.0,
            "total_to_pay": 0.0,
            "rrp_model": None,
            "packaging_cost_total": 0.0,
            "cogs_cost_total": 0.0,
            "packaging_missing_count": 0,
            "additional_costs_total": 0.0,
            "marketplace_additional_costs_total": 0.0,
            "full_profit_total": None,
            "full_margin_pct_of_revenue": None,
        }
        debug = {
            "sum_retail_raw": 0.0,
            "sum_sale_signed": 0.0,
            "sum_transfer_raw": 0.0,
            "sum_transfer_signed": 0.0,
            "deduction_pos_sum": 0.0,
            "deduction_neg_sum": 0.0,
            "penalty_pos_sum": 0.0,
            "penalty_neg_sum": 0.0,
        }
        return {
            "scope": _scope_to_dict(scope),
            "rows_total": 0,
            "items": [],
            "header_totals": header,
            "debug": debug,
        }

    first = rows[0]
    header_totals = {
        "rows_total": int(first.get("rows_total") or 0),
        "sale": float(first.get("sum_sale_signed") or 0),
        "transfer_for_goods": float(first.get("sum_transfer_signed") or 0),
        "logistics_cost": 0.0,  # From first row - need to aggregate separately
        "storage_cost": 0.0,
        "acceptance_cost": 0.0,
        "other_withholdings": 0.0,
        "penalties": 0.0,
        "loyalty_comp_display": 0.0,
        "commission_vv_signed": 0.0,
        "acquiring": 0.0,
        "wb_total_signed": 0.0,
        "wb_total_pct_of_revenue": 0.0,
        "total_to_pay": 0.0,
    }
    # Header: when filter_header=True, restrict to nm_ids matching q+category
    use_filtered_header = filter_header and (q and q.strip() or subject_id is not None)
    header_nm_filter = ""
    header_from = "FROM base_lines"
    base_lines_close = ")"  # default: close base_lines CTE
    if use_filtered_header:
        header_search_sql = (
            " AND (p.title ILIKE :q_pattern OR p.vendor_code ILIKE :q_pattern "
            "OR p.vendor_code_norm ILIKE :q_pattern OR sa.nm_id::text = :q_exact)"
            if (q and q.strip())
            else ""
        )
        base_lines_close = ")"  # close base_lines
        header_nm_filter = f""",
        sku_agg_h AS (
            SELECT nm_id FROM base_lines WHERE nm_id IS NOT NULL GROUP BY nm_id
        ),
        filtered_nm_ids_h AS (
            SELECT sa.nm_id
            FROM sku_agg_h sa
            LEFT JOIN v_wb_product_source p ON p.project_id = :project_id AND p.nm_id = sa.nm_id
            WHERE 1=1
            {category_sql}
            {header_search_sql}
        )
        """
        header_from = "FROM base_lines bl WHERE bl.nm_id IN (SELECT nm_id FROM filtered_nm_ids_h)"

    header_sql = text(f"""
        WITH base_lines AS (
            SELECT
                CASE WHEN COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$'
                    THEN (COALESCE(r.payload->>'nm_id', r.payload->>'nmId')::bigint)
                    ELSE NULL
                END AS nm_id,
                ({sign_expr})::int AS sign_val,
                {v_retail} AS retail_amount,
                {v_transfer} AS ppvz_for_pay,
                {v_delivery} AS delivery_rub,
                {v_storage} AS storage_fee,
                {v_acceptance} AS acceptance,
                {v_deduction} AS deduction,
                {v_penalty} AS penalty,
                {v_cashback} AS cashback_discount,
                {v_ppvz_vw} AS ppvz_vw,
                {v_ppvz_vw_nds} AS ppvz_vw_nds,
                {v_acquiring} AS acquiring_fee
            {from_clause}
            {scope_where}
              AND (COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$')
        {base_lines_close}
        {header_nm_filter}
        SELECT
            COUNT(*)::bigint AS rows_total,
            SUM(sign_val * retail_amount) AS sum_sale_signed,
            SUM(retail_amount) AS sum_retail_raw,
            SUM(sign_val * ppvz_for_pay) AS sum_transfer_signed,
            SUM(ppvz_for_pay) AS sum_transfer_raw,
            SUM(delivery_rub) AS logistics_cost,
            SUM(storage_fee) AS storage_cost,
            SUM(acceptance) AS acceptance_cost,
            SUM(deduction) AS other_withholdings,
            SUM(penalty) AS penalties,
            SUM(cashback_discount) AS loyalty_comp_display,
            SUM(COALESCE(ppvz_vw, 0) + COALESCE(ppvz_vw_nds, 0)) AS commission_vv_signed,
            SUM(COALESCE(acquiring_fee, 0)) AS acquiring,
            SUM(CASE WHEN deduction > 0 THEN deduction ELSE 0 END) AS deduction_pos_sum,
            SUM(CASE WHEN deduction < 0 THEN deduction ELSE 0 END) AS deduction_neg_sum,
            SUM(CASE WHEN penalty > 0 THEN penalty ELSE 0 END) AS penalty_pos_sum,
            SUM(CASE WHEN penalty < 0 THEN penalty ELSE 0 END) AS penalty_neg_sum
        {header_from}
    """)
    header_row = conn.execute(header_sql, params).mappings().first()
    if header_row:
        transfer = float(header_row.get("sum_transfer_signed") or 0)
        logistics = float(header_row.get("logistics_cost") or 0)
        storage = float(header_row.get("storage_cost") or 0)
        acceptance = float(header_row.get("acceptance_cost") or 0)
        other = float(header_row.get("other_withholdings") or 0)
        penalties = float(header_row.get("penalties") or 0)
        commission_vv_signed = float(header_row.get("commission_vv_signed") or 0)
        acquiring = float(header_row.get("acquiring") or 0)
        wb_total_signed = compute_wb_take_signed(
            commission_vv_signed=commission_vv_signed,
            acquiring=acquiring,
            logistics_cost=logistics,
            storage_cost=storage,
            acceptance_cost=acceptance,
            other_withholdings=other,
            penalties=penalties,
        )
        sale = float(header_row.get("sum_sale_signed") or 0)
        header_totals = {
            "rows_total": int(header_row.get("rows_total") or 0),
            "sale": sale,
            "transfer_for_goods": transfer,
            "logistics_cost": logistics,
            "storage_cost": storage,
            "acceptance_cost": acceptance,
            "other_withholdings": other,
            "penalties": float(header_row.get("penalties") or 0),
            "loyalty_comp_display": float(header_row.get("loyalty_comp_display") or 0),
            "commission_vv_signed": commission_vv_signed,
            "acquiring": acquiring,
            "wb_total_signed": wb_total_signed,
            "wb_total_pct_of_revenue": (wb_total_signed / sale) * 100 if sale > 0 else None,
            "total_to_pay": transfer - logistics - storage - acceptance - other - penalties,
        }

    debug = {
        "sum_retail_raw": float(header_row.get("sum_retail_raw") or 0) if header_row else 0,
        "sum_sale_signed": float(header_row.get("sum_sale_signed") or 0) if header_row else 0,
        "sum_transfer_raw": float(header_row.get("sum_transfer_raw") or 0) if header_row else 0,
        "sum_transfer_signed": float(header_row.get("sum_transfer_signed") or 0) if header_row else 0,
        "deduction_pos_sum": float(header_row.get("deduction_pos_sum") or 0) if header_row else 0,
        "deduction_neg_sum": float(header_row.get("deduction_neg_sum") or 0) if header_row else 0,
        "penalty_pos_sum": float(header_row.get("penalty_pos_sum") or 0) if header_row else 0,
        "penalty_neg_sum": float(header_row.get("penalty_neg_sum") or 0) if header_row else 0,
        "retail_price_nonzero_rows": sum(int(r.get("retail_price_nonzero_rows") or 0) for r in rows),
        "spp_nonzero_rows": sum(int(r.get("spp_nonzero_rows") or 0) for r in rows),
        "retail_amount_nonzero_rows": sum(int(r.get("retail_amount_nonzero_rows") or 0) for r in rows),
    }

    def _row_to_item(r: Any) -> Dict[str, Any]:
        d = dict(r)
        photos = []
        pics_val = d.get("pics")
        if pics_val:
            if isinstance(pics_val, str):
                import json
                try:
                    pics_val = json.loads(pics_val)
                except Exception:
                    pics_val = None
            if isinstance(pics_val, list):
                for pic in pics_val:
                    if isinstance(pic, dict):
                        url = pic.get("url") or pic.get("big") or pic.get("c128")
                        if url:
                            photos.append(str(url))
                    elif isinstance(pic, str):
                        photos.append(pic)
        return {
            "nm_id": int(d["nm_id"]),
            "vendor_code": d.get("vendor_code"),
            "title": d.get("title"),
            "photos": photos,
            "sale_amount": float(d.get("sale_amount") or 0),
            "transfer_amount": float(d.get("transfer_amount") or 0),
            "logistics_cost": float(d.get("logistics_cost") or 0),
            "storage_cost": float(d.get("storage_cost") or 0),
            "acceptance_cost": float(d.get("acceptance_cost") or 0),
            "other_withholdings": float(d.get("other_withholdings") or 0),
            "penalties": float(d.get("penalties") or 0),
            "loyalty_comp_display": float(d.get("loyalty_comp_display") or 0),
            "total_to_pay": float(d.get("total_to_pay") or 0),
            "sales_cnt": int(d.get("sales_cnt") or 0),
            "returns_cnt": int(d.get("returns_cnt") or 0),
            "net_sales_cnt": int(d.get("net_sales_cnt") or 0),
            "deliveries_qty": int(d["deliveries_qty"]) if d.get("deliveries_qty") is not None else None,
            "returns_log_qty": int(d["returns_log_qty"]) if d.get("returns_log_qty") is not None else None,
            "buyout_rate": float(d["buyout_rate"]) if d.get("buyout_rate") is not None else None,
            "wb_price_avg": float(d["wb_price_avg"]) if d.get("wb_price_avg") is not None else None,
            "spp_avg": float(d["spp_avg"]) if d.get("spp_avg") is not None else None,
            "fact_price_avg": float(d["fact_price_avg"]) if d.get("fact_price_avg") is not None else None,
            "commission_vv_signed": float(d["commission_vv_signed"]) if d.get("commission_vv_signed") is not None else None,
            "acquiring": float(d["acquiring"]) if d.get("acquiring") is not None else None,
            "wb_own_total_signed": float(d["wb_own_total_signed"]) if d.get("wb_own_total_signed") is not None else None,
            "wb_common_allocated_total": (
                float(d["wb_common_allocated_total"]) if d.get("wb_common_allocated_total") is not None else None
            ),
            "wb_common_allocated_per_unit": (
                float(d["wb_common_allocated_total"]) / int(d.get("sales_cnt") or 0)
                if d.get("wb_common_allocated_total") is not None and int(d.get("sales_cnt") or 0) > 0
                else None
            ),
            "wb_total_signed": float(d["wb_total_signed"]) if d.get("wb_total_signed") is not None else None,
            "wb_total_cost_per_unit": float(d["wb_total_cost_per_unit"]) if d.get("wb_total_cost_per_unit") is not None else None,
            "vendor_code_norm": d.get("vendor_code_norm"),
        }

    items = [_row_to_item(r) for r in rows]
    as_of = _resolve_as_of_date(conn, project_id, scope)
    scope_from, scope_to = _resolve_scope_dates(conn, project_id, scope)
    items = enrich_with_rrp_and_cogs(conn, project_id, items, as_of)

    # RRP model: when filter_header=0 use scope only; when filter_header=1 use q+category
    rrp_q = q if filter_header else None
    rrp_subject_id = subject_id if filter_header else None
    rrp_model = _compute_rrp_model_header(
        conn, project_id, scope, as_of, params,
        from_clause, scope_where, sign_expr,
        v_retail, v_transfer, v_delivery, v_storage, v_acceptance, v_deduction, v_penalty, v_cashback,
        v_ppvz_vw, v_ppvz_vw_nds, v_acquiring,
        search_sql, category_sql, rrp_q, rrp_subject_id,
    )

    extended_basis = _load_extended_header_basis(
        conn,
        project_id,
        params,
        from_clause,
        scope_where,
        sign_expr,
        v_retail,
        v_transfer,
        v_delivery,
        v_storage,
        v_acceptance,
        v_deduction,
        v_penalty,
        v_ppvz_vw,
        v_ppvz_vw_nds,
        v_acquiring,
        v_retail_price,
        v_ppvz_spp_prc,
        rrp_q,
        rrp_subject_id,
    )
    extended_basis = enrich_with_rrp_and_cogs(conn, project_id, extended_basis, as_of)
    marketplace_sale_total = sum(max(float(r.get("sale_amount") or 0), 0.0) for r in extended_basis)
    extended_header = apply_extended_costs(
        conn,
        project_id,
        extended_basis,
        scope_from=scope_from,
        scope_to=scope_to,
        as_of_date=as_of,
        marketplace_sale_total=marketplace_sale_total,
    )
    apply_extended_costs(
        conn,
        project_id,
        items,
        scope_from=scope_from,
        scope_to=scope_to,
        as_of_date=as_of,
        marketplace_sale_total=marketplace_sale_total,
    )

    lines_total = (
        int(header_row.get("rows_total") or 0) if use_filtered_header and header_row else scope_lines_total
    )
    header_totals["lines_total"] = lines_total
    header_totals["scope_lines_total"] = scope_lines_total
    header_totals["skus_total"] = total_count
    header_totals["filter_header"] = filter_header
    header_totals["rows_total"] = total_count
    header_totals["rrp_model"] = rrp_model
    # Keep legacy flat keys for backward compat; frontend will use rrp_model
    header_totals["rrp_sales_model"] = rrp_model.get("rrp_sales_model")
    header_totals["wb_take_from_rrp"] = rrp_model.get("wb_took_from_rrp_rub")
    header_totals["wb_take_pct_of_rrp"] = rrp_model.get("wb_took_from_rrp_pct")
    header_totals["rrp_coverage_pct"] = rrp_model.get("rrp_coverage_qty_pct")
    header_totals["packaging_cost_total"] = extended_header.get("packaging_cost_total")
    header_totals["cogs_cost_total"] = extended_header.get("cogs_cost_total")
    header_totals["packaging_missing_count"] = extended_header.get("packaging_missing_count")
    header_totals["additional_costs_total"] = extended_header.get("additional_costs_total")
    header_totals["marketplace_additional_costs_total"] = extended_header.get("marketplace_additional_costs_total")
    header_totals["warehouse_labor_costs_total"] = extended_header.get("warehouse_labor_costs_total")
    tax_header = _compute_unit_pnl_tax_header(
        conn,
        project_id,
        transfer_for_goods=header_totals.get("transfer_for_goods"),
        wb_total_signed=header_totals.get("wb_total_signed"),
        cogs_cost_total=extended_header.get("cogs_cost_total"),
    )
    full_profit_before_tax = extended_header.get("full_profit_total")
    tax_expense_total = float(tax_header.get("tax_expense_total") or 0)
    full_profit_after_tax = (
        float(full_profit_before_tax) - tax_expense_total
        if full_profit_before_tax is not None
        else None
    )
    sale_for_margin = float(header_totals.get("sale") or 0)
    header_totals["tax_model_code"] = tax_header.get("tax_model_code")
    header_totals["tax_base"] = tax_header.get("tax_base")
    header_totals["tax_vat_amount"] = tax_header.get("tax_vat_amount")
    header_totals["tax_profit_amount"] = tax_header.get("tax_profit_amount")
    header_totals["tax_expense_total"] = tax_expense_total
    header_totals["tax_rate"] = tax_header.get("tax_rate")
    header_totals["tax_vat_rate"] = tax_header.get("tax_vat_rate")
    header_totals["full_profit_before_tax_total"] = full_profit_before_tax
    header_totals["full_profit_total"] = full_profit_after_tax
    header_totals["full_margin_pct_of_revenue"] = (
        (full_profit_after_tax / sale_for_margin) * 100
        if full_profit_after_tax is not None and sale_for_margin > 0
        else None
    )

    return {
        "scope": _scope_to_dict(scope),
        "rows_total": total_count,
        "items": items,
        "header_totals": header_totals,
        "debug": debug,
    }


def _compute_rrp_model_header(
    conn: Connection,
    project_id: int,
    scope: Union[ReportScope, PeriodScope],
    as_of_date: date,
    params: Dict[str, Any],
    from_clause: str,
    scope_where: str,
    sign_expr: str,
    v_retail: str,
    v_transfer: str,
    v_delivery: str,
    v_storage: str,
    v_acceptance: str,
    v_deduction: str,
    v_penalty: str,
    v_cashback: str,
    v_ppvz_vw: str,
    v_ppvz_vw_nds: str,
    v_acquiring: str,
    search_sql: str,
    category_sql: str,
    q: Optional[str],
    subject_id: Optional[int],
) -> Dict[str, Optional[float]]:
    """Compute RRP model header from ALL filtered SKUs (not current page). Uses sales_cnt = net_sales_cnt."""
    # Build filtered sku query: nm_id, net_sales_cnt, total_to_pay, vendor_code_norm
    filtered_sku_from = ""
    filtered_sku_where = ""
    if subject_id is not None and q and q.strip():
        filtered_sku_from = """FROM sku_computed sc
            INNER JOIN v_wb_product_source p ON p.project_id = :project_id AND p.nm_id = sc.nm_id AND p.subject_id = :subject_id"""
        filtered_sku_where = "WHERE (p.title ILIKE :q_pattern OR p.vendor_code ILIKE :q_pattern OR p.vendor_code_norm ILIKE :q_pattern OR sc.nm_id::text = :q_exact)"
    elif subject_id is not None:
        filtered_sku_from = """FROM sku_computed sc
            INNER JOIN v_wb_product_source p ON p.project_id = :project_id AND p.nm_id = sc.nm_id AND p.subject_id = :subject_id"""
    elif q and q.strip():
        filtered_sku_from = """FROM sku_computed sc
            LEFT JOIN v_wb_product_source p ON p.project_id = :project_id AND p.nm_id = sc.nm_id"""
        filtered_sku_where = "WHERE (p.title ILIKE :q_pattern OR p.vendor_code ILIKE :q_pattern OR p.vendor_code_norm ILIKE :q_pattern OR sc.nm_id::text = :q_exact)"
    else:
        filtered_sku_from = "FROM sku_computed sc LEFT JOIN v_wb_product_source p ON p.project_id = :project_id AND p.nm_id = sc.nm_id"

    base_lines_select = f"""
        SELECT
            CASE WHEN COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$'
                THEN (COALESCE(r.payload->>'nm_id', r.payload->>'nmId')::bigint)
                ELSE NULL
            END AS nm_id,
            ({sign_expr})::int AS sign_val,
            CASE WHEN COALESCE(r.payload->>'doc_type_name', r.payload->>'docTypeName') ILIKE '%возврат%'
              OR COALESCE(r.payload->>'supplier_oper_name', r.payload->>'supplierOperName') ILIKE '%возврат%'
            THEN true ELSE false END AS is_return,
            {v_retail} AS retail_amount,
            {v_transfer} AS ppvz_for_pay,
            {v_delivery} AS delivery_rub,
            {v_storage} AS storage_fee,
            {v_acceptance} AS acceptance,
            {v_deduction} AS deduction,
            {v_penalty} AS penalty,
            {v_ppvz_vw} AS ppvz_vw,
            {v_ppvz_vw_nds} AS ppvz_vw_nds,
            {v_acquiring} AS acquiring_fee
    """
    sku_agg_select = """
        nm_id,
        SUM(sign_val * retail_amount) AS sale_amount,
        (COUNT(*) FILTER (WHERE retail_amount > 0) - COUNT(*) FILTER (WHERE is_return AND retail_amount != 0))::int AS net_sales_cnt,
        SUM(sign_val * ppvz_for_pay) AS transfer_amount,
        SUM(delivery_rub) AS logistics_cost,
        SUM(storage_fee) AS storage_cost,
        SUM(acceptance) AS acceptance_cost,
        SUM(deduction) AS other_withholdings,
        SUM(penalty) AS penalties,
        SUM(COALESCE(ppvz_vw, 0) + COALESCE(ppvz_vw_nds, 0)) AS commission_vv_signed,
        SUM(COALESCE(acquiring_fee, 0)) AS acquiring
    """
    rrp_sql = text(f"""
        WITH base_lines AS (
            {base_lines_select}
            {from_clause}
            {scope_where}
              AND (COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$')
        ),
        sku_agg AS (
            SELECT {sku_agg_select}
            FROM base_lines
            WHERE nm_id IS NOT NULL
            GROUP BY nm_id
        ),
        allocation_totals AS (
            SELECT
                COALESCE(SUM(
                    COALESCE(commission_vv_signed, 0)
                    + COALESCE(acquiring, 0)
                    + logistics_cost
                    + storage_cost
                    + acceptance_cost
                    + other_withholdings
                    + penalties
                ) FILTER (WHERE nm_id = 0), 0) AS common_wb_total,
                COALESCE(SUM(GREATEST(sale_amount, 0)) FILTER (WHERE nm_id <> 0), 0) AS positive_sale_total
            FROM sku_agg
        ),
        sku_computed AS (
            SELECT
                sa.*,
                (
                    transfer_amount
                    - logistics_cost
                    - storage_cost
                    - acceptance_cost
                    - other_withholdings
                    - penalties
                    - CASE
                        WHEN sa.nm_id <> 0
                          AND at.positive_sale_total > 0
                          AND GREATEST(sa.sale_amount, 0) > 0
                        THEN at.common_wb_total * GREATEST(sa.sale_amount, 0) / at.positive_sale_total
                        ELSE 0
                      END
                ) AS total_to_pay
            FROM sku_agg sa
            CROSS JOIN allocation_totals at
        ),
        filtered_skus AS (
            SELECT sc.nm_id, sc.net_sales_cnt, sc.total_to_pay, p.vendor_code_norm
            {filtered_sku_from}
            {filtered_sku_where}
        )
        SELECT nm_id, net_sales_cnt, total_to_pay, vendor_code_norm FROM filtered_skus
        WHERE nm_id <> 0
    """)
    sku_rows = conn.execute(rrp_sql, params).mappings().all()
    if not sku_rows:
        return {
            "rrp_sales_model": None,
            "wb_took_from_rrp_rub": None,
            "wb_took_from_rrp_pct": None,
            "rrp_coverage_qty_pct": None,
        }

    from app.services.wb_financial.sku_resolver import resolve_internal_skus_bulk

    nm_ids = [r["nm_id"] for r in sku_rows]
    nm_to_sku = resolve_internal_skus_bulk(project_id, nm_ids)

    unique_skus_set: set = set()
    for r in sku_rows:
        sn = _normalize_sku_norm(nm_to_sku.get(r["nm_id"]) or r.get("vendor_code_norm"))
        if sn:
            unique_skus_set.add(sn)
    unique_skus = list(unique_skus_set)

    rrp_map: Dict[str, float] = {}
    if unique_skus:
        snapshot_id = conn.execute(
            text(
                """
                SELECT id FROM internal_data_snapshots
                WHERE project_id = :project_id AND status IN ('success', 'partial')
                ORDER BY imported_at DESC NULLS LAST LIMIT 1
                """
            ),
            {"project_id": project_id},
        ).scalar()
        if snapshot_id:
            rrp_db = conn.execute(
                text(
                    """
                    SELECT
                        NULLIF(regexp_replace(trim(both '/' from ip.internal_sku), '^.*/', ''), '') AS sku_norm,
                        MAX(ipp.rrp) AS rrp_price
                    FROM internal_products ip
                    JOIN internal_product_prices ipp
                      ON ipp.internal_product_id = ip.id AND ipp.snapshot_id = ip.snapshot_id
                    WHERE ip.project_id = :project_id AND ip.snapshot_id = :snapshot_id
                      AND ipp.rrp IS NOT NULL
                      AND NULLIF(regexp_replace(trim(both '/' from ip.internal_sku), '^.*/', ''), '') = ANY(:skus)
                    GROUP BY 1
                    """
                ),
                {"project_id": project_id, "snapshot_id": snapshot_id, "skus": unique_skus},
            ).mappings().all()
            rrp_map = {str(r["sku_norm"]): float(r["rrp_price"]) for r in rrp_db if r.get("sku_norm")}

    rrp_sales_model = 0.0
    total_to_pay_filtered = 0.0
    sold_total = 0
    sold_with_rrp = 0

    for r in sku_rows:
        nm_id = r["nm_id"]
        sold_qty = int(r["net_sales_cnt"] or 0)
        tp = float(r["total_to_pay"] or 0)
        total_to_pay_filtered += tp
        sold_total += sold_qty

        sku_norm = _normalize_sku_norm(nm_to_sku.get(nm_id) or r.get("vendor_code_norm"))
        rrp = float(rrp_map.get(str(sku_norm))) if sku_norm and sku_norm in rrp_map else None
        if rrp is not None and sold_qty > 0:
            rrp_sales_model += rrp * sold_qty
            sold_with_rrp += sold_qty

    wb_took_from_rrp_rub = None
    wb_took_from_rrp_pct = None
    if rrp_sales_model and rrp_sales_model > 0:
        wb_took_from_rrp_rub = rrp_sales_model - total_to_pay_filtered
        wb_took_from_rrp_pct = (wb_took_from_rrp_rub / rrp_sales_model) * 100

    rrp_coverage_qty_pct = None
    if sold_total > 0:
        rrp_coverage_qty_pct = (sold_with_rrp / sold_total) * 100

    return {
        "rrp_sales_model": rrp_sales_model if rrp_sales_model else None,
        "wb_took_from_rrp_rub": wb_took_from_rrp_rub,
        "wb_took_from_rrp_pct": wb_took_from_rrp_pct,
        "rrp_coverage_qty_pct": rrp_coverage_qty_pct,
    }


def _scope_to_dict(scope: Union[ReportScope, PeriodScope]) -> Dict[str, Any]:
    if scope.mode == "report":
        return {"mode": "report", "report_id": scope.report_id}
    return {
        "mode": "period",
        "rr_dt_from": scope.rr_dt_from.isoformat() if scope.rr_dt_from else None,
        "rr_dt_to": scope.rr_dt_to.isoformat() if scope.rr_dt_to else None,
    }


def _resolve_as_of_date(
    conn: Connection,
    project_id: int,
    scope: Union[ReportScope, PeriodScope],
) -> date:
    """Resolve as_of_date for COGS rule selection. Report: period_to from wb_finance_reports else MAX(rr_dt). Period: rr_dt_to."""
    if scope.mode == "period":
        return scope.rr_dt_to if scope.rr_dt_to else date.today()
    if scope.mode == "report":
        row = conn.execute(
            text(
                """
                SELECT period_to FROM wb_finance_reports
                WHERE project_id = :project_id AND report_id = :report_id
                  AND marketplace_code = 'wildberries'
                LIMIT 1
                """
            ),
            {"project_id": project_id, "report_id": scope.report_id},
        ).mappings().first()
        if row and row.get("period_to"):
            return row["period_to"]
        row = conn.execute(
            text(
                """
                SELECT MAX(
                    (COALESCE(r.payload->>'rr_dt', r.payload->>'rrDt'))::date
                ) AS max_dt
                FROM wb_finance_report_lines r
                WHERE r.project_id = :project_id AND r.report_id = :report_id
                  AND COALESCE(r.payload->>'rr_dt', r.payload->>'rrDt') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                """
            ),
            {"project_id": project_id, "report_id": scope.report_id},
        ).mappings().first()
        if row and row.get("max_dt"):
            return row["max_dt"]
    return date.today()


def _resolve_scope_dates(
    conn: Connection,
    project_id: int,
    scope: Union[ReportScope, PeriodScope],
) -> Tuple[date, date]:
    """Resolve inclusive date range for additional-cost overlap."""
    if scope.mode == "period":
        d_from = scope.rr_dt_from or date.today()
        d_to = scope.rr_dt_to or d_from
        return d_from, d_to

    row = conn.execute(
        text(
            """
            SELECT period_from, period_to
            FROM wb_finance_reports
            WHERE project_id = :project_id
              AND report_id = :report_id
              AND marketplace_code = 'wildberries'
            LIMIT 1
            """
        ),
        {"project_id": project_id, "report_id": scope.report_id},
    ).mappings().first()
    if row and row.get("period_from") and row.get("period_to"):
        return row["period_from"], row["period_to"]

    row = conn.execute(
        text(
            """
            SELECT
                MIN((COALESCE(r.payload->>'rr_dt', r.payload->>'rrDt'))::date) AS min_dt,
                MAX((COALESCE(r.payload->>'rr_dt', r.payload->>'rrDt'))::date) AS max_dt
            FROM wb_finance_report_lines r
            WHERE r.project_id = :project_id
              AND r.report_id = :report_id
              AND COALESCE(r.payload->>'rr_dt', r.payload->>'rrDt') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
            """
        ),
        {"project_id": project_id, "report_id": scope.report_id},
    ).mappings().first()
    if row and row.get("min_dt") and row.get("max_dt"):
        return row["min_dt"], row["max_dt"]

    fallback = _resolve_as_of_date(conn, project_id, scope)
    return fallback, fallback


def _fetch_packaging_costs(
    conn: Connection,
    project_id: int,
    sku_norms: List[str],
    as_of_date: date,
) -> Dict[str, Optional[float]]:
    if not sku_norms:
        return {}
    values_clause = ", ".join(f"(:pkg_sku_{i})" for i in range(len(sku_norms)))
    params: Dict[str, Any] = {
        "project_id": project_id,
        "as_of_date": as_of_date,
        **{f"pkg_sku_{i}": sku for i, sku in enumerate(sku_norms)},
    }
    rows = conn.execute(
        text(
            f"""
            WITH sku_input(sku_norm) AS (
                VALUES {values_clause}
            )
            SELECT DISTINCT ON (si.sku_norm)
                si.sku_norm,
                pt.cost_per_unit
            FROM sku_input si
            LEFT JOIN packaging_tariffs pt
              ON pt.project_id = :project_id
             AND NULLIF(regexp_replace(trim(both '/' from pt.internal_sku), '^.*/', ''), '') = si.sku_norm
             AND pt.valid_from <= :as_of_date
            ORDER BY si.sku_norm, pt.valid_from DESC NULLS LAST
            """
        ),
        params,
    ).mappings().all()
    return {
        str(r["sku_norm"]): (float(r["cost_per_unit"]) if r.get("cost_per_unit") is not None else None)
        for r in rows
    }


def _fetch_product_additional_costs(
    conn: Connection,
    project_id: int,
    sku_norms: List[str],
    scope_from: date,
    scope_to: date,
) -> Dict[str, float]:
    if not sku_norms:
        return {}
    rows = conn.execute(
        text(
            """
            SELECT
                NULLIF(regexp_replace(trim(both '/' from internal_sku), '^.*/', ''), '') AS sku_norm,
                SUM(
                    amount
                    * ((LEAST(period_to, :scope_to) - GREATEST(period_from, :scope_from) + 1)::numeric)
                    / NULLIF((period_to - period_from + 1)::numeric, 0)
                ) AS amount
            FROM additional_cost_entries
            WHERE project_id = :project_id
              AND scope = 'product'
              AND period_from <= :scope_to
              AND period_to >= :scope_from
              AND internal_sku IS NOT NULL
              AND NULLIF(regexp_replace(trim(both '/' from internal_sku), '^.*/', ''), '') = ANY(:skus)
            GROUP BY 1
            """
        ),
        {"project_id": project_id, "scope_from": scope_from, "scope_to": scope_to, "skus": sku_norms},
    ).mappings().all()
    return {str(r["sku_norm"]): float(r["amount"] or 0) for r in rows if r.get("sku_norm")}


def _fetch_marketplace_additional_total(
    conn: Connection,
    project_id: int,
    scope_from: date,
    scope_to: date,
) -> float:
    total = conn.execute(
        text(
            """
            SELECT COALESCE(SUM(
                amount
                * ((LEAST(period_to, :scope_to) - GREATEST(period_from, :scope_from) + 1)::numeric)
                / NULLIF((period_to - period_from + 1)::numeric, 0)
            ), 0) AS amount
            FROM additional_cost_entries
            WHERE project_id = :project_id
              AND scope = 'marketplace'
              AND marketplace_code = 'wildberries'
              AND period_from <= :scope_to
              AND period_to >= :scope_from
            """
        ),
        {"project_id": project_id, "scope_from": scope_from, "scope_to": scope_to},
    ).scalar()
    return float(total or 0)


def _fetch_warehouse_labor_total(
    conn: Connection,
    project_id: int,
    scope_from: date,
    scope_to: date,
) -> float:
    total = conn.execute(
        text(
            """
            SELECT COALESCE(SUM(r.employees_count * r.rate_amount), 0) AS amount
            FROM warehouse_labor_days d
            INNER JOIN warehouse_labor_day_rates r ON r.labor_day_id = d.id
            WHERE d.project_id = :project_id
              AND (d.marketplace_code = 'wildberries' OR d.marketplace_code IS NULL OR d.marketplace_code = '')
              AND d.work_date >= :scope_from
              AND d.work_date <= :scope_to
            """
        ),
        {"project_id": project_id, "scope_from": scope_from, "scope_to": scope_to},
    ).scalar()
    return float(total or 0)


def _fetch_common_wb_allocation_for_nm(
    conn: Connection,
    project_id: int,
    nm_id: int,
    scope: Union[ReportScope, PeriodScope],
) -> Dict[str, float]:
    """Return the nm_id=0 WB take allocated to one SKU by positive sale share."""
    params: Dict[str, Any] = {"project_id": project_id, "nm_id": nm_id}
    scope_filter = _build_scope_filter(scope, params)
    scope_where = f"WHERE {scope_filter}"
    from_clause = _build_from_clause(scope)

    v_retail = _coalesce_num("retail_amount")
    v_delivery = _coalesce_num("delivery_rub")
    v_storage = _coalesce_num("storage_fee")
    v_acceptance = _coalesce_num("acceptance")
    v_deduction = _coalesce_num("deduction")
    v_penalty = _coalesce_num("penalty")
    v_ppvz_vw = _coalesce_num("ppvz_vw")
    v_ppvz_vw_nds = _coalesce_num("ppvz_vw_nds")
    v_acquiring = _coalesce_num("acquiring_fee")
    sign_expr = """CASE
        WHEN COALESCE(r.payload->>'doc_type_name', r.payload->>'docTypeName') ILIKE '%возврат%'
          OR COALESCE(r.payload->>'supplier_oper_name', r.payload->>'supplierOperName') ILIKE '%возврат%'
        THEN -1
        ELSE 1
    END"""

    row = conn.execute(
        text(
            f"""
            WITH base_lines AS (
                SELECT
                    CASE WHEN COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$'
                        THEN (COALESCE(r.payload->>'nm_id', r.payload->>'nmId')::bigint)
                        ELSE NULL
                    END AS nm_id,
                    ({sign_expr})::int AS sign_val,
                    {v_retail} AS retail_amount,
                    {v_delivery} AS delivery_rub,
                    {v_storage} AS storage_fee,
                    {v_acceptance} AS acceptance,
                    {v_deduction} AS deduction,
                    {v_penalty} AS penalty,
                    {v_ppvz_vw} AS ppvz_vw,
                    {v_ppvz_vw_nds} AS ppvz_vw_nds,
                    {v_acquiring} AS acquiring_fee
                {from_clause}
                {scope_where}
                  AND (COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$')
            ),
            sku_agg AS (
                SELECT
                    nm_id,
                    SUM(sign_val * retail_amount) AS sale_amount,
                    SUM(COALESCE(ppvz_vw, 0) + COALESCE(ppvz_vw_nds, 0)) AS commission_vv_signed,
                    SUM(COALESCE(acquiring_fee, 0)) AS acquiring,
                    SUM(delivery_rub) AS logistics_cost,
                    SUM(storage_fee) AS storage_cost,
                    SUM(acceptance) AS acceptance_cost,
                    SUM(deduction) AS other_withholdings,
                    SUM(penalty) AS penalties
                FROM base_lines
                WHERE nm_id IS NOT NULL
                GROUP BY nm_id
            ),
            allocation_totals AS (
                SELECT
                    COALESCE(SUM(
                        COALESCE(commission_vv_signed, 0)
                        + COALESCE(acquiring, 0)
                        + logistics_cost
                        + storage_cost
                        + acceptance_cost
                        + other_withholdings
                        + penalties
                    ) FILTER (WHERE nm_id = 0), 0) AS common_wb_total,
                    COALESCE(SUM(GREATEST(sale_amount, 0)) FILTER (WHERE nm_id <> 0), 0) AS positive_sale_total
                FROM sku_agg
            )
            SELECT
                at.common_wb_total,
                at.positive_sale_total,
                COALESCE(sa.sale_amount, 0) AS sku_sale,
                CASE
                    WHEN at.positive_sale_total > 0 AND GREATEST(COALESCE(sa.sale_amount, 0), 0) > 0
                    THEN at.common_wb_total * GREATEST(COALESCE(sa.sale_amount, 0), 0) / at.positive_sale_total
                    ELSE 0
                END AS allocated_total
            FROM allocation_totals at
            LEFT JOIN sku_agg sa ON sa.nm_id = :nm_id
            """
        ),
        params,
    ).mappings().first()
    if not row:
        return {
            "common_wb_total": 0.0,
            "common_wb_positive_sale_total": 0.0,
            "sku_sale": 0.0,
            "allocated_total": 0.0,
        }
    return {
        "common_wb_total": float(row.get("common_wb_total") or 0),
        "common_wb_positive_sale_total": float(row.get("positive_sale_total") or 0),
        "sku_sale": float(row.get("sku_sale") or 0),
        "allocated_total": float(row.get("allocated_total") or 0),
    }


def apply_extended_costs(
    conn: Connection,
    project_id: int,
    items: List[Dict[str, Any]],
    *,
    scope_from: date,
    scope_to: date,
    as_of_date: date,
    marketplace_sale_total: Optional[float] = None,
) -> Dict[str, Any]:
    """Attach packaging/additional costs and full-profit metrics to Unit PnL rows."""
    if not items:
        return {
            "packaging_cost_total": 0.0,
            "cogs_cost_total": 0.0,
            "additional_costs_total": 0.0,
            "full_profit_total": None,
            "full_margin_pct_of_revenue": None,
            "packaging_missing_count": 0,
        }

    sku_norms = [
        str(item.get("internal_sku") or item.get("vendor_code_norm"))
        for item in items
        if item.get("internal_sku") or item.get("vendor_code_norm")
    ]
    sku_norms = list({s for s in (_normalize_sku_norm(s) for s in sku_norms) if s})

    packaging_map = _fetch_packaging_costs(conn, project_id, sku_norms, as_of_date)
    product_costs_map = _fetch_product_additional_costs(conn, project_id, sku_norms, scope_from, scope_to)
    marketplace_total = _fetch_marketplace_additional_total(conn, project_id, scope_from, scope_to)
    warehouse_labor_total = _fetch_warehouse_labor_total(conn, project_id, scope_from, scope_to)
    distributable_total = marketplace_total + warehouse_labor_total
    sale_total = marketplace_sale_total
    if sale_total is None:
        sale_total = sum(max(float(item.get("sale_amount") or 0), 0.0) for item in items)

    packaging_total_sum = 0.0
    cogs_total_sum = 0.0
    additional_total_sum = 0.0
    full_profit_total_sum = 0.0
    full_profit_known = False
    full_margin_revenue = 0.0
    full_margin_revenue_known = False
    packaging_missing_count = 0

    for item in items:
        sku_norm = _normalize_sku_norm(item.get("internal_sku") or item.get("vendor_code_norm"))
        qty = int(item.get("sales_cnt") or 0)
        sale_amount = float(item.get("sale_amount") or 0)
        positive_sale = max(sale_amount, 0.0)

        packaging_unit = packaging_map.get(str(sku_norm)) if sku_norm else None
        packaging_missing = packaging_unit is None
        packaging_total = (packaging_unit * qty) if packaging_unit is not None and qty > 0 else None
        if packaging_total is not None:
            packaging_total_sum += packaging_total
        if packaging_missing:
            packaging_missing_count += 1

        cogs_total = item.get("cogs_total")
        if cogs_total is not None:
            cogs_total_sum += float(cogs_total or 0)

        product_total = float(product_costs_map.get(str(sku_norm), 0.0)) if sku_norm else 0.0
        marketplace_allocated = (
            marketplace_total * positive_sale / sale_total
            if sale_total and sale_total > 0 and positive_sale > 0
            else 0.0
        )
        warehouse_labor_allocated = (
            warehouse_labor_total * positive_sale / sale_total
            if sale_total and sale_total > 0 and positive_sale > 0
            else 0.0
        )
        additional_total = product_total + marketplace_allocated + warehouse_labor_allocated
        additional_unit = (additional_total / qty) if qty > 0 else None
        additional_total_sum += additional_total

        metrics = compute_extended_unit_metrics(
            fact_price_avg=item.get("fact_price_avg"),
            wb_total_cost_per_unit=item.get("wb_total_cost_per_unit"),
            cogs_per_unit=item.get("cogs_per_unit"),
            packaging_cost_per_unit=packaging_unit,
            additional_costs_per_unit=additional_unit,
            sales_cnt=qty,
        )

        item["packaging_cost_per_unit"] = packaging_unit
        item["packaging_cost_total"] = packaging_total
        item["packaging_missing"] = packaging_missing
        item["additional_costs_total"] = additional_total
        item["additional_costs_per_unit"] = additional_unit if additional_unit is not None else 0.0
        item["full_profit_per_unit"] = metrics["full_profit_per_unit"]
        item["full_profit_total"] = metrics["full_profit_total"]
        item["full_margin_pct_of_revenue"] = metrics["full_margin_pct_of_revenue"]
        item["extended_costs"] = {
            "packaging_cost_per_unit": packaging_unit,
            "packaging_cost_total": packaging_total,
            "packaging_missing": packaging_missing,
            "product_additional_costs_total": product_total,
            "marketplace_additional_costs_total": marketplace_allocated,
            "warehouse_labor_costs_total": warehouse_labor_allocated,
            "additional_costs_total": additional_total,
            "additional_costs_per_unit": item["additional_costs_per_unit"],
        }

        if metrics["full_profit_total"] is not None:
            full_profit_known = True
            full_profit_total_sum += float(metrics["full_profit_total"])
        if metrics["full_profit_total"] is not None and sale_amount > 0:
            full_margin_revenue_known = True
            full_margin_revenue += sale_amount

    return {
        "packaging_cost_total": packaging_total_sum,
        "cogs_cost_total": cogs_total_sum,
        "additional_costs_total": additional_total_sum,
        "full_profit_total": full_profit_total_sum if full_profit_known else None,
        "full_margin_pct_of_revenue": (
            (full_profit_total_sum / full_margin_revenue) * 100
            if full_margin_revenue_known and full_margin_revenue > 0
            else None
        ),
        "packaging_missing_count": packaging_missing_count,
        "marketplace_additional_costs_total": marketplace_total,
        "warehouse_labor_costs_total": warehouse_labor_total,
        "distributable_additional_costs_total": distributable_total,
    }


def _load_extended_header_basis(
    conn: Connection,
    project_id: int,
    params: Dict[str, Any],
    from_clause: str,
    scope_where: str,
    sign_expr: str,
    v_retail: str,
    v_transfer: str,
    v_delivery: str,
    v_storage: str,
    v_acceptance: str,
    v_deduction: str,
    v_penalty: str,
    v_ppvz_vw: str,
    v_ppvz_vw_nds: str,
    v_acquiring: str,
    v_retail_price: str,
    v_ppvz_spp_prc: str,
    q: Optional[str],
    subject_id: Optional[int],
) -> List[Dict[str, Any]]:
    """Load all filtered SKU basis rows for extended header totals."""
    filtered_from = ""
    filtered_where = ""
    if subject_id is not None and q and q.strip():
        filtered_from = """FROM sku_computed sc
            INNER JOIN v_wb_product_source p ON p.project_id = :project_id AND p.nm_id = sc.nm_id AND p.subject_id = :subject_id"""
        filtered_where = "WHERE (p.title ILIKE :q_pattern OR p.vendor_code ILIKE :q_pattern OR p.vendor_code_norm ILIKE :q_pattern OR sc.nm_id::text = :q_exact)"
    elif subject_id is not None:
        filtered_from = """FROM sku_computed sc
            INNER JOIN v_wb_product_source p ON p.project_id = :project_id AND p.nm_id = sc.nm_id AND p.subject_id = :subject_id"""
    elif q and q.strip():
        filtered_from = """FROM sku_computed sc
            LEFT JOIN v_wb_product_source p ON p.project_id = :project_id AND p.nm_id = sc.nm_id"""
        filtered_where = "WHERE (p.title ILIKE :q_pattern OR p.vendor_code ILIKE :q_pattern OR p.vendor_code_norm ILIKE :q_pattern OR sc.nm_id::text = :q_exact)"
    else:
        filtered_from = "FROM sku_computed sc LEFT JOIN v_wb_product_source p ON p.project_id = :project_id AND p.nm_id = sc.nm_id"

    rows = conn.execute(
        text(
            f"""
            WITH base_lines AS (
                SELECT
                    CASE WHEN COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$'
                        THEN (COALESCE(r.payload->>'nm_id', r.payload->>'nmId')::bigint)
                        ELSE NULL
                    END AS nm_id,
                    ({sign_expr})::int AS sign_val,
                    CASE WHEN ({sign_expr}) = -1 THEN true ELSE false END AS is_return,
                    {v_retail} AS retail_amount,
                    {v_transfer} AS ppvz_for_pay,
                    {v_delivery} AS delivery_rub,
                    {v_storage} AS storage_fee,
                    {v_acceptance} AS acceptance,
                    {v_deduction} AS deduction,
                    {v_penalty} AS penalty,
                    {v_ppvz_vw} AS ppvz_vw,
                    {v_ppvz_vw_nds} AS ppvz_vw_nds,
                    {v_acquiring} AS acquiring_fee,
                    {v_retail_price} AS retail_price,
                    {v_ppvz_spp_prc} AS ppvz_spp_prc
                {from_clause}
                {scope_where}
                  AND (COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$')
            ),
            sku_agg AS (
                SELECT
                    nm_id,
                    SUM(sign_val * retail_amount) AS sale_amount,
                    SUM(COALESCE(ppvz_vw, 0) + COALESCE(ppvz_vw_nds, 0)) AS commission_vv_signed,
                    SUM(COALESCE(acquiring_fee, 0)) AS acquiring,
                    SUM(delivery_rub) AS logistics_cost,
                    SUM(storage_fee) AS storage_cost,
                    SUM(acceptance) AS acceptance_cost,
                    SUM(deduction) AS other_withholdings,
                    SUM(penalty) AS penalties,
                    COUNT(*) FILTER (WHERE retail_amount > 0) AS sales_cnt,
                    COUNT(*) FILTER (WHERE is_return AND retail_amount != 0) AS returns_cnt,
                    AVG(retail_price) FILTER (WHERE retail_price IS NOT NULL AND retail_price > 0) AS wb_price_avg,
                    AVG(sign_val * retail_amount) FILTER (WHERE retail_amount IS NOT NULL AND retail_amount != 0) AS fact_price_avg
                FROM base_lines
                WHERE nm_id IS NOT NULL
                GROUP BY nm_id
            ),
            allocation_totals AS (
                SELECT
                    COALESCE(SUM(
                        COALESCE(commission_vv_signed, 0)
                        + COALESCE(acquiring, 0)
                        + logistics_cost
                        + storage_cost
                        + acceptance_cost
                        + other_withholdings
                        + penalties
                    ) FILTER (WHERE nm_id = 0), 0) AS common_wb_total,
                    COALESCE(SUM(GREATEST(sale_amount, 0)) FILTER (WHERE nm_id <> 0), 0) AS positive_sale_total
                FROM sku_agg
            ),
            sku_computed AS (
                SELECT
                    sa.*,
                    (sales_cnt - returns_cnt)::int AS net_sales_cnt,
                    (
                        COALESCE(commission_vv_signed, 0)
                        + COALESCE(acquiring, 0)
                        + logistics_cost
                        + storage_cost
                        + acceptance_cost
                        + other_withholdings
                        + penalties
                    ) AS wb_own_total_signed,
                    CASE
                        WHEN sa.nm_id <> 0
                          AND at.positive_sale_total > 0
                          AND GREATEST(sa.sale_amount, 0) > 0
                        THEN at.common_wb_total * GREATEST(sa.sale_amount, 0) / at.positive_sale_total
                        ELSE 0
                    END AS wb_common_allocated_total,
                    (
                        COALESCE(commission_vv_signed, 0)
                        + COALESCE(acquiring, 0)
                        + logistics_cost
                        + storage_cost
                        + acceptance_cost
                        + other_withholdings
                        + penalties
                        + CASE
                            WHEN sa.nm_id <> 0
                              AND at.positive_sale_total > 0
                              AND GREATEST(sa.sale_amount, 0) > 0
                            THEN at.common_wb_total * GREATEST(sa.sale_amount, 0) / at.positive_sale_total
                            ELSE 0
                          END
                    ) AS wb_total_signed
                FROM sku_agg sa
                CROSS JOIN allocation_totals at
            ),
            filtered_skus AS (
                SELECT
                    sc.nm_id,
                    sc.sale_amount,
                    sc.sales_cnt,
                    sc.net_sales_cnt,
                    sc.fact_price_avg,
                    sc.wb_price_avg,
                    sc.wb_own_total_signed,
                    sc.wb_common_allocated_total,
                    CASE WHEN sc.sales_cnt > 0 THEN sc.wb_total_signed / sc.sales_cnt ELSE NULL END AS wb_total_cost_per_unit,
                    p.vendor_code_norm
                {filtered_from}
                {filtered_where}
            )
            SELECT * FROM filtered_skus
            WHERE nm_id <> 0
            """
        ),
        params,
    ).mappings().all()

    return [
        {
            "nm_id": int(r["nm_id"]),
            "sale_amount": float(r.get("sale_amount") or 0),
            "sales_cnt": int(r.get("sales_cnt") or 0),
            "net_sales_cnt": int(r.get("net_sales_cnt") or 0),
            "fact_price_avg": float(r["fact_price_avg"]) if r.get("fact_price_avg") is not None else None,
            "wb_price_avg": float(r["wb_price_avg"]) if r.get("wb_price_avg") is not None else None,
            "wb_own_total_signed": (
                float(r["wb_own_total_signed"]) if r.get("wb_own_total_signed") is not None else None
            ),
            "wb_common_allocated_total": (
                float(r["wb_common_allocated_total"]) if r.get("wb_common_allocated_total") is not None else None
            ),
            "wb_total_cost_per_unit": (
                float(r["wb_total_cost_per_unit"]) if r.get("wb_total_cost_per_unit") is not None else None
            ),
            "vendor_code_norm": r.get("vendor_code_norm"),
        }
        for r in rows
    ]


def _normalize_sku_norm(internal_sku: Optional[str]) -> Optional[str]:
    """Normalize internal_sku to sku_norm (same as db_wb_sku_pnl). Keep in sync with sku-pnl."""
    if not internal_sku or not isinstance(internal_sku, str):
        return None
    s = internal_sku.strip().strip("/")
    if not s:
        return None
    return re.sub(r"^.*/", "", s).strip() or None


def _build_cogs_rule_text(mode: Optional[str], value: Any) -> str:
    """Build human-readable cogs rule text from mode+value."""
    if not mode or value is None:
        return ""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return ""
    if mode == "fixed":
        return f"{v:,.0f} ₽".replace(",", " ")
    if mode == "percent_of_rrp":
        return f"{v}% от RRP"
    if mode == "percent_of_price":
        return f"{v}% от цены каталога"
    if mode == "percent_of_selling_price":
        return f"{v}% от цены реализации"
    return ""


def enrich_with_rrp_and_cogs(
    conn: Connection,
    project_id: int,
    items: List[Dict[str, Any]],
    as_of_date: date,
) -> List[Dict[str, Any]]:
    """Enrich unit-pnl items with RRP, COGS, profit, margin. Batch only, no N+1."""
    if not items:
        return items

    from app.services.wb_financial.sku_resolver import resolve_internal_skus_bulk
    from app.services.wb_financial.sku_pnl_metrics import compute_unit_metrics

    nm_ids = [r["nm_id"] for r in items]
    nm_to_sku = resolve_internal_skus_bulk(project_id, nm_ids)

    sku_norms: List[Optional[str]] = []
    for r in items:
        internal_sku = nm_to_sku.get(r["nm_id"]) or r.get("vendor_code_norm")
        sku_norms.append(_normalize_sku_norm(internal_sku))

    unique_skus = list({s for s in sku_norms if s})
    if not unique_skus:
        for r in items:
            r["rrp_price"] = None
            r["rrp_missing"] = True
            r["cogs_per_unit"] = None
            r["cogs_total"] = None
            r["cogs_rule_text"] = None
            r["cogs_missing"] = True
            r["profit_per_unit"] = None
            r["margin_pct_of_revenue"] = None
            r["margin_pct_of_rrp"] = None
            r["markup_pct_of_cogs"] = None
        return items

    snapshot_id = conn.execute(
        text(
            """
            SELECT id FROM internal_data_snapshots
            WHERE project_id = :project_id AND status IN ('success', 'partial')
            ORDER BY imported_at DESC NULLS LAST LIMIT 1
            """
        ),
        {"project_id": project_id},
    ).scalar()
    rrp_map: Dict[str, float] = {}
    if snapshot_id:
        rrp_rows = conn.execute(
            text(
                """
                SELECT
                    NULLIF(regexp_replace(trim(both '/' from ip.internal_sku), '^.*/', ''), '') AS sku_norm,
                    MAX(ipp.rrp) AS rrp_price
                FROM internal_products ip
                JOIN internal_product_prices ipp
                  ON ipp.internal_product_id = ip.id AND ipp.snapshot_id = ip.snapshot_id
                WHERE ip.project_id = :project_id AND ip.snapshot_id = :snapshot_id
                  AND ipp.rrp IS NOT NULL
                  AND NULLIF(regexp_replace(trim(both '/' from ip.internal_sku), '^.*/', ''), '') = ANY(:skus)
                GROUP BY 1
                """
            ),
            {"project_id": project_id, "snapshot_id": snapshot_id, "skus": unique_skus},
        ).mappings().all()
        rrp_map = {str(r["sku_norm"]): float(r["rrp_price"]) for r in rrp_rows if r.get("sku_norm")}

    # VALUES clause to avoid SQLAlchemy :param conflicting with PostgreSQL :: cast in unnest
    values_clause = ", ".join(f"(:sku_{i})" for i in range(len(unique_skus)))
    cogs_params: Dict[str, Any] = {
        "project_id": project_id,
        "as_of_date": as_of_date,
        **{f"sku_{i}": s for i, s in enumerate(unique_skus)},
    }

    cogs_rows = conn.execute(
        text(
            f"""
            WITH sku_input(sku_norm) AS (
                VALUES {values_clause}
            ),
            rules AS (
                SELECT
                    si.sku_norm,
                    r.mode,
                    r.value,
                    r.price_source_code
                FROM sku_input si
                LEFT JOIN LATERAL (
                    SELECT r.mode, r.value, r.price_source_code
                    FROM cogs_direct_rules r
                    WHERE r.project_id = :project_id
                      AND r.valid_from <= :as_of_date
                      AND (r.valid_to IS NULL OR r.valid_to >= :as_of_date)
                      AND (
                        (r.applies_to = 'sku'
                         AND NULLIF(regexp_replace(trim(both '/' from r.internal_sku), '^.*/', ''), '') = si.sku_norm)
                        OR (r.applies_to = 'all' AND r.internal_sku = '__ALL__')
                      )
                    ORDER BY CASE WHEN r.applies_to = 'sku' THEN 0 ELSE 1 END, r.valid_from DESC
                    LIMIT 1
                ) r ON true
            )
            SELECT sku_norm, mode, value, price_source_code FROM rules
            """
        ),
        cogs_params,
    ).mappings().all()
    cogs_map: Dict[str, Dict[str, Any]] = {}
    for row in cogs_rows:
        sn = row.get("sku_norm")
        if sn:
            cogs_map[str(sn)] = {
                "mode": row.get("mode"),
                "value": row.get("value"),
                "price_source_code": row.get("price_source_code"),
            }

    wb_price_admin_map: Dict[int, Optional[float]] = {}
    for r in items:
        wb_price_admin_map[r["nm_id"]] = r.get("wb_price_avg")

    for i, r in enumerate(items):
        sku_norm = sku_norms[i]
        rrp = float(rrp_map[sku_norm]) if sku_norm and sku_norm in rrp_map else None
        rule = cogs_map.get(sku_norm) if sku_norm else None

        r["internal_sku"] = sku_norm
        r["rrp_price"] = rrp
        r["rrp_missing"] = rrp is None

        cogs_per_unit = None
        cogs_rule_text = None
        if rule and rule.get("mode"):
            mode = rule["mode"]
            val = rule.get("value")
            price_src = rule.get("price_source_code") or ""
            if mode == "fixed" and val is not None:
                cogs_per_unit = float(val)
            elif mode == "percent_of_rrp" and rrp is not None and val is not None:
                cogs_per_unit = float(rrp * float(val) / 100)
            elif mode == "percent_of_price" and price_src == "internal_catalog_rrp" and rrp is not None and val is not None:
                cogs_per_unit = float(rrp * float(val) / 100)
            elif mode == "percent_of_selling_price":
                wb_admin = wb_price_admin_map.get(r["nm_id"])
                if wb_admin is not None and val is not None:
                    cogs_per_unit = float(wb_admin * float(val) / 100)
            cogs_rule_text = _build_cogs_rule_text(mode, val) if cogs_per_unit is not None else None

        r["cogs_per_unit"] = cogs_per_unit
        r["cogs_rule_text"] = cogs_rule_text
        r["cogs_missing"] = cogs_per_unit is None

        net = int(r.get("net_sales_cnt") or 0)
        r["cogs_total"] = (cogs_per_unit * net) if cogs_per_unit is not None and net > 0 else None

        avg_price = r.get("fact_price_avg")
        if avg_price is None and net > 0:
            sale = float(r.get("sale_amount") or 0)
            avg_price = sale / net if sale else None
        wb_unit = r.get("wb_total_cost_per_unit")

        metrics = compute_unit_metrics(
            avg_price_realization_unit=avg_price,
            wb_total_unit=wb_unit,
            cogs_unit=cogs_per_unit,
            rrp=rrp,
        )
        r["profit_per_unit"] = float(metrics.profit_unit) if metrics.profit_unit is not None else None
        r["margin_pct_of_revenue"] = float(metrics.margin_pct_unit) if metrics.margin_pct_unit is not None else None
        r["margin_pct_of_rrp"] = float(metrics.profit_pct_rrp) if metrics.profit_pct_rrp is not None else None

        if r["profit_per_unit"] is not None and cogs_per_unit is not None and cogs_per_unit != 0:
            r["markup_pct_of_cogs"] = (r["profit_per_unit"] / cogs_per_unit) * 100
        else:
            r["markup_pct_of_cogs"] = None

    return items


def get_wb_unit_pnl_details(
    conn: Connection,
    project_id: int,
    nm_id: int,
    scope: Union[ReportScope, PeriodScope],
) -> Dict[str, Any]:
    """Get details for one nm_id. Minimal: aggregates, product, base_calc, logistics_counts, wb_costs_per_unit."""
    params: Dict[str, Any] = {"project_id": project_id, "nm_id": nm_id}
    scope_filter = _build_scope_filter(scope, params)
    scope_where = f"WHERE {scope_filter}"
    from_clause = _build_from_clause(scope)

    v_retail = _coalesce_num("retail_amount")
    v_transfer = _coalesce_num("ppvz_for_pay")
    v_delivery = _coalesce_num("delivery_rub")
    v_storage = _coalesce_num("storage_fee")
    v_acceptance = _coalesce_num("acceptance")
    v_deduction = _coalesce_num("deduction")
    v_penalty = _coalesce_num("penalty")
    v_cashback = _coalesce_num("cashback_discount")
    v_ppvz_vw = _coalesce_num("ppvz_vw")
    v_ppvz_vw_nds = _coalesce_num("ppvz_vw_nds")
    v_acquiring = _coalesce_num("acquiring_fee")
    v_retail_price = "NULLIF(TRIM(COALESCE(r.payload->>'retail_price', r.payload->>'retailPrice')), '')::numeric"
    v_ppvz_spp_prc = "NULLIF(TRIM(COALESCE(r.payload->>'ppvz_spp_prc', r.payload->>'ppvzSppPrc')), '')::numeric"
    v_delivery_amount = "NULLIF(TRIM(COALESCE(r.payload->>'delivery_amount', r.payload->>'deliveryAmount')), '')::numeric"
    v_return_amount = "NULLIF(TRIM(COALESCE(r.payload->>'return_amount', r.payload->>'returnAmount')), '')::numeric"
    bonus_type_expr = "COALESCE(r.payload->>'bonus_type_name', r.payload->>'bonusTypeName')"
    is_logistics_expr = """(
        COALESCE(r.payload->>'supplier_oper_name', r.payload->>'supplierOperName') = 'Логистика'
        OR COALESCE(r.payload->>'supplier_oper_name', r.payload->>'supplierOperName') ILIKE '%логистик%'
    )"""
    is_delivery_bonus = f"({bonus_type_expr} LIKE 'К клиенту%')"
    is_return_bonus = f"""(
        {bonus_type_expr} LIKE 'От клиента%'
        OR {bonus_type_expr} LIKE 'Возврат % (К продавцу)%'
        OR {bonus_type_expr} IN ('Возврат брака (К продавцу)', 'Возврат неопознанного товара (К продавцу)')
    )"""

    sign_expr = """CASE
        WHEN COALESCE(r.payload->>'doc_type_name', r.payload->>'docTypeName') ILIKE '%возврат%'
          OR COALESCE(r.payload->>'supplier_oper_name', r.payload->>'supplierOperName') ILIKE '%возврат%'
        THEN -1
        ELSE 1
    END"""

    nm_filter = """AND (
        COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$'
        AND (COALESCE(r.payload->>'nm_id', r.payload->>'nmId')::bigint) = :nm_id
    )"""

    sql = text(f"""
        WITH base_lines AS (
            SELECT
                ({sign_expr})::int AS sign_val,
                CASE WHEN ({sign_expr}) = -1 THEN true ELSE false END AS is_return,
                {v_retail} AS retail_amount,
                {v_transfer} AS ppvz_for_pay,
                {v_delivery} AS delivery_rub,
                {v_storage} AS storage_fee,
                {v_acceptance} AS acceptance,
                {v_deduction} AS deduction,
                {v_penalty} AS penalty,
                {v_cashback} AS cashback_discount,
                {v_ppvz_vw} AS ppvz_vw,
                {v_ppvz_vw_nds} AS ppvz_vw_nds,
                {v_acquiring} AS acquiring_fee,
                {v_retail_price} AS retail_price,
                {v_ppvz_spp_prc} AS ppvz_spp_prc,
                {v_delivery_amount} AS delivery_amount,
                {v_return_amount} AS return_amount,
                {is_logistics_expr} AS is_logistics,
                {is_delivery_bonus} AS is_delivery_bonus,
                {is_return_bonus} AS is_return_bonus
            {from_clause}
            {scope_where}
            {nm_filter}
        ),
        agg AS (
            SELECT
                SUM(sign_val * retail_amount) AS sale_amount,
                SUM(sign_val * ppvz_for_pay) AS transfer_amount,
                SUM(COALESCE(ppvz_vw, 0) + COALESCE(ppvz_vw_nds, 0)) AS commission_vv_signed,
                SUM(COALESCE(acquiring_fee, 0)) AS acquiring,
                SUM(delivery_rub) AS logistics_cost,
                SUM(storage_fee) AS storage_cost,
                SUM(acceptance) AS acceptance_cost,
                SUM(deduction) AS other_withholdings,
                SUM(penalty) AS penalties,
                SUM(cashback_discount) AS loyalty_comp_display,
                COUNT(*) FILTER (WHERE retail_amount > 0) AS sales_cnt,
                COUNT(*) FILTER (WHERE is_return AND retail_amount != 0) AS returns_cnt,
                AVG(retail_price) FILTER (WHERE retail_price IS NOT NULL AND retail_price > 0) AS wb_price_avg,
                AVG(ppvz_spp_prc) FILTER (WHERE ppvz_spp_prc IS NOT NULL AND ppvz_spp_prc > 0) AS spp_avg,
                AVG(sign_val * retail_amount) FILTER (WHERE retail_amount IS NOT NULL AND retail_amount != 0) AS fact_price_avg,
                COUNT(*) FILTER (WHERE retail_price IS NOT NULL AND retail_price > 0) AS retail_price_nonzero_rows,
                COUNT(*) FILTER (WHERE ppvz_spp_prc IS NOT NULL AND ppvz_spp_prc > 0) AS spp_nonzero_rows,
                COUNT(*) FILTER (WHERE retail_amount IS NOT NULL AND retail_amount != 0) AS retail_amount_nonzero_rows,
                CASE WHEN COUNT(delivery_amount) FILTER (WHERE is_logistics) > 0
                    THEN SUM(delivery_amount) FILTER (WHERE is_logistics)
                    ELSE (COUNT(*) FILTER (WHERE is_logistics AND is_delivery_bonus))::numeric
                END AS deliveries_qty,
                CASE WHEN COUNT(return_amount) FILTER (WHERE is_logistics) > 0
                    THEN SUM(return_amount) FILTER (WHERE is_logistics)
                    ELSE (COUNT(*) FILTER (WHERE is_logistics AND is_return_bonus))::numeric
                END AS returns_log_qty
            FROM base_lines
        )
        SELECT a.*, p.title, p.pics, p.vendor_code, p.vendor_code_norm
        FROM agg a
        LEFT JOIN v_wb_product_source p ON p.project_id = :project_id AND p.nm_id = :nm_id
    """)

    row = conn.execute(sql, params).mappings().first()
    if not row or row.get("sale_amount") is None:
        return {
            "nm_id": nm_id,
            "scope": _scope_to_dict(scope),
            "product": None,
            "base_calc": {},
            "wb_costs_per_unit": {},
            "logistics_counts": {},
            "debug": {"retail_price_nonzero_rows": 0, "spp_nonzero_rows": 0, "retail_amount_nonzero_rows": 0},
        }

    net_sales = int(row.get("sales_cnt") or 0) - int(row.get("returns_cnt") or 0)
    sales_cnt = int(row.get("sales_cnt") or 0)
    commission_vv_signed = float(row.get("commission_vv_signed") or 0)
    acquiring = float(row.get("acquiring") or 0)
    logistics_cost = float(row.get("logistics_cost") or 0)
    storage_cost = float(row.get("storage_cost") or 0)
    acceptance_cost = float(row.get("acceptance_cost") or 0)
    other_withholdings = float(row.get("other_withholdings") or 0)
    penalties = float(row.get("penalties") or 0)
    wb_total_signed = (
        commission_vv_signed
        + acquiring
        + logistics_cost
        + storage_cost
        + acceptance_cost
        + other_withholdings
        + penalties
    )
    wb_own_total_signed = wb_total_signed
    common_wb_allocation = _fetch_common_wb_allocation_for_nm(conn, project_id, nm_id, scope)
    wb_common_allocated_total = float(common_wb_allocation.get("allocated_total") or 0)
    wb_total_signed += wb_common_allocated_total
    deliveries_qty = int(row["deliveries_qty"]) if row.get("deliveries_qty") is not None else None
    returns_log_qty = int(row["returns_log_qty"]) if row.get("returns_log_qty") is not None else None
    buyout_rate = None
    if deliveries_qty and deliveries_qty > 0:
        buyout_rate = (deliveries_qty - (returns_log_qty or 0)) / deliveries_qty

    photos = []
    pics_val = row.get("pics")
    if pics_val:
        if isinstance(pics_val, str):
            import json
            try:
                pics_val = json.loads(pics_val)
            except Exception:
                pics_val = None
        if isinstance(pics_val, list):
            for pic in pics_val:
                if isinstance(pic, dict):
                    url = pic.get("url") or pic.get("big") or pic.get("c128")
                    if url:
                        photos.append(str(url))
                elif isinstance(pic, str):
                    photos.append(pic)

    sale_amount = float(row.get("sale_amount") or 0)
    # Per-unit denominator: sales_cnt (as in report)
    wb_total_per_unit = wb_total_signed / sales_cnt if sales_cnt > 0 else None
    wb_total_pct_of_sale = wb_total_signed / sale_amount if sale_amount > 0 else None

    def _pu(v: float) -> Optional[float]:
        return v / sales_cnt if sales_cnt > 0 else None

    breakdown = {
        "commission": _pu(commission_vv_signed),
        "acquiring": _pu(acquiring),
        "logistics": _pu(logistics_cost),
        "storage": _pu(storage_cost),
        "acceptance": _pu(acceptance_cost),
        "withholdings": _pu(other_withholdings),
        "penalties": _pu(penalties),
        "common_wb_allocated": _pu(wb_common_allocated_total),
        "total": wb_total_per_unit,
    }

    row_dict = {
        "nm_id": nm_id,
        "vendor_code_norm": row.get("vendor_code_norm"),
        "fact_price_avg": float(row["fact_price_avg"]) if row.get("fact_price_avg") is not None else None,
        "wb_total_cost_per_unit": wb_total_per_unit,
        "wb_own_total_signed": wb_own_total_signed,
        "wb_common_allocated_total": wb_common_allocated_total,
        "wb_common_allocated_per_unit": _pu(wb_common_allocated_total),
        "sales_cnt": sales_cnt,
        "net_sales_cnt": net_sales,
        "sale_amount": sale_amount,
        "wb_price_avg": float(row["wb_price_avg"]) if row.get("wb_price_avg") is not None else None,
    }
    as_of = _resolve_as_of_date(conn, project_id, scope)
    scope_from, scope_to = _resolve_scope_dates(conn, project_id, scope)
    allocation_basis = _load_extended_header_basis(
        conn,
        project_id,
        params,
        from_clause,
        scope_where,
        sign_expr,
        v_retail,
        v_transfer,
        v_delivery,
        v_storage,
        v_acceptance,
        v_deduction,
        v_penalty,
        v_ppvz_vw,
        v_ppvz_vw_nds,
        v_acquiring,
        v_retail_price,
        v_ppvz_spp_prc,
        None,
        None,
    )
    marketplace_sale_total = sum(max(float(r.get("sale_amount") or 0), 0.0) for r in allocation_basis)
    enriched_list = enrich_with_rrp_and_cogs(conn, project_id, [row_dict], as_of)
    enriched = enriched_list[0] if enriched_list else {}
    apply_extended_costs(
        conn,
        project_id,
        enriched_list,
        scope_from=scope_from,
        scope_to=scope_to,
        as_of_date=as_of,
        marketplace_sale_total=marketplace_sale_total,
    )
    enriched = enriched_list[0] if enriched_list else {}

    return {
        "nm_id": nm_id,
        "scope": _scope_to_dict(scope),
        "product": {
            "title": row.get("title"),
            "vendor_code": row.get("vendor_code"),
            "photos": photos,
        } if row.get("title") is not None or row.get("vendor_code") is not None else None,
        "base_calc": {
            "wb_price_avg": float(row["wb_price_avg"]) if row.get("wb_price_avg") is not None else None,
            "spp_avg": float(row["spp_avg"]) if row.get("spp_avg") is not None else None,
            "fact_price_avg": float(row["fact_price_avg"]) if row.get("fact_price_avg") is not None else None,
            "rrp_price": enriched.get("rrp_price"),
            "delta_fact_to_rrp_pct": (
                (float(row["fact_price_avg"]) - enriched["rrp_price"]) / enriched["rrp_price"] * 100
                if (
                    row.get("fact_price_avg") is not None
                    and enriched.get("rrp_price") is not None
                    and enriched["rrp_price"] != 0
                )
                else None
            ),
        },
        "profitability": {
            "profit_per_unit": enriched.get("profit_per_unit"),
            "margin_pct_of_revenue": enriched.get("margin_pct_of_revenue"),
            "margin_pct_of_rrp": enriched.get("margin_pct_of_rrp"),
            "cogs_rule_text": enriched.get("cogs_rule_text"),
            "markup_pct_of_cogs": enriched.get("markup_pct_of_cogs"),
            "rrp_missing": enriched.get("rrp_missing", True),
            "cogs_missing": enriched.get("cogs_missing", True),
            "cogs_per_unit": enriched.get("cogs_per_unit"),
            "cogs_total": enriched.get("cogs_total"),
        },
        "extended_costs": enriched.get("extended_costs", {}),
        "commission_vv_signed": commission_vv_signed,
        "acquiring": acquiring,
        "wb_own_total_signed": wb_own_total_signed,
        "wb_common_allocated_total": wb_common_allocated_total,
        "wb_common_allocated_per_unit": _pu(wb_common_allocated_total),
        "wb_total_signed": wb_total_signed,
        "wb_total_pct_of_sale": wb_total_pct_of_sale,
        "wb_costs_per_unit": {
            "total": wb_total_per_unit,
            "breakdown": breakdown,
            "own_wb_total_signed": wb_own_total_signed,
            "common_wb_allocated_total": wb_common_allocated_total,
            "common_wb_allocation_basis": common_wb_allocation,
            "logistics_cost": logistics_cost,
            "storage_cost": storage_cost,
            "acceptance_cost": acceptance_cost,
            "other_withholdings": other_withholdings,
            "penalties": penalties,
        },
        "logistics_counts": {
            "deliveries_qty": deliveries_qty,
            "returns_log_qty": returns_log_qty,
            "buyout_rate": buyout_rate,
        },
        "debug": {
            "retail_price_nonzero_rows": int(row.get("retail_price_nonzero_rows") or 0),
            "spp_nonzero_rows": int(row.get("spp_nonzero_rows") or 0),
            "retail_amount_nonzero_rows": int(row.get("retail_amount_nonzero_rows") or 0),
        },
    }
