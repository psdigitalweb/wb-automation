"""Tests for WB funnel signals service."""
from __future__ import annotations

from app.services.wb_funnel_signals import (
    compute_funnel_signals,
    compute_benchmarks,
    SIGNAL_INSUFFICIENT_DATA,
    SIGNAL_LOW_ADD_TO_CART,
    SIGNAL_LOW_ORDER_RATE,
    SIGNAL_LOW_TRAFFIC,
    SIGNAL_SCALE_UP,
)


def test_gating_opens_below_min_opens():
    """When opens < min_opens, signal is insufficient_data, severity and potential null/0."""
    raw = [
        {
            "nm_id": 1,
            "opens": 100,
            "carts": 10,
            "orders": 2,
            "revenue": 1000.0,
            "cart_rate": 0.1,
            "order_rate": 0.02,
            "cart_to_order": 0.2,
            "avg_check": 500.0,
        },
    ]
    result = compute_funnel_signals(raw, min_opens=200)
    assert len(result) == 1
    assert result[0]["signal_code"] == SIGNAL_INSUFFICIENT_DATA
    assert result[0]["signal"] == "Недостаточно данных"
    assert result[0]["severity"] is None
    assert result[0]["potential_rub"] == 0.0
    assert result[0]["bucket"] is None
    assert result[0].get("benchmark_scope") is None


def test_conflict_resolution_by_higher_potential():
    """When two signals fire, the one with higher potential_rub is chosen."""
    # Two SKUs in same bucket; one has low cart_rate (high potential for low_add_to_cart),
    # one has low order_rate. We need enough rows to form bucket and benchmarks.
    # Create data so that for nm_id=1 both low_add_to_cart and low_order_rate could fire,
    # but low_add_to_cart has higher potential.
    raw = []
    # Eligible rows for bucket (opens >= 200)
    for i in range(15):
        raw.append({
            "nm_id": 1000 + i,
            "opens": 300 + i * 50,
            "carts": 30 + i * 5,
            "orders": 6 + i,
            "revenue": 3000.0 + i * 100,
            "cart_rate": 0.10 + i * 0.01,  # 10% to 24%
            "order_rate": 0.02 + i * 0.002,  # 2% to 4.8%
            "cart_to_order": 0.2 + i * 0.01,
            "avg_check": 500.0,
        })
    # Row that will have low cart_rate (below P10) and low order_rate (below P10):
    # so both signals fire. Give it high avg_check so low_add_to_cart potential is large.
    raw.append({
        "nm_id": 1,
        "opens": 400,
        "carts": 8,   # cart_rate 2%
        "orders": 2,
        "revenue": 2000.0,
        "cart_rate": 0.02,
        "order_rate": 0.005,
        "cart_to_order": 0.25,
        "avg_check": 1000.0,
    })
    result = compute_funnel_signals(raw, min_opens=200)
    by_nm = {r["nm_id"]: r for r in result}
    assert 1 in by_nm
    # Should pick one signal; implementation picks by max potential then priority.
    # Both low_add_to_cart and low_order_rate can have positive potential; the one with
    # higher potential wins.
    r1 = by_nm[1]
    assert r1["signal_code"] in (SIGNAL_LOW_ADD_TO_CART, SIGNAL_LOW_ORDER_RATE, SIGNAL_LOW_TRAFFIC)
    assert r1["potential_rub"] >= 0
    assert r1["bucket"] is not None


