"""Read-only Actual PnL v2 preview from wb_finance_report_lines.

Does NOT touch wb_sku_pnl_snapshots, event_mapping, or wb_financial_events.
Only aggregates raw payload for manual verification against WB report totals.

WB report mapping:
  transfer_for_goods = "К перечислению за товар"
  total_to_pay = "Итого к оплате"
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection


def _coalesce_num(*keys: str) -> str:
    """Build COALESCE for payload keys (snake_case, camelCase). First key wins."""
    parts = []
    for k in keys:
        camel = _to_camel(k)
        expr = f"NULLIF(TRIM(COALESCE(r.payload->>'{k}', r.payload->>'{camel}')), '')::numeric"
        parts.append(expr)
    return f"COALESCE({', '.join(parts)}, 0)"


def _to_camel(snake: str) -> str:
    """Convert snake_case to camelCase."""
    parts = snake.split("_")
    return parts[0].lower() + "".join(p.title() for p in parts[1:])


def get_wb_actual_v2_preview(
    conn: Connection,
    project_id: int,
    period_from: date,
    period_to: date,
    nm_id: Optional[int] = None,
    internal_sku: Optional[str] = None,
    report_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Get Actual PnL v2 preview aggregation from wb_finance_report_lines.

    Read-only. No changes to wb_financial_events or wb_sku_pnl_snapshots.

    Args:
        conn: DB connection
        project_id: Project ID
        period_from: Period start
        period_to: Period end
        nm_id: Filter by nm_id (optional)
        internal_sku: Filter by internal SKU via products.vendor_code_norm (optional)
        report_id: Filter by single report_id for testing (optional)

    Returns:
        Dict with aggregates, breakdown, and sample_rows.
    """
    params: Dict[str, Any] = {
        "project_id": project_id,
        "period_from": period_from,
        "period_to": period_to,
    }

    # nm_id / internal_sku filter (same pattern as db_discounts_preview)
    if nm_id is not None:
        params["nm_id_filter"] = nm_id
        nm_filter_sql = """AND (
            COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$'
            AND (COALESCE(r.payload->>'nm_id', r.payload->>'nmId')::bigint) = :nm_id_filter
        )"""
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
        nm_filter_sql = ""

    # When report_id is passed: filter ONLY by report_id (no period overlap).
    # When report_id is NOT passed: filter by period overlap.
    if report_id is not None:
        params["report_id"] = report_id
        report_filter_sql = "AND rf.report_id = :report_id"
        period_filter_sql = ""  # no period filter in report_id mode
    else:
        report_filter_sql = ""
        period_filter_sql = "AND rf.period_from <= :period_to AND rf.period_to >= :period_from"

    # sign: ILIKE '%Возврат%' for doc_type_name or supplier_oper_name
    sign_expr = """CASE
        WHEN COALESCE(r.payload->>'doc_type_name', r.payload->>'docTypeName') ILIKE '%Возврат%'
          OR COALESCE(r.payload->>'supplier_oper_name', r.payload->>'supplierOperName') ILIKE '%Возврат%'
        THEN -1
        ELSE 1
    END"""

    # Payload key helpers (snake + camel, known from event_mapping / WB API)
    # LOGISTICS: delivery_rub, rebill_logistic_cost, ppvz_reward, storage_fee, acceptance
    # OTHER: penalty, deduction, cashback_discount, additional_payment, sticker (Стикер МП)
    v_retail = _coalesce_num("retail_amount")
    v_vv_no = _coalesce_num("ppvz_vw")
    v_vv_nds = _coalesce_num("ppvz_vw_nds")
    v_acquiring = _coalesce_num("acquiring_fee")
    v_delivery = _coalesce_num("delivery_rub")
    v_rebill = _coalesce_num("rebill_logistic_cost")
    v_ppvz_reward = _coalesce_num("ppvz_reward")
    v_storage = _coalesce_num("storage_fee")
    v_acceptance = _coalesce_num("acceptance")
    v_penalty = _coalesce_num("penalty")
    v_deduction = _coalesce_num("deduction")
    v_cashback_discount = _coalesce_num("cashback_discount")
    v_additional = _coalesce_num("additional_payment")
    v_sticker = _coalesce_num("sticker_mp", "sticker_mp_fee", "sticker_fee")

    agg_sql = text(f"""
        WITH base AS (
            SELECT
                r.report_id,
                r.line_id,
                COALESCE(
                    (r.payload->>'sale_dt')::date,
                    (r.payload->>'saleDt')::date,
                    (r.payload->>'rr_dt')::date,
                    rf.period_to
                ) AS line_date,
                ({sign_expr})::int AS sign_val,
                {v_retail} AS retail_amount,
                {v_vv_no} AS vv_no_vat,
                {v_vv_nds} AS vv_vat,
                {v_acquiring} AS acquiring,
                {v_delivery} AS logistics_delivery,
                {v_rebill} AS logistics_transport,
                {v_ppvz_reward} AS logistics_pvz,
                {v_storage} AS logistics_storage,
                {v_acceptance} AS logistics_acceptance,
                {v_penalty} AS other_fines,
                {v_deduction} AS other_deductions,
                {v_cashback_discount} AS other_loyalty,
                {v_additional} AS other_vv_adjustment,
                {v_sticker} AS other_sticker
            FROM wb_finance_report_lines r
            JOIN wb_finance_reports rf ON rf.project_id = r.project_id
                AND rf.report_id = r.report_id
                AND rf.marketplace_code = 'wildberries'
            WHERE r.project_id = :project_id
              {period_filter_sql}
              {nm_filter_sql}
              {report_filter_sql}
        ),
        computed AS (
            SELECT
                *,
                retail_amount * sign_val AS sale_row,
                (vv_no_vat + vv_vat) AS commission_vv_row,
                (logistics_delivery + logistics_transport + logistics_pvz + logistics_storage + logistics_acceptance) AS logistics_total_row,
                (other_fines + other_deductions + other_loyalty + other_vv_adjustment + other_sticker) AS other_total_row
            FROM base
        ),
        with_transfer AS (
            SELECT
                *,
                (sale_row + commission_vv_row - acquiring) AS transfer_for_goods_row,
                (sale_row + commission_vv_row - acquiring)
                    - logistics_total_row - other_total_row AS total_to_pay_row
            FROM computed
        )
        SELECT
            COUNT(*)::bigint AS rows_total,
            COUNT(*) FILTER (WHERE retail_amount != 0)::bigint AS sale_rows_nonzero,
            COALESCE(SUM(sale_row), 0)::numeric AS sale,
            COALESCE(SUM(commission_vv_row), 0)::numeric AS commission_vv_signed,
            COALESCE(SUM(acquiring), 0)::numeric AS acquiring,
            COALESCE(SUM(logistics_delivery), 0)::numeric AS logistics_delivery,
            COALESCE(SUM(logistics_transport), 0)::numeric AS logistics_transport,
            COALESCE(SUM(logistics_pvz), 0)::numeric AS logistics_pvz,
            COALESCE(SUM(logistics_storage), 0)::numeric AS logistics_storage,
            COALESCE(SUM(logistics_acceptance), 0)::numeric AS logistics_acceptance,
            COALESCE(SUM(logistics_total_row), 0)::numeric AS logistics_total,
            COALESCE(SUM(other_fines), 0)::numeric AS other_fines,
            COALESCE(SUM(other_deductions), 0)::numeric AS other_deductions,
            COALESCE(SUM(other_loyalty), 0)::numeric AS other_loyalty,
            COALESCE(SUM(other_vv_adjustment), 0)::numeric AS other_vv_adjustment,
            COALESCE(SUM(other_sticker), 0)::numeric AS other_sticker,
            COALESCE(SUM(other_total_row), 0)::numeric AS other_total,
            COALESCE(SUM(transfer_for_goods_row), 0)::numeric AS transfer_for_goods,
            COALESCE(SUM(total_to_pay_row), 0)::numeric AS total_to_pay
        FROM with_transfer
    """)

    samples_sql = text(f"""
        WITH base AS (
            SELECT
                r.report_id,
                r.line_id,
                COALESCE(r.payload->>'doc_type_name', r.payload->>'docTypeName') AS doc_type_name,
                COALESCE(r.payload->>'supplier_oper_name', r.payload->>'supplierOperName') AS supplier_oper_name,
                COALESCE(
                    (r.payload->>'sale_dt')::date,
                    (r.payload->>'saleDt')::date,
                    (r.payload->>'rr_dt')::date,
                    rf.period_to
                ) AS line_date,
                ({sign_expr})::int AS sign_val,
                {v_retail} AS retail_amount,
                {v_vv_no} AS ppvz_vw,
                {v_vv_nds} AS ppvz_vw_nds,
                {v_acquiring} AS acquiring_fee,
                {v_delivery} AS logistics_delivery,
                {v_rebill} AS logistics_transport,
                {v_ppvz_reward} AS logistics_pvz,
                {v_storage} AS logistics_storage,
                {v_acceptance} AS logistics_acceptance,
                {v_penalty} AS other_fines,
                {v_deduction} AS other_deductions,
                {v_cashback_discount} AS other_loyalty,
                {v_additional} AS other_vv_adjustment,
                {v_sticker} AS other_sticker
            FROM wb_finance_report_lines r
            JOIN wb_finance_reports rf ON rf.project_id = r.project_id
                AND rf.report_id = r.report_id
                AND rf.marketplace_code = 'wildberries'
            WHERE r.project_id = :project_id
              {period_filter_sql}
              {nm_filter_sql}
              {report_filter_sql}
        ),
        computed AS (
            SELECT
                report_id, line_id, line_date,
                doc_type_name, supplier_oper_name,
                retail_amount, ppvz_vw, ppvz_vw_nds, acquiring_fee,
                retail_amount * sign_val AS sale_row,
                (ppvz_vw + ppvz_vw_nds) AS commission_vv_row,
                acquiring_fee AS acquiring_row,
                (logistics_delivery + logistics_transport + logistics_pvz + logistics_storage + logistics_acceptance) AS logistics_total_row,
                logistics_delivery, logistics_transport, logistics_pvz, logistics_storage, logistics_acceptance,
                (other_fines + other_deductions + other_loyalty + other_vv_adjustment + other_sticker) AS other_total_row,
                other_fines, other_deductions, other_loyalty, other_vv_adjustment, other_sticker,
                (retail_amount * sign_val + ppvz_vw + ppvz_vw_nds - acquiring_fee)
                    - (logistics_delivery + logistics_transport + logistics_pvz + logistics_storage + logistics_acceptance)
                    - (other_fines + other_deductions + other_loyalty + other_vv_adjustment + other_sticker)
                    AS total_to_pay_row
            FROM base
        )
        SELECT
            report_id, line_id, line_date,
            retail_amount, doc_type_name, supplier_oper_name,
            ppvz_vw, ppvz_vw_nds, acquiring_fee,
            sale_row, commission_vv_row, acquiring_row,
            logistics_total_row, logistics_delivery, logistics_transport, logistics_pvz, logistics_storage, logistics_acceptance,
            other_total_row, other_fines, other_deductions, other_loyalty, other_vv_adjustment, other_sticker,
            (sale_row + commission_vv_row - acquiring_row) AS transfer_for_goods_row,
            total_to_pay_row
        FROM computed
        ORDER BY line_date DESC NULLS LAST, report_id, line_id
        LIMIT 10
    """)

    agg_row = conn.execute(agg_sql, params).mappings().first()
    sample_rows = conn.execute(samples_sql, params).mappings().all()

    if not agg_row:
        return {
            "rows_total": 0,
            "sale_rows_nonzero": 0,
            "sale": 0.0,
            "commission_vv_signed": 0.0,
            "transfer_for_goods": 0.0,
            "acquiring": 0.0,
            "logistics_delivery": 0.0,
            "logistics_transport": 0.0,
            "logistics_pvz": 0.0,
            "logistics_storage": 0.0,
            "logistics_acceptance": 0.0,
            "logistics_total": 0.0,
            "other_fines": 0.0,
            "other_deductions": 0.0,
            "other_loyalty": 0.0,
            "other_vv_adjustment": 0.0,
            "other_sticker": 0.0,
            "other_total": 0.0,
            "total_to_pay": 0.0,
            "wb_total_cost_actual": 0.0,
            "wb_total_cost_pct_of_sale": None,
            "retail_price": None,
            "reconciliation": {
                "transfer_expected": 0.0,
                "transfer_delta": 0.0,
                "wb_cost_expected": 0.0,
                "wb_cost_delta": 0.0,
            },
            "sample_rows": [],
        }

    sale_val = float(agg_row["sale"] or 0)
    commission_vv = float(agg_row["commission_vv_signed"] or 0)
    acquiring_val = float(agg_row["acquiring"] or 0)
    logistics_total_val = float(agg_row["logistics_total"] or 0)
    other_total_val = float(agg_row["other_total"] or 0)
    transfer_from_rows = float(agg_row["transfer_for_goods"] or 0)

    # Exact formulas from spec (no per-row sum rounding)
    transfer_expected = sale_val + commission_vv - acquiring_val
    transfer_for_goods_val = transfer_expected
    wb_cost_expected = (-commission_vv) + acquiring_val + logistics_total_val + other_total_val
    wb_total_cost_val = wb_cost_expected
    total_to_pay_val = transfer_for_goods_val - logistics_total_val - other_total_val

    # Reconciliation: delta between sum-of-rows and formula
    transfer_delta = transfer_from_rows - transfer_expected
    wb_cost_delta = 0.0  # wb_total_cost_actual from formula

    wb_cost_pct = (wb_total_cost_val / sale_val) if sale_val > 0 else None

    def _row_dict(r: Any) -> Dict[str, Any]:
        d = dict(r)
        for k, v in d.items():
            if isinstance(v, Decimal):
                d[k] = float(v)
            elif hasattr(v, "isoformat"):
                d[k] = v.isoformat() if v else None
        return d

    return {
        "rows_total": int(agg_row["rows_total"] or 0),
        "sale_rows_nonzero": int(agg_row["sale_rows_nonzero"] or 0),
        "sale": sale_val,
        "commission_vv_signed": commission_vv,
        "transfer_for_goods": transfer_for_goods_val,
        "acquiring": acquiring_val,
        "logistics_delivery": float(agg_row["logistics_delivery"] or 0),
        "logistics_transport": float(agg_row["logistics_transport"] or 0),
        "logistics_pvz": float(agg_row["logistics_pvz"] or 0),
        "logistics_storage": float(agg_row["logistics_storage"] or 0),
        "logistics_acceptance": float(agg_row["logistics_acceptance"] or 0),
        "logistics_total": float(agg_row["logistics_total"] or 0),
        "other_fines": float(agg_row["other_fines"] or 0),
        "other_deductions": float(agg_row["other_deductions"] or 0),
        "other_loyalty": float(agg_row["other_loyalty"] or 0),
        "other_vv_adjustment": float(agg_row["other_vv_adjustment"] or 0),
        "other_sticker": float(agg_row["other_sticker"] or 0),
        "other_total": other_total_val,
        "total_to_pay": total_to_pay_val,
        "wb_total_cost_actual": wb_total_cost_val,
        "wb_total_cost_pct_of_sale": wb_cost_pct,
        "retail_price": None,
        "reconciliation": {
            "transfer_expected": transfer_expected,
            "transfer_delta": transfer_delta,
            "wb_cost_expected": wb_cost_expected,
            "wb_cost_delta": wb_cost_delta,
        },
        "sample_rows": [_row_dict(r) for r in sample_rows],
    }
