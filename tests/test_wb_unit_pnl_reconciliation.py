from decimal import Decimal

import pytest

from app.db_wb_unit_pnl import (
    compute_extended_unit_metrics,
    compute_wb_payout_reconciliation,
)


def test_payout_reconciliation_uses_sale_to_transfer_gap() -> None:
    result = compute_wb_payout_reconciliation(
        sale_amount=Decimal("8487.00"),
        transfer_amount=Decimal("6305.05"),
        commission_vv_signed=Decimal("1521.6057377049180388"),
        acquiring=Decimal("315.58"),
        pvz_reward=Decimal("280.818"),
        rebill_logistic_cost=Decimal("63.90"),
    )

    assert result["settlement_total"] == pytest.approx(2181.95)
    assert result["component_total"] == pytest.approx(2181.903737704918)
    assert result["settlement_adjustment"] == pytest.approx(0.046262295082)


def test_full_margin_uses_reconciled_wb_cost_per_unit() -> None:
    quantity = Decimal("13")
    fact_price = Decimal("8487") / quantity
    common_wb_allocated = Decimal("49.6549210421774")
    wb_total = Decimal("2181.95") + Decimal("1477.81") + common_wb_allocated
    wb_per_unit = wb_total / quantity

    result = compute_extended_unit_metrics(
        fact_price_avg=fact_price,
        wb_total_cost_per_unit=wb_per_unit,
        cogs_per_unit=Decimal("239.60"),
        packaging_cost_per_unit=Decimal("19.00"),
        additional_costs_per_unit=Decimal("0"),
        sales_cnt=13,
    )

    assert wb_per_unit == pytest.approx(Decimal("285.3396093109367"))
    assert result["full_profit_per_unit"] == pytest.approx(108.90654453521707)
    assert result["full_margin_pct_of_revenue"] == pytest.approx(16.681808400587038)
