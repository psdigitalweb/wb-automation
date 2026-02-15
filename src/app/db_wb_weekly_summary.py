"""Read-only Weekly Summary aggregate for WB reports.

Matches WB Excel/header totals exactly.
Source: wb_finance_report_lines filtered by report_id.
Sign flip for returns ONLY on SALE (retail_amount) and TRANSFER (ppvz_for_pay).

Field mapping (WB header -> payload key):
  retail_amount     -> "Вайлдберриз реализовал Товар (Пр)"
  ppvz_for_pay      -> "К перечислению Продавцу за реализованный Товар"
  delivery_rub       -> "Услуги по доставке товара покупателю"
  storage_fee        -> "Хранение"
  acceptance         -> "Операции на приемке"
  deduction          -> "Удержания"
  penalty            -> "Общая сумма штрафов"
  cashback_discount  -> "Компенсация скидки по программе лояльности"
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection


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


def get_wb_weekly_summary(
    conn: Connection,
    project_id: int,
    report_id: int,
) -> Dict[str, Any]:
    """Get Weekly Summary aggregate for a single WB report.

    Matches WB header/Excel totals. Filter: report_id only, no period filters.

    Args:
        conn: DB connection
        project_id: Project ID
        report_id: WB report ID (realizationreport_id)

    Returns:
        Dict with SALE, TRANSFER_FOR_GOODS, LOGISTICS_COST, etc. and sample_rows.
    """
    params: Dict[str, Any] = {"project_id": project_id, "report_id": report_id}

    # Sign: flip only for returns (doc_type or supplier_oper contains 'Возврат')
    sign_expr = """CASE
        WHEN COALESCE(r.payload->>'doc_type_name', r.payload->>'docTypeName') ILIKE '%Возврат%'
          OR COALESCE(r.payload->>'supplier_oper_name', r.payload->>'supplierOperName') ILIKE '%Возврат%'
        THEN -1
        ELSE 1
    END"""

    v_retail = _coalesce_num("retail_amount")
    v_transfer = _coalesce_num("ppvz_for_pay")
    v_delivery = _coalesce_num("delivery_rub")
    v_storage = _coalesce_num("storage_fee")
    v_acceptance = _coalesce_num("acceptance")
    v_deduction = _coalesce_num("deduction")
    v_penalty = _coalesce_num("penalty")
    v_cashback = _coalesce_num("cashback_discount")

    # Single query: all sums + debug aggregates from one selection (same WHERE, same CTE)
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
                COALESCE(r.payload->>'doc_type_name', r.payload->>'docTypeName') AS doc_type_name,
                COALESCE(r.payload->>'supplier_oper_name', r.payload->>'supplierOperName') AS supplier_oper_name,
                ({sign_expr})::int AS sign_val,
                {v_retail} AS retail_amount,
                {v_transfer} AS transfer_field,
                {v_delivery} AS delivery_rub,
                {v_storage} AS storage_fee,
                {v_acceptance} AS acceptance,
                {v_deduction} AS deduction,
                {v_penalty} AS penalty,
                {v_cashback} AS cashback_discount
            FROM wb_finance_report_lines r
            JOIN wb_finance_reports rf ON rf.project_id = r.project_id
                AND rf.report_id = r.report_id
                AND rf.marketplace_code = 'wildberries'
            WHERE r.project_id = :project_id
              AND rf.report_id = :report_id
        ),
        signed AS (
            SELECT
                *,
                retail_amount * sign_val AS sale_row,
                transfer_field * sign_val AS transfer_row
            FROM base
        )
        SELECT
            COUNT(*)::bigint AS rows_total,
            COALESCE(SUM(retail_amount), 0)::numeric AS sum_retail_raw,
            COALESCE(SUM(sale_row), 0)::numeric AS sum_sale_signed,
            COALESCE(SUM(transfer_field), 0)::numeric AS sum_transfer_raw,
            COALESCE(SUM(transfer_row), 0)::numeric AS sum_transfer_signed,
            COALESCE(SUM(delivery_rub), 0)::numeric AS logistics_cost,
            COALESCE(SUM(storage_fee), 0)::numeric AS storage_cost,
            COALESCE(SUM(acceptance), 0)::numeric AS acceptance_cost,
            COALESCE(SUM(deduction), 0)::numeric AS other_withholdings,
            COALESCE(SUM(penalty), 0)::numeric AS penalties,
            COALESCE(SUM(cashback_discount), 0)::numeric AS loyalty_comp_display,
            COALESCE(SUM(CASE WHEN deduction > 0 THEN deduction ELSE 0 END), 0)::numeric AS deduction_pos_sum,
            COALESCE(SUM(CASE WHEN deduction < 0 THEN deduction ELSE 0 END), 0)::numeric AS deduction_neg_sum,
            COALESCE(SUM(CASE WHEN penalty > 0 THEN penalty ELSE 0 END), 0)::numeric AS penalty_pos_sum,
            COALESCE(SUM(CASE WHEN penalty < 0 THEN penalty ELSE 0 END), 0)::numeric AS penalty_neg_sum
        FROM signed
    """)

    # Same base/signed logic as agg, only LIMIT for display
    samples_sql = text(f"""
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
                COALESCE(r.payload->>'doc_type_name', r.payload->>'docTypeName') AS doc_type_name,
                COALESCE(r.payload->>'supplier_oper_name', r.payload->>'supplierOperName') AS supplier_oper_name,
                ({sign_expr})::int AS sign_val,
                {v_retail} AS retail_amount,
                {v_transfer} AS transfer_field,
                {v_delivery} AS delivery_rub,
                {v_storage} AS storage_fee,
                {v_acceptance} AS acceptance,
                {v_deduction} AS deduction,
                {v_penalty} AS penalty,
                {v_cashback} AS cashback_discount
            FROM wb_finance_report_lines r
            JOIN wb_finance_reports rf ON rf.project_id = r.project_id
                AND rf.report_id = r.report_id
                AND rf.marketplace_code = 'wildberries'
            WHERE r.project_id = :project_id
              AND rf.report_id = :report_id
        ),
        signed AS (
            SELECT
                *,
                retail_amount * sign_val AS sale_row,
                transfer_field * sign_val AS transfer_row,
                (CASE WHEN sign_val = -1 THEN true ELSE false END) AS is_return
            FROM base
        )
        SELECT
            report_id, line_id, line_date,
            doc_type_name, supplier_oper_name,
            retail_amount,
            transfer_field AS ppvz_for_pay,
            delivery_rub, storage_fee, acceptance,
            deduction, penalty, cashback_discount,
            is_return, sale_row, transfer_row
        FROM signed
        ORDER BY line_id
        LIMIT 20
    """)

    agg_row = conn.execute(agg_sql, params).mappings().first()
    sample_rows = conn.execute(samples_sql, params).mappings().all()

    if not agg_row:
        return {
            "field_mapping": _FIELD_MAPPING,
            "rows_total": 0,
            "sale": 0.0,
            "transfer_for_goods": 0.0,
            "logistics_cost": 0.0,
            "storage_cost": 0.0,
            "acceptance_cost": 0.0,
            "other_withholdings": 0.0,
            "penalties": 0.0,
            "loyalty_comp_display": 0.0,
            "total_to_pay": 0.0,
            "reconciliation": {
                "transfer_expected": 0.0,
                "transfer_delta": 0.0,
                "total_to_pay_expected": 0.0,
                "total_to_pay_delta": 0.0,
            },
            "debug": {
                "sum_retail_raw": 0.0,
                "sum_sale_signed": 0.0,
                "sum_transfer_raw": 0.0,
                "sum_transfer_signed": 0.0,
                "deduction_pos_sum": 0.0,
                "deduction_neg_sum": 0.0,
                "penalty_pos_sum": 0.0,
                "penalty_neg_sum": 0.0,
            },
            "sample_rows": [],
        }

    # All from same agg_row (one selection)
    sale_val = float(agg_row["sum_sale_signed"] or 0)
    transfer_val = float(agg_row["sum_transfer_signed"] or 0)
    logistics_val = float(agg_row["logistics_cost"] or 0)
    storage_val = float(agg_row["storage_cost"] or 0)
    acceptance_val = float(agg_row["acceptance_cost"] or 0)
    other_val = float(agg_row["other_withholdings"] or 0)
    penalties_val = float(agg_row["penalties"] or 0)
    loyalty_val = float(agg_row["loyalty_comp_display"] or 0)

    # TOTAL_TO_PAY = TRANSFER_FOR_GOODS - LOGISTICS - STORAGE - ACCEPTANCE - OTHER - PENALTIES
    total_to_pay_expected = (
        transfer_val - logistics_val - storage_val - acceptance_val - other_val - penalties_val
    )
    total_to_pay = total_to_pay_expected
    total_to_pay_delta = total_to_pay - total_to_pay_expected  # always 0

    # Transfer reconciliation: transfer_expected = transfer_for_goods, delta = 0
    transfer_expected = transfer_val
    transfer_delta = transfer_val - transfer_expected  # always 0

    def _row_dict(r: Any) -> Dict[str, Any]:
        d = dict(r)
        for k, v in d.items():
            if isinstance(v, Decimal):
                d[k] = float(v)
            elif hasattr(v, "isoformat") and not isinstance(v, (str, bytes)):
                d[k] = v.isoformat() if v else None
        return d

    return {
        "field_mapping": _FIELD_MAPPING,
        "rows_total": int(agg_row["rows_total"] or 0),
        "sale": sale_val,
        "transfer_for_goods": transfer_val,
        "logistics_cost": logistics_val,
        "storage_cost": storage_val,
        "acceptance_cost": acceptance_val,
        "other_withholdings": other_val,
        "penalties": penalties_val,
        "loyalty_comp_display": loyalty_val,
        "total_to_pay": total_to_pay,
        "reconciliation": {
            "transfer_expected": transfer_expected,
            "transfer_delta": transfer_delta,
            "total_to_pay_expected": total_to_pay_expected,
            "total_to_pay_delta": total_to_pay_delta,
        },
        "debug": {
            "sum_retail_raw": float(agg_row["sum_retail_raw"] or 0),
            "sum_sale_signed": float(agg_row["sum_sale_signed"] or 0),
            "sum_transfer_raw": float(agg_row["sum_transfer_raw"] or 0),
            "sum_transfer_signed": float(agg_row["sum_transfer_signed"] or 0),
            "deduction_pos_sum": float(agg_row.get("deduction_pos_sum") or 0),
            "deduction_neg_sum": float(agg_row.get("deduction_neg_sum") or 0),
            "penalty_pos_sum": float(agg_row.get("penalty_pos_sum") or 0),
            "penalty_neg_sum": float(agg_row.get("penalty_neg_sum") or 0),
        },
        "sample_rows": [_row_dict(r) for r in sample_rows],
    }


_FIELD_MAPPING = {
    "retail_amount": "Вайлдберриз реализовал Товар (Пр)",
    "ppvz_for_pay": "К перечислению Продавцу за реализованный Товар",
    "delivery_rub": "Услуги по доставке товара покупателю",
    "storage_fee": "Хранение",
    "acceptance": "Операции на приемке",
    "deduction": "Удержания",
    "penalty": "Общая сумма штрафов",
    "cashback_discount": "Компенсация скидки по программе лояльности",
}
