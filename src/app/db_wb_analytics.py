"""DAO for WB Analytics ingest tables."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.db import engine

# Batch size for UPSERT to avoid huge statements
BATCH_UPSERT_SIZE = 200


def get_wb_nm_ids_for_project(project_id: int, limit: Optional[int] = None) -> List[int]:
    """NM IDs из products для проекта (Product Identity).

    Args:
        project_id: ID проекта.
        limit: Если задан — взять первые N nm_id (ORDER BY nm_id ASC).
               Для search ingest (params_json.top_nm_limit).

    Returns:
        Список nm_id.
    """
    if limit is not None and limit <= 0:
        return []

    sql = text("""
        SELECT nm_id FROM products
        WHERE project_id = :project_id AND nm_id IS NOT NULL
        ORDER BY nm_id ASC
    """)
    params: Dict[str, Any] = {"project_id": project_id}
    if limit is not None:
        sql = text("""
            SELECT nm_id FROM products
            WHERE project_id = :project_id AND nm_id IS NOT NULL
            ORDER BY nm_id ASC
            LIMIT :lim
        """)
        params["lim"] = limit

    with engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [int(r[0]) for r in rows if r[0] is not None]


def _chunked(rows: List[Dict[str, Any]], size: int):
    """Yield batches of size."""
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def upsert_card_stats_daily(
    conn,
    project_id: int,
    ingest_run_id: int,
    rows: List[Dict[str, Any]],
) -> int:
    """Batch UPSERT в wb_card_stats_daily. Одна транзакция на batch."""
    if not rows:
        return 0
    sql = text("""
        INSERT INTO wb_card_stats_daily (
            project_id, nm_id, stat_date, currency,
            open_count, cart_count, order_count, order_sum,
            buyout_count, buyout_sum, buyout_percent,
            add_to_cart_conversion, cart_to_order_conversion, add_to_wishlist_count,
            extra, ingest_run_id
        ) VALUES (
            :project_id, :nm_id, :stat_date, :currency,
            :open_count, :cart_count, :order_count, :order_sum,
            :buyout_count, :buyout_sum, :buyout_percent,
            :add_to_cart_conversion, :cart_to_order_conversion, :add_to_wishlist_count,
            CAST(:extra AS jsonb), :ingest_run_id
        )
        ON CONFLICT (project_id, nm_id, stat_date) DO UPDATE SET
            currency = EXCLUDED.currency,
            open_count = EXCLUDED.open_count,
            cart_count = EXCLUDED.cart_count,
            order_count = EXCLUDED.order_count,
            order_sum = EXCLUDED.order_sum,
            buyout_count = EXCLUDED.buyout_count,
            buyout_sum = EXCLUDED.buyout_sum,
            buyout_percent = EXCLUDED.buyout_percent,
            add_to_cart_conversion = EXCLUDED.add_to_cart_conversion,
            cart_to_order_conversion = EXCLUDED.cart_to_order_conversion,
            add_to_wishlist_count = EXCLUDED.add_to_wishlist_count,
            extra = EXCLUDED.extra,
            ingest_run_id = EXCLUDED.ingest_run_id,
            updated_at = NOW()
    """)
    n = 0
    for batch in _chunked(rows, BATCH_UPSERT_SIZE):
        for r in batch:
            conn.execute(
                sql,
                {
                    "project_id": project_id,
                    "nm_id": r["nm_id"],
                    "stat_date": r["stat_date"],
                    "currency": r.get("currency"),
                    "open_count": r.get("open_count", 0),
                    "cart_count": r.get("cart_count", 0),
                    "order_count": r.get("order_count", 0),
                    "order_sum": r.get("order_sum", 0),
                    "buyout_count": r.get("buyout_count", 0),
                    "buyout_sum": r.get("buyout_sum", 0),
                    "buyout_percent": r.get("buyout_percent"),
                    "add_to_cart_conversion": r.get("add_to_cart_conversion"),
                    "cart_to_order_conversion": r.get("cart_to_order_conversion"),
                    "add_to_wishlist_count": r.get("add_to_wishlist_count", 0),
                    "extra": json.dumps(r.get("extra") or {}, ensure_ascii=False),
                    "ingest_run_id": ingest_run_id,
                },
            )
            n += 1
    return n


def upsert_search_query_terms(
    conn,
    project_id: int,
    ingest_run_id: int,
    rows: List[Dict[str, Any]],
) -> int:
    """Batch UPSERT в wb_search_query_terms."""
    if not rows:
        return 0
    sql = text("""
        INSERT INTO wb_search_query_terms (
            project_id, nm_id, search_text, frequency, is_ad, extra, ingest_run_id
        ) VALUES (
            :project_id, :nm_id, :search_text, :frequency, :is_ad,
            CAST(:extra AS jsonb), :ingest_run_id
        )
        ON CONFLICT (project_id, nm_id, search_text) DO UPDATE SET
            frequency = EXCLUDED.frequency,
            is_ad = EXCLUDED.is_ad,
            extra = EXCLUDED.extra,
            ingest_run_id = EXCLUDED.ingest_run_id,
            updated_at = NOW()
    """)
    n = 0
    for batch in _chunked(rows, BATCH_UPSERT_SIZE):
        for r in batch:
            conn.execute(
                sql,
                {
                    "project_id": project_id,
                    "nm_id": r["nm_id"],
                    "search_text": r["search_text"],
                    "frequency": r.get("frequency"),
                    "is_ad": r.get("is_ad"),
                    "extra": json.dumps(r.get("extra") or {}, ensure_ascii=False),
                    "ingest_run_id": ingest_run_id,
                },
            )
            n += 1
    return n


def upsert_search_query_daily(
    conn,
    project_id: int,
    ingest_run_id: int,
    rows: List[Dict[str, Any]],
) -> int:
    """Batch UPSERT в wb_search_query_daily."""
    if not rows:
        return 0
    sql = text("""
        INSERT INTO wb_search_query_daily (
            project_id, nm_id, search_text, stat_date, orders, avg_position, extra, ingest_run_id
        ) VALUES (
            :project_id, :nm_id, :search_text, :stat_date, :orders, :avg_position,
            CAST(:extra AS jsonb), :ingest_run_id
        )
        ON CONFLICT (project_id, nm_id, search_text, stat_date) DO UPDATE SET
            orders = EXCLUDED.orders,
            avg_position = EXCLUDED.avg_position,
            extra = EXCLUDED.extra,
            ingest_run_id = EXCLUDED.ingest_run_id,
            updated_at = NOW()
    """)
    n = 0
    for batch in _chunked(rows, BATCH_UPSERT_SIZE):
        for r in batch:
            conn.execute(
                sql,
                {
                    "project_id": project_id,
                    "nm_id": r["nm_id"],
                    "search_text": r["search_text"],
                    "stat_date": r["stat_date"],
                    "orders": r.get("orders", 0),
                    "avg_position": r.get("avg_position"),
                    "extra": json.dumps(r.get("extra") or {}, ensure_ascii=False),
                    "ingest_run_id": ingest_run_id,
                },
            )
            n += 1
    return n


def get_content_analytics_summary(
    project_id: int,
    period_from: date,
    period_to: date,
    nm_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Aggregate wb_card_stats_daily by nm_id for content analytics funnel.

    Returns: list of dicts with keys nm_id, opens, add_to_cart, cart_rate, orders, conversion, revenue.
    cart_rate = add_to_cart/opens, conversion = orders/add_to_cart (NULL when divisor is 0).
    """
    sql = text("""
        SELECT
            nm_id,
            COALESCE(SUM(open_count), 0)::bigint AS opens,
            COALESCE(SUM(cart_count), 0)::bigint AS add_to_cart,
            CASE WHEN SUM(open_count) > 0
                THEN SUM(cart_count)::numeric / NULLIF(SUM(open_count), 0)
                ELSE NULL END AS cart_rate,
            COALESCE(SUM(order_count), 0)::bigint AS orders,
            CASE WHEN SUM(cart_count) > 0
                THEN SUM(order_count)::numeric / NULLIF(SUM(cart_count), 0)
                ELSE NULL END AS conversion,
            COALESCE(SUM(order_sum), 0)::numeric AS revenue
        FROM wb_card_stats_daily
        WHERE project_id = :project_id
          AND stat_date >= :period_from AND stat_date <= :period_to
          AND (:nm_id IS NULL OR nm_id = :nm_id)
        GROUP BY nm_id
        ORDER BY nm_id
    """)
    params: Dict[str, Any] = {
        "project_id": project_id,
        "period_from": period_from,
        "period_to": period_to,
        "nm_id": nm_id,
    }
    with engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [
        {
            "nm_id": int(r[0]),
            "opens": int(r[1]),
            "add_to_cart": int(r[2]),
            "cart_rate": float(r[3]) if r[3] is not None else None,
            "orders": int(r[4]),
            "conversion": float(r[5]) if r[5] is not None else None,
            "revenue": float(r[6]) if r[6] is not None else 0,
        }
        for r in rows
    ]


