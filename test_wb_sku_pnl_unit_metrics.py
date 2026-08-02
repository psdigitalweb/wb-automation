from decimal import Decimal
from datetime import date

import pytest

from app import db_wb_unit_pnl
from app.db_wb_unit_pnl import compute_extended_unit_metrics, compute_wb_take_signed, prorate_amount_by_overlap
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


def test_unit_pnl_prorates_additional_cost_by_period_overlap():
    amount = prorate_amount_by_overlap(
        30000,
        date(2026, 6, 15),
        date(2026, 7, 14),
        date(2026, 7, 1),
        date(2026, 7, 31),
    )

    assert amount == Decimal("14000")


def test_unit_pnl_extended_metrics_include_packaging_and_additional_costs():
    metrics = compute_extended_unit_metrics(
        fact_price_avg=1000,
        wb_total_cost_per_unit=200,
        cogs_per_unit=300,
        packaging_cost_per_unit=50,
        additional_costs_per_unit=25,
        sales_cnt=10,
    )

    assert metrics["full_profit_per_unit"] == 425.0
    assert metrics["full_profit_total"] == 4250.0
    assert metrics["full_margin_pct_of_revenue"] == 42.5


def test_unit_pnl_wb_take_signed_allows_negative_compensation():
    total = compute_wb_take_signed(
        commission_vv_signed=-150,
        acquiring=25,
        logistics_cost=100,
        storage_cost=50,
        acceptance_cost=10,
        other_withholdings=20,
        penalties=5,
    )

    assert total == 60.0


def test_unit_pnl_tax_profile_transfer_minus_vat_wb_cogs():
    class FakeResult:
        def mappings(self):
            return self

        def first(self):
            return {
                "model_code": "wb_transfer_minus_vat_wb_cogs_tax",
                "params_json": {"vat_rate": "0.047619047619047616", "tax_rate": "0.15"},
            }

    class FakeConn:
        def execute(self, sql, params):
            self.sql = str(sql)
            self.params = params
            return FakeResult()

    result = db_wb_unit_pnl._compute_unit_pnl_tax_header(
        FakeConn(),
        1,
        transfer_for_goods=105000,
        wb_total_signed=20000,
        cogs_cost_total=30000,
    )

    assert result["tax_vat_amount"] == pytest.approx(5000.0)
    assert result["tax_base"] == pytest.approx(50000.0)
    assert result["tax_profit_amount"] == pytest.approx(7500.0)
    assert result["tax_expense_total"] == pytest.approx(7500.0)


def test_unit_pnl_extended_metrics_missing_packaging_keeps_full_profit_unknown():
    metrics = compute_extended_unit_metrics(
        fact_price_avg=1000,
        wb_total_cost_per_unit=200,
        cogs_per_unit=300,
        packaging_cost_per_unit=None,
        additional_costs_per_unit=0,
        sales_cnt=10,
    )

    assert metrics["full_profit_per_unit"] is None
    assert metrics["full_profit_total"] is None
    assert metrics["full_margin_pct_of_revenue"] is None


def test_unit_pnl_allocates_warehouse_labor_as_additional_cost(monkeypatch):
    monkeypatch.setattr(
        db_wb_unit_pnl,
        "_fetch_packaging_costs",
        lambda conn, project_id, sku_norms, as_of_date: {"sku-1": 10.0, "sku-2": 10.0},
    )
    monkeypatch.setattr(
        db_wb_unit_pnl,
        "_fetch_product_additional_costs",
        lambda conn, project_id, sku_norms, scope_from, scope_to: {},
    )
    monkeypatch.setattr(
        db_wb_unit_pnl,
        "_fetch_marketplace_additional_total",
        lambda conn, project_id, scope_from, scope_to: 0.0,
    )
    monkeypatch.setattr(
        db_wb_unit_pnl,
        "_fetch_warehouse_labor_total",
        lambda conn, project_id, scope_from, scope_to: 3000.0,
    )

    items = [
        {
            "internal_sku": "sku-1",
            "sales_cnt": 10,
            "sale_amount": 1000.0,
            "fact_price_avg": 100.0,
            "wb_total_cost_per_unit": 10.0,
            "cogs_per_unit": 20.0,
        },
        {
            "internal_sku": "sku-2",
            "sales_cnt": 20,
            "sale_amount": 2000.0,
            "fact_price_avg": 100.0,
            "wb_total_cost_per_unit": 10.0,
            "cogs_per_unit": 20.0,
        },
    ]

    totals = db_wb_unit_pnl.apply_extended_costs(
        object(),
        1,
        items,
        scope_from=date(2026, 3, 1),
        scope_to=date(2026, 3, 31),
        as_of_date=date(2026, 3, 31),
    )

    assert totals["warehouse_labor_costs_total"] == 3000.0
    assert totals["additional_costs_total"] == 3000.0
    assert totals["cogs_missing_count"] == 0
    assert totals["packaging_missing_count"] == 0
    assert items[0]["extended_costs"]["warehouse_labor_costs_total"] == pytest.approx(1000.0)
    assert items[1]["extended_costs"]["warehouse_labor_costs_total"] == pytest.approx(2000.0)
    assert items[0]["additional_costs_per_unit"] == pytest.approx(100.0)
    assert items[1]["additional_costs_per_unit"] == pytest.approx(100.0)


def test_unit_pnl_counts_missing_cogs_and_packaging(monkeypatch):
    monkeypatch.setattr(
        db_wb_unit_pnl,
        "_fetch_packaging_costs",
        lambda conn, project_id, sku_norms, as_of_date: {"sku-1": None},
    )
    monkeypatch.setattr(
        db_wb_unit_pnl,
        "_fetch_product_additional_costs",
        lambda conn, project_id, sku_norms, scope_from, scope_to: {},
    )
    monkeypatch.setattr(
        db_wb_unit_pnl,
        "_fetch_marketplace_additional_total",
        lambda conn, project_id, scope_from, scope_to: 0.0,
    )
    monkeypatch.setattr(
        db_wb_unit_pnl,
        "_fetch_warehouse_labor_total",
        lambda conn, project_id, scope_from, scope_to: 0.0,
    )

    items = [{
        "internal_sku": "sku-1",
        "sales_cnt": 1,
        "sale_amount": 100.0,
        "fact_price_avg": 100.0,
        "wb_total_cost_per_unit": 10.0,
        "cogs_per_unit": None,
        "cogs_missing": True,
    }]

    totals = db_wb_unit_pnl.apply_extended_costs(
        object(),
        1,
        items,
        scope_from=date(2026, 3, 1),
        scope_to=date(2026, 3, 31),
        as_of_date=date(2026, 3, 31),
    )

    assert totals["cogs_missing_count"] == 1
    assert totals["packaging_missing_count"] == 1
    assert totals["full_profit_total"] is None


def test_unit_pnl_warehouse_labor_includes_common_marketplace_rows():
    class FakeResult:
        def scalar(self):
            return Decimal("6000.00")

    class FakeConn:
        def __init__(self):
            self.sql = ""

        def execute(self, sql, params):
            self.sql = str(sql)
            self.params = params
            return FakeResult()

    conn = FakeConn()

    total = db_wb_unit_pnl._fetch_warehouse_labor_total(
        conn,
        project_id=1,
        scope_from=date(2026, 3, 23),
        scope_to=date(2026, 3, 29),
    )

    assert total == 6000.0
    assert "d.marketplace_code = 'wildberries'" in conn.sql
    assert "d.marketplace_code IS NULL" in conn.sql
    assert "d.marketplace_code = ''" in conn.sql

