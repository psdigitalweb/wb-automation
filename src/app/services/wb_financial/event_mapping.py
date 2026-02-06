"""WB payload field -> event_type mapping.

Based on WB API reportDetailByPeriod official documentation.
Amount is signed passthrough - no abs(), no sign change.
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

# Format: (list of payload key aliases, event_type, scope)
# First matching key wins. source_field = the alias actually used.
# Amount is signed passthrough.
# scope='sku' when nm_id present (builder override); else use mapping scope.
FIELD_TO_EVENT: List[Tuple[List[str], str, str]] = [
    # --- SKU events (scope sku when nm_id present) ---
    (["retail_amount", "retailAmount"], "sale_gmv", "sku"),
    (["ppvz_vw", "ppvzVw"], "wb_commission_no_vat", "sku"),
    (["ppvz_vw_nds", "ppvzVwNds"], "wb_commission_vat", "sku"),
    (["ppvz_sales_commission", "ppvzSalesCommission"], "wb_sales_commission_excl_services_no_vat", "sku"),
    (["acquiring_fee", "acquiringFee"], "acquiring_fee", "sku"),
    (["delivery_rub", "deliveryRub"], "delivery_fee", "sku"),
    (["rebill_logistic_cost", "rebillLogisticCost"], "rebill_logistics_cost", "sku"),
    (["ppvz_reward", "ppvzReward"], "pvz_issue_return_compensation", "sku"),
    # --- Control metric (reconciliation only, not PnL) ---
    (["ppvz_for_pay", "ppvzForPay"], "net_payable_to_seller_per_item", "sku"),
    # --- Project events (scope project when nm_id absent) ---
    (["storage_fee", "storageFee"], "storage_fee", "project"),
    (["penalty", "penalty"], "penalty_total", "project"),
    (["deduction", "deduction"], "deduction", "project"),
    (["acceptance", "acceptance"], "acceptance_fee", "project"),
    (["additional_payment", "additionalPayment"], "wb_commission_correction", "project"),
    (["installment_cofinancing_amount", "installmentCofinancingAmount"], "installment_cofinancing_discount", "project"),
    (["cashback_amount", "cashbackAmount"], "cashback_withheld", "project"),
    (["cashback_discount", "cashbackDiscount"], "cashback_discount_compensation", "project"),
    (["cashback_commission_change", "cashbackCommissionChange"], "cashback_program_fee", "project"),
    (["payment_schedule", "paymentSchedule"], "payout_timing_fee", "project"),
]

# Keys excluded from unmapped money candidates (percent/ID/qty noise)
NON_MONEY_KEYS = frozenset(
    [
        "nm_id", "nmId", "rrd_id", "rrdId", "realizationreport_id", "realizationReportId",
        "quantity", "qty", "quantity_doc", "percent", "commission_percent",
        "commissionPercent", "id", "doc_number", "docNumber", "supplier_oper_name",
        "seller_oper_name", "operation_type", "supplierOperName", "sellerOperName",
        "operationType", "srid", "rid", "sticker_id", "stickerId", "gi_id", "giId",
        "subject_name", "subjectName", "brand_name", "brandName", "ts_name", "tsName",
        "barcode", "doc_type_name", "docTypeName", "office_name", "officeName",
        "sale_dt", "saleDt", "order_dt", "orderDt", "rr_dt", "rrDt",  # date fields
    ]
)


def resolve_amount_for_event(payload: dict, aliases: List[str]) -> Tuple[Optional[float], Optional[str]]:
    """Get first existing numeric value for given alias group.
    Returns (amount, source_field) or (None, None).
    Amount is signed passthrough - no transformations.
    """
    for key in aliases:
        v = payload.get(key)
        if v is None:
            continue
        try:
            if isinstance(v, (int, float)):
                return (float(v), key)
            if isinstance(v, str):
                s = v.replace(",", ".").replace(" ", "").strip()
                if s:
                    return (float(s), key)
        except (ValueError, TypeError):
            continue
    return (None, None)