def get_funnel_signals_raw(
    project_id: int,
    period_from: date,
    period_to: date,
    only_cart_gt0: bool = False,
    wb_category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Raw aggregation by nm_id for funnel signals. Sums from SQL; derived in Python.
    LEFT JOIN products for title, subject_name (wb_category), pics (first → image_url).
    """
    having = " HAVING SUM(cart_count) > 0" if only_cart_gt0 else ""
    join_filter = " AND p.subject_name = :wb_category" if wb_category else ""
    where_category = " AND p.nm_id IS NOT NULL" if wb_category else ""

    sql = text(f"""
        WITH agg AS (
            SELECT
                nm_id,
                COALESCE(SUM(open_count), 0)::bigint AS opens,
                COALESCE(SUM(cart_count), 0)::bigint AS carts,
                COALESCE(SUM(order_count), 0)::bigint AS orders,
                COALESCE(SUM(order_sum), 0)::numeric AS revenue
            FROM wb_card_stats_daily
            WHERE project_id = :project_id
              AND stat_date >= :period_from AND stat_date <= :period_to
            GROUP BY nm_id
            {having}
        )
        SELECT
            agg.nm_id,
            agg.opens,
            agg.carts,
            agg.orders,
            agg.revenue,
            p.title AS product_title,
            p.subject_name AS wb_category,
            p.pics AS pics,
            p.vendor_code AS vendor_code
        FROM agg
        LEFT JOIN products p ON p.project_id = :project_id AND p.nm_id = agg.nm_id{join_filter}
        WHERE 1=1{where_category}
        ORDER BY agg.nm_id
    """)
    params: Dict[str, Any] = {
        "project_id": project_id,
        "period_from": period_from,
        "period_to": period_to,
    }
    if wb_category:
        params["wb_category"] = wb_category
    with engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    result = []
    for r in rows:
        nm_id = int(r[0])
        opens = int(r[1])
        carts = int(r[2])
        orders = int(r[3])
        revenue = float(r[4]) if r[4] is not None else 0.0
        cart_rate = (carts / opens) if opens else None
        order_rate = (orders / opens) if opens else None
        cart_to_order = (orders / carts) if carts else None
        avg_check = (revenue / orders) if orders else None
        product_title = r[5] if r[5] is not None else None
        wb_cat = r[6] if r[6] is not None else None
        pics = r[7]
        vendor_code = r[8] if len(r) > 8 and r[8] is not None else None
        image_url = _first_image_url_from_pics(pics)
        result.append({
            "nm_id": nm_id,
            "opens": opens,
            "carts": carts,
            "orders": orders,
            "revenue": revenue,
            "cart_rate": cart_rate,
            "order_rate": order_rate,
            "cart_to_order": cart_to_order,
            "avg_check": avg_check,
            "title": product_title,
            "wb_category": wb_cat,
            "image_url": image_url,
            "vendor_code": vendor_code,
        })
    return result


def _first_image_url_from_pics(pics: Any) -> Optional[str]:
    """Extract first image URL from products.pics JSONB (list of URLs or objects with url/big/c128)."""
    if pics is None:
        return None
    try:
        if isinstance(pics, str):
            import json
            pics = json.loads(pics)
        if not isinstance(pics, list) or not pics:
            return None
        first = pics[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            return first.get("url") or first.get("big") or first.get("c128") or None
    except Exception:
        pass
    return None


def get_funnel_categories(project_id: int) -> List[str]:
    """Distinct WB categories (subject_name) from products for funnel-signals filter."""
    sql = text("""
        SELECT DISTINCT subject_name
        FROM products
        WHERE project_id = :project_id AND subject_name IS NOT NULL AND subject_name != ''
        ORDER BY subject_name
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, {"project_id": project_id}).fetchall()
    return [str(r[0]) for r in rows]
