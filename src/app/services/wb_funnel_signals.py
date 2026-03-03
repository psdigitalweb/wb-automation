"""Funnel signals: buckets, benchmarks, signal rules, potential_rub, severity.

Benchmarks (percentiles, buckets) are computed within WB category; if category has
fewer than MIN_CATEGORY_SIZE eligible SKUs, fallback to project-level benchmarks.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Signal codes for API/filtering
SIGNAL_LOW_TRAFFIC = "low_traffic"
SIGNAL_LOW_ADD_TO_CART = "low_add_to_cart"
SIGNAL_LOSS_CART_TO_ORDER = "loss_cart_to_order"
SIGNAL_LOW_ORDER_RATE = "low_order_rate"
SIGNAL_SCALE_UP = "scale_up"
SIGNAL_INSUFFICIENT_DATA = "insufficient_data"

# Priority order when potential ties (first wins)
SIGNAL_PRIORITY: List[str] = [
    SIGNAL_LOW_TRAFFIC,
    SIGNAL_LOW_ADD_TO_CART,
    SIGNAL_LOSS_CART_TO_ORDER,
    SIGNAL_LOW_ORDER_RATE,
    SIGNAL_SCALE_UP,
]

BUCKET_LOW = "low"
BUCKET_MID = "mid"
BUCKET_HIGH = "high"
MIN_BUCKET_SIZE = 10
MIN_CATEGORY_SIZE = 10  # below this use project-level benchmarks

BENCHMARK_SCOPE_CATEGORY = "category"
BENCHMARK_SCOPE_PROJECT_FALLBACK = "project_fallback"


def _percentile(arr: List[float], p: float) -> Optional[float]:
    """Linear interpolation percentile. No numpy. Returns None if arr is empty."""
    if not arr:
        return None
    sorted_arr = sorted(arr)
    n = len(sorted_arr)
    if n == 1:
        return sorted_arr[0]
    idx = (p / 100.0) * (n - 1)
    i0 = int(idx)
    i1 = min(i0 + 1, n - 1)
    if i0 == i1:
        return sorted_arr[i0]
    w = idx - i0
    return sorted_arr[i0] * (1 - w) + sorted_arr[i1] * w


def _get_bucket(opens: int, p50_opens: float, p90_opens: float) -> str:
    if p50_opens >= p90_opens:
        return BUCKET_LOW
    if opens <= p50_opens:
        return BUCKET_LOW
    if opens <= p90_opens:
        return BUCKET_MID
    return BUCKET_HIGH


def _percentiles_for_skus(skus: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Single benchmark dict: P10/P50 for cart_rate, order_rate, cart_to_order; P75 for order_rate, revenue."""
    cart_rates = [s["cart_rate"] for s in skus if s.get("cart_rate") is not None]
    order_rates = [s["order_rate"] for s in skus if s.get("order_rate") is not None]
    cart_to_orders = [s["cart_to_order"] for s in skus if s.get("cart_to_order") is not None]
    revenues = [s["revenue"] for s in skus]
    return {
        "cart_rate_p10": _percentile(cart_rates, 10) if cart_rates else None,
        "cart_rate_p50": _percentile(cart_rates, 50) if cart_rates else None,
        "order_rate_p10": _percentile(order_rates, 10) if order_rates else None,
        "order_rate_p50": _percentile(order_rates, 50) if order_rates else None,
        "order_rate_p75": _percentile(order_rates, 75) if order_rates else None,
        "cart_to_order_p10": _percentile(cart_to_orders, 10) if cart_to_orders else None,
        "cart_to_order_p50": _percentile(cart_to_orders, 50) if cart_to_orders else None,
        "revenue_p75": _percentile(revenues, 75) if revenues else None,
    }


