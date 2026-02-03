from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional


def _to_decimal(v: object) -> Optional[Decimal]:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    try:
        # Use str() to avoid float binary artifacts as much as possible.
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None


def safe_div(n: Decimal, d: Decimal) -> Optional[Decimal]:
    if d == 0:
        return None
    return n / d


def abs_cost(v: object) -> Decimal:
    """Normalize a WB cost component to a positive Decimal (absolute value)."""
    dv = _to_decimal(v) or Decimal("0")
    return abs(dv)


def wb_total_total_abs(
    *,
    wb_commission_no_vat: object,
    wb_commission_vat: object,
    acquiring_fee: object,
    delivery_fee: object,
    rebill_logistics_cost: object,
    pvz_fee: object,
) -> Decimal:
    """WB total costs as ABS-sum of all WB expense components (always >= 0)."""
    return (
        abs_cost(wb_commission_no_vat)
        + abs_cost(wb_commission_vat)
        + abs_cost(acquiring_fee)
        + abs_cost(delivery_fee)
        + abs_cost(rebill_logistics_cost)
        + abs_cost(pvz_fee)
    )


@dataclass(frozen=True)
class SkuPnlUnitMetrics:
    avg_price_realization_unit: Optional[Decimal]
    wb_total_unit: Optional[Decimal]
    income_before_cogs_unit: Optional[Decimal]
    income_before_cogs_pct_rrp: Optional[Decimal]
    profit_unit: Optional[Decimal]
    margin_pct_unit: Optional[Decimal]
    profit_pct_rrp: Optional[Decimal]
    wb_total_pct_rrp: Optional[Decimal]


def compute_unit_metrics(
    *,
    avg_price_realization_unit: object,
    wb_total_unit: object,
    cogs_unit: object,
    rrp: object,
) -> SkuPnlUnitMetrics:
    """Compute unit KPI metrics using a single consistent definition.

    Definitions:
      - profit_unit = avg_price_realization_unit - wb_total_unit - cogs_unit
      - margin_pct_unit = profit_unit / avg_price_realization_unit * 100
      - profit_pct_rrp = profit_unit / rrp * 100
      - income_before_cogs_unit = avg_price_realization_unit - wb_total_unit
      - income_before_cogs_pct_rrp = income_before_cogs_unit / rrp * 100
    """
    avg = _to_decimal(avg_price_realization_unit)
    wb_u = _to_decimal(wb_total_unit)
    cogs = _to_decimal(cogs_unit)
    rrp_d = _to_decimal(rrp)

    income_before = None if (avg is None or wb_u is None) else (avg - wb_u)
    profit = None if (income_before is None or cogs is None) else (income_before - cogs)

    margin_pct = None
    if profit is not None and avg is not None and avg != 0:
        margin_pct = (profit / avg) * Decimal("100")

    profit_pct_rrp = None
    if profit is not None and rrp_d is not None and rrp_d != 0:
        profit_pct_rrp = (profit / rrp_d) * Decimal("100")

    income_before_pct_rrp = None
    if income_before is not None and rrp_d is not None and rrp_d != 0:
        income_before_pct_rrp = (income_before / rrp_d) * Decimal("100")

    wb_total_pct_rrp = None
    if wb_u is not None and rrp_d is not None and rrp_d != 0:
        wb_total_pct_rrp = (wb_u / rrp_d) * Decimal("100")

    return SkuPnlUnitMetrics(
        avg_price_realization_unit=avg,
        wb_total_unit=wb_u,
        income_before_cogs_unit=income_before,
        income_before_cogs_pct_rrp=income_before_pct_rrp,
        profit_unit=profit,
        margin_pct_unit=margin_pct,
        profit_pct_rrp=profit_pct_rrp,
        wb_total_pct_rrp=wb_total_pct_rrp,
    )