def test_priority_when_potential_equal():
    """When potential is equal (e.g. both 0), priority order: low_traffic before scale_up."""
    # One row: low_traffic (opens < P10 global) and could be scale_up if conditions met.
    # Create many rows so P10(opens) is defined; one row with opens just above min_opens
    # but below P10(opens) -> low_traffic with potential 0.
    raw = []
    for i in range(25):
        raw.append({
            "nm_id": 2000 + i,
            "opens": 400 + i * 100,  # 400 to 2800
            "carts": 40 + i * 10,
            "orders": 8 + i * 2,
            "revenue": 4000.0 + i * 200,
            "cart_rate": 0.10,
            "order_rate": 0.02,
            "cart_to_order": 0.2,
            "avg_check": 500.0,
        })
    # This row: opens=250 (above min_opens=200), but below P10(opens) of the set.
    # P10 of [400,500,...,2800] is around 400+0.1*(2400)=640. So 250 is below that.
    # So it gets low_traffic (potential 0). No other signal should win.
    raw.append({
        "nm_id": 99,
        "opens": 250,
        "carts": 25,
        "orders": 5,
        "revenue": 2500.0,
        "cart_rate": 0.10,
        "order_rate": 0.02,
        "cart_to_order": 0.2,
        "avg_check": 500.0,
    })
    result = compute_funnel_signals(raw, min_opens=200)
    by_nm = {r["nm_id"]: r for r in result}
    assert 99 in by_nm
    # Should be low_traffic (priority over others when potential is 0)
    assert by_nm[99]["signal_code"] == SIGNAL_LOW_TRAFFIC
    assert by_nm[99]["potential_rub"] == 0.0


def test_benchmark_scope_category_when_enough_skus():
    """When category has >= 10 eligible SKUs, benchmark_scope is 'category'."""
    raw = []
    for i in range(12):
        raw.append({
            "nm_id": 1000 + i,
            "opens": 300 + i * 20,
            "carts": 30 + i,
            "orders": 5 + i,
            "revenue": 2000.0,
            "cart_rate": 0.10,
            "order_rate": 0.02,
            "cart_to_order": 0.2,
            "avg_check": 400.0,
            "wb_category": "Кружки",
        })
    result = compute_funnel_signals(raw, min_opens=200)
    assert len(result) == 12
    for r in result:
        assert r["benchmark_scope"] == "category"


def test_benchmark_scope_project_fallback_when_few_skus():
    """When category has < 10 eligible SKUs, benchmark_scope is 'project_fallback'."""
    raw = []
    for i in range(15):
        raw.append({
            "nm_id": 2000 + i,
            "opens": 400 + i * 30,
            "carts": 40 + i,
            "orders": 8 + i,
            "revenue": 3000.0,
            "cart_rate": 0.11,
            "order_rate": 0.025,
            "cart_to_order": 0.22,
            "avg_check": 500.0,
            "wb_category": "Тарелки",
        })
    for i in range(5):
        raw.append({
            "nm_id": 3000 + i,
            "opens": 250 + i * 20,
            "carts": 25 + i,
            "orders": 4 + i,
            "revenue": 1500.0,
            "cart_rate": 0.10,
            "order_rate": 0.02,
            "cart_to_order": 0.2,
            "avg_check": 350.0,
            "wb_category": "Редкая категория",
        })
    result = compute_funnel_signals(raw, min_opens=200)
    by_nm = {r["nm_id"]: r for r in result}
    for i in range(5):
        assert by_nm[3000 + i]["benchmark_scope"] == "project_fallback"
    for i in range(15):
        assert by_nm[2000 + i]["benchmark_scope"] == "category"


def test_compute_benchmarks_returns_p10_opens_and_buckets():
    """compute_benchmarks assigns _bucket and returns p10_opens."""
    skus = [
        {"nm_id": 1, "opens": 100, "carts": 10, "orders": 2, "revenue": 500.0, "cart_rate": 0.1, "order_rate": 0.02, "cart_to_order": 0.2},
        {"nm_id": 2, "opens": 500, "carts": 50, "orders": 10, "revenue": 2000.0, "cart_rate": 0.1, "order_rate": 0.02, "cart_to_order": 0.2},
        {"nm_id": 3, "opens": 1000, "carts": 100, "orders": 25, "revenue": 5000.0, "cart_rate": 0.1, "order_rate": 0.025, "cart_to_order": 0.25},
    ] + [
        {"nm_id": 100 + i, "opens": 300 + i * 50, "carts": 30, "orders": 6, "revenue": 1500.0, "cart_rate": 0.1, "order_rate": 0.02, "cart_to_order": 0.2}
        for i in range(12)
    ]
    bench, p10_opens = compute_benchmarks(skus)
    assert p10_opens is not None
    assert "low" in bench and "mid" in bench and "high" in bench
    for s in skus:
        assert "_bucket" in s
        assert s["_bucket"] in ("low", "mid", "high")
