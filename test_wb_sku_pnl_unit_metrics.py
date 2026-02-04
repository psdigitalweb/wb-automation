from decimal import Decimal

import pytest

from app.services.wb_financial.sku_pnl_metrics import compute_unit_metrics


def test_sku_pnl_unit_metrics_example_from_ticket():
    m = compute_unit_metrics(
        avg_price_realization_unit=1457,
        wb_total_unit=1230.24,
        cogs_unit=999.6,
        rrp=2499,
    )

    # Given example:
    # 1457 - 1230.24 - 999.6 = -772.84
    assert m.profit_unit == Decimal("-772.84")

    assert float(m.margin_pct_unit) == pytest.approx(-53.05, abs=0.02)
    assert float(m.profit_pct_rrp) == pytest.approx(-30.93, abs=0.02)

