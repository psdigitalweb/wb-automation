"""WB payload field -> event_type mapping.

TODO: Fill after introspection. Run:
  python scripts/introspect_wb_finance_payload.py --project-id <id>

Currently only structural/identifier keys that are known from existing code.
Money fields will be added after introspection.
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple

# Format: (list of payload key aliases, event_type, scope)
# First matching key wins. source_field = the alias actually used.
# Amount is signed passthrough - no abs(), no *-1.
FIELD_TO_EVENT: List[Tuple[List[str], str, str]] = [
    # TODO: fill after introspection - add money fields from introspection report
    # Example once keys are known:
    # (["retail_amount_for_pay", "retailAmountForPay"], "sale_income", "sku"),
    # (["commission_percent", "commissionPercent"], "wb_commission", "sku"),  # if derived to amount
    # (["logistics_fee", "logisticsFee"], "logistics_fee", "sku"),
    # (["storage_fee", "storageFee"], "storage_fee", "project"),
    # (["penalty", "штраф"], "penalty", "project"),
]

# Keys that are NOT money (exclude from unmapped diagnostics)
NON_MONEY_KEYS = frozenset(
    [
        "nm_id", "nmId", "rrd_id", "rrdId", "realizationreport_id", "realizationReportId",
        "quantity", "qty", "quantity_doc", "percent", "commission_percent", "commissionPercent",
        "id", "doc_number", "supplier_oper_name", "seller_oper_name", "operation_type",
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