def compute_benchmarks(sku_list: List[Dict[str, Any]]) -> Tuple[
    Dict[str, Dict[str, Optional[float]]],
    Optional[float],
]:
    """
    Compute benchmarks for a scope (category or project): per-bucket percentiles
    and P10(opens) for low_traffic. Assigns _bucket on each SKU in sku_list in-place.

    Returns:
        bench_by_bucket: { "low" | "mid" | "high" -> { cart_rate_p10, ... } }
        p10_opens: P10(opens) in this scope (for low_traffic signal)
    """
    if not sku_list:
        empty_bench = _percentiles_for_skus([])
        return (
            {BUCKET_LOW: empty_bench, BUCKET_MID: empty_bench, BUCKET_HIGH: empty_bench},
            None,
        )
    opens_list = [r["opens"] for r in sku_list]
    p50_opens = _percentile(opens_list, 50) or 0.0
    p90_opens = _percentile(opens_list, 90) or p50_opens
    p10_opens = _percentile(opens_list, 10)

    for r in sku_list:
        r["_bucket"] = _get_bucket(r["opens"], p50_opens, p90_opens)

    by_bucket: Dict[str, List[Dict[str, Any]]] = {
        BUCKET_LOW: [r for r in sku_list if r["_bucket"] == BUCKET_LOW],
        BUCKET_MID: [r for r in sku_list if r["_bucket"] == BUCKET_MID],
        BUCKET_HIGH: [r for r in sku_list if r["_bucket"] == BUCKET_HIGH],
    }

    def skus_for_bench(bucket: str) -> List[Dict[str, Any]]:
        skus = by_bucket.get(bucket, [])
        if len(skus) < MIN_BUCKET_SIZE:
            return sku_list
        return skus

    bench_by_bucket = {
        BUCKET_LOW: _percentiles_for_skus(skus_for_bench(BUCKET_LOW)),
        BUCKET_MID: _percentiles_for_skus(skus_for_bench(BUCKET_MID)),
        BUCKET_HIGH: _percentiles_for_skus(skus_for_bench(BUCKET_HIGH)),
    }
    return bench_by_bucket, p10_opens


def compute_funnel_signals(
    raw_rows: List[Dict[str, Any]],
    min_opens: int = 200,
) -> List[Dict[str, Any]]:
    """
    From raw aggregation rows (nm_id, opens, carts, orders, revenue, cart_rate, order_rate,
    cart_to_order, avg_check, wb_category), compute signal_code, signal, severity, potential_rub,
    bucket, signal_details, benchmark_scope.

    Benchmarks and buckets are computed within WB category; if category has fewer than
    MIN_CATEGORY_SIZE eligible SKUs, project-level benchmarks are used (benchmark_scope = "project_fallback").
    """
    result: List[Dict[str, Any]] = []
    eligible: List[Dict[str, Any]] = []
    for r in raw_rows:
        if r["opens"] < min_opens:
            result.append({
                **r,
                "signal_code": SIGNAL_INSUFFICIENT_DATA,
                "signal": "Недостаточно данных",
                "signal_label": "Недостаточно данных",
                "severity": None,
                "potential_rub": 0.0,
                "bucket": None,
                "signal_details": None,
                "benchmark_scope": None,
            })
        else:
            eligible.append(dict(r))

    if not eligible:
        return result

    # Normalize category key for grouping (None / empty -> same key)
    def _category_key(r: Dict[str, Any]) -> str:
        c = r.get("wb_category")
        if c is None or (isinstance(c, str) and c.strip() == ""):
            return "__unknown__"
        return str(c).strip()

    # Project-level benchmarks (for fallback when category has < MIN_CATEGORY_SIZE)
    project_bench, project_p10_opens = compute_benchmarks(eligible)

    # Group eligible by WB category
    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for r in eligible:
        key = _category_key(r)
        by_category.setdefault(key, []).append(r)

    # Per-category: assign _bench, _p10_opens, _bucket, _scope to each row
    for cat_key, category_skus in by_category.items():
        if len(category_skus) >= MIN_CATEGORY_SIZE:
            scope_bench, scope_p10 = compute_benchmarks(category_skus)
            scope = BENCHMARK_SCOPE_CATEGORY
        else:
            scope_bench = project_bench
            scope_p10 = project_p10_opens
            # Buckets for fallback: use project's opens distribution
            opens_list = [r["opens"] for r in eligible]
            p50_opens = _percentile(opens_list, 50) or 0.0
            p90_opens = _percentile(opens_list, 90) or p50_opens
            for r in category_skus:
                r["_bucket"] = _get_bucket(r["opens"], p50_opens, p90_opens)
            scope = BENCHMARK_SCOPE_PROJECT_FALLBACK

        for r in category_skus:
            r["_bench"] = scope_bench
            r["_p10_opens"] = scope_p10
            r["_scope"] = scope
            if scope == BENCHMARK_SCOPE_CATEGORY:
                # _bucket already set by compute_benchmarks(category_skus)
                pass
            # else _bucket set above in fallback branch

    def potential_low_add_to_cart(row: Dict[str, Any], b: Dict[str, Optional[float]]) -> float:
        cr50 = b.get("cart_rate_p50")
        co50 = b.get("cart_to_order_p50")
        avg = row.get("avg_check") or 0
        if cr50 is None or co50 is None or avg <= 0:
            return 0.0
        expected_carts = row["opens"] * cr50
        expected_orders = expected_carts * co50
        lost = max(0, expected_orders - row["orders"])
        return lost * avg

    def potential_loss_cart_to_order(row: Dict[str, Any], b: Dict[str, Optional[float]]) -> float:
        co50 = b.get("cart_to_order_p50")
        avg = row.get("avg_check") or 0
        if co50 is None or avg <= 0:
            return 0.0
        expected_orders = row["carts"] * co50
        lost = max(0, expected_orders - row["orders"])
        return lost * avg

    def potential_low_order_rate(row: Dict[str, Any], b: Dict[str, Optional[float]]) -> float:
        or50 = b.get("order_rate_p50")
        avg = row.get("avg_check") or 0
        if or50 is None or avg <= 0:
            return 0.0
        expected_orders = row["opens"] * or50
        lost = max(0, expected_orders - row["orders"])
        return lost * avg

    def potential_scale_up(row: Dict[str, Any], b: Dict[str, Optional[float]]) -> float:
        or75 = b.get("order_rate_p75")
        avg = row.get("avg_check") or 0
        if or75 is None or avg <= 0:
            return 0.0
        diff = or75 - (row.get("order_rate") or 0)
        if diff <= 0:
            return 0.0
        return (row["opens"] * diff) * avg

    opens_list_global = [r["opens"] for r in eligible]
    or50_opens_global = _percentile(opens_list_global, 50)

    potentials_positive: List[float] = []

    for row in eligible:
        bucket = row["_bucket"]
        b = row["_bench"][bucket]
        p10_opens = row["_p10_opens"]
        signals_with_potential: List[Tuple[str, float, Optional[str]]] = []

        if p10_opens is not None and row["opens"] < p10_opens:
            signals_with_potential.append((SIGNAL_LOW_TRAFFIC, 0.0, None))

        cr10 = b.get("cart_rate_p10")
        if cr10 is not None and (row.get("cart_rate") or 0) < cr10:
            p = potential_low_add_to_cart(row, b)
            signals_with_potential.append((SIGNAL_LOW_ADD_TO_CART, p, f"cart_rate {((row.get('cart_rate') or 0)*100):.1f}% ниже P10={cr10*100:.1f}% (bucket {bucket.upper()})"))

        co10 = b.get("cart_to_order_p10")
        if co10 is not None and (row.get("cart_to_order") or 0) < co10:
            p = potential_loss_cart_to_order(row, b)
            signals_with_potential.append((SIGNAL_LOSS_CART_TO_ORDER, p, f"cart_to_order {((row.get('cart_to_order') or 0)*100):.1f}% ниже P10={co10*100:.1f}% (bucket {bucket.upper()})"))

        or10 = b.get("order_rate_p10")
        if or10 is not None and (row.get("order_rate") or 0) < or10:
            p = potential_low_order_rate(row, b)
            signals_with_potential.append((SIGNAL_LOW_ORDER_RATE, p, f"order_rate {((row.get('order_rate') or 0)*100):.1f}% ниже P10={or10*100:.1f}% (bucket {bucket.upper()})"))

        or75 = b.get("order_rate_p75")
        rev75 = b.get("revenue_p75")
        if or75 is not None and rev75 is not None and or50_opens_global is not None:
            if row["opens"] >= or50_opens_global and (row.get("order_rate") or 0) >= or75 and (row.get("revenue") or 0) >= rev75:
                p = potential_scale_up(row, b)
                signals_with_potential.append((SIGNAL_SCALE_UP, p, None))

        chosen_code = SIGNAL_LOW_TRAFFIC
        chosen_potential = 0.0
        chosen_details: Optional[str] = None
        if signals_with_potential:
            best = max(signals_with_potential, key=lambda x: (x[1], -SIGNAL_PRIORITY.index(x[0])))
            chosen_code = best[0]
            chosen_potential = best[1]
            chosen_details = best[2]

        row["_signal_code"] = chosen_code
        row["_potential_rub"] = chosen_potential
        row["_signal_details"] = chosen_details
        if chosen_potential > 0:
            potentials_positive.append(chosen_potential)

    if potentials_positive:
        p50_pot = _percentile(potentials_positive, 50)
        p90_pot = _percentile(potentials_positive, 90)
    else:
        p50_pot = p90_pot = None

    signal_display = {
        SIGNAL_LOW_TRAFFIC: "Сигнал: Низкий трафик",
        SIGNAL_LOW_ADD_TO_CART: "Сигнал: Низкий add-to-cart",
        SIGNAL_LOSS_CART_TO_ORDER: "Сигнал: Потеря cart→order",
        SIGNAL_LOW_ORDER_RATE: "Сигнал: Низкая конверсия в заказ",
        SIGNAL_SCALE_UP: "Сигнал: Масштабировать",
    }
    signal_label_display = {
        SIGNAL_LOW_TRAFFIC: "Низкий трафик",
        SIGNAL_LOW_ADD_TO_CART: "Низкий add-to-cart",
        SIGNAL_LOSS_CART_TO_ORDER: "Потеря cart→order",
        SIGNAL_LOW_ORDER_RATE: "Низкая конверсия в заказ",
        SIGNAL_SCALE_UP: "Масштабировать",
    }

    for row in eligible:
        potential = row["_potential_rub"]
        if potential > 0 and p50_pot is not None and p90_pot is not None:
            if potential >= p90_pot:
                severity = "high"
            elif potential >= p50_pot:
                severity = "med"
            else:
                severity = "low"
        else:
            severity = None

        result.append({
            "nm_id": row["nm_id"],
            "opens": row["opens"],
            "carts": row["carts"],
            "orders": row["orders"],
            "revenue": row["revenue"],
            "cart_rate": row.get("cart_rate"),
            "order_rate": row.get("order_rate"),
            "cart_to_order": row.get("cart_to_order"),
            "avg_check": row.get("avg_check"),
            "title": row.get("title"),
            "wb_category": row.get("wb_category"),
            "image_url": row.get("image_url"),
            "vendor_code": row.get("vendor_code"),
            "signal_code": row["_signal_code"],
            "signal": signal_display.get(row["_signal_code"], row["_signal_code"]),
            "signal_label": signal_label_display.get(row["_signal_code"], row["_signal_code"]),
            "severity": severity,
            "potential_rub": round(potential, 2),
            "bucket": row["_bucket"],
            "signal_details": row["_signal_details"],
            "benchmark_scope": row["_scope"],
        })

    return result
