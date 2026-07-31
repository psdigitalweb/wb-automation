"""Read-only query layer for the project-scoped Wildberries product catalog."""

from __future__ import annotations

from datetime import date, timedelta
from math import ceil
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.db import engine


_SORT_EXPRESSIONS = {
    "title": "LOWER(COALESCE(pb.title, ''))",
    "vendor_code": "LOWER(COALESCE(pb.vendor_code, ''))",
    "price": "cm.current_price_showcase",
    "rating": "reviews.rating",
    "impressions": "COALESCE(ctr.impressions, 0)",
    "ctr": "CASE WHEN COALESCE(ctr.impressions, 0) > 0 THEN ctr.card_clicks::numeric / ctr.impressions ELSE NULL END",
    "opens": "COALESCE(stats.opens, 0)",
    "carts": "COALESCE(stats.cart_count, 0)",
    "orders": "COALESCE(stats.order_count, 0)",
    "order_sum": "COALESCE(stats.order_sum, 0)",
    "buyouts": "COALESCE(stats.buyout_count, 0)",
}

_CTR_EXCLUDED_FLAGS = (
    "ZERO_IMPRESSIONS_WITH_CLICKS",
    "CLICKS_EXCEED_IMPRESSIONS",
    "CTR_EXCEEDS_100",
    "REPORTED_CTR_MISMATCH",
    "DELETED_PRODUCT",
)


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _sort_clause(sort: str, order: str) -> str:
    expression = _SORT_EXPRESSIONS.get(sort, _SORT_EXPRESSIONS["order_sum"])
    direction = "ASC" if order == "asc" else "DESC"
    return f"{expression} {direction} NULLS LAST, pb.nm_id ASC"


def get_catalog_default_period(project_id: int) -> Tuple[date, date]:
    with engine.connect() as conn:
        latest = conn.execute(
            text(
                """
                SELECT MAX(stat_date)
                FROM wb_card_stats_daily
                WHERE project_id = :project_id
                """
            ),
            {"project_id": int(project_id)},
        ).scalar_one_or_none()
    period_to = latest if isinstance(latest, date) else date.today() - timedelta(days=1)
    return period_to - timedelta(days=29), period_to


def _catalog_filters(
    q: Optional[str],
    activity: str,
    exact_nm_id: Optional[int] = None,
) -> Tuple[str, Dict[str, Any]]:
    clauses = ["p.project_id = :project_id"]
    params: Dict[str, Any] = {}
    if exact_nm_id is not None:
        clauses.append("p.nm_id = :exact_nm_id")
        params["exact_nm_id"] = int(exact_nm_id)
    else:
        normalized_q = (q or "").strip()
        if normalized_q:
            clauses.append(
                """
                (
                    p.nm_id::text ILIKE :q_pattern
                    OR COALESCE(p.vendor_code, '') ILIKE :q_pattern
                    OR COALESCE(p.title, '') ILIKE :q_pattern
                )
                """
            )
            params["q_pattern"] = f"%{normalized_q}%"
    if activity == "active":
        clauses.append("sp.is_active IS TRUE")
    return " AND ".join(clauses), params


def list_wb_catalog(
    *,
    project_id: int,
    period_from: date,
    period_to: date,
    q: Optional[str],
    activity: str,
    sort: str,
    order: str,
    page: int,
    page_size: int,
    ctr_mode: str,
    exact_nm_id: Optional[int] = None,
) -> Dict[str, Any]:
    where_sql, filter_params = _catalog_filters(q, activity, exact_nm_id)
    sort_sql = _sort_clause(sort, order)
    ctr_quality_sql = ""
    if ctr_mode == "quality_filtered":
        quoted_flags = ",".join(f"'{flag}'" for flag in _CTR_EXCLUDED_FLAGS)
        ctr_quality_sql = (
            f"AND NOT (COALESCE(c.quality_flags, ARRAY[]::text[]) "
            f"&& ARRAY[{quoted_flags}]::text[])"
        )

    params: Dict[str, Any] = {
        "project_id": int(project_id),
        "period_from": period_from,
        "period_to": period_to,
        "limit": int(page_size),
        "offset": (int(page) - 1) * int(page_size),
        **filter_params,
    }

    count_sql = text(
        f"""
        SELECT COUNT(*)::bigint
        FROM products p
        LEFT JOIN wb_showcase_product_presence sp
          ON sp.project_id = p.project_id
         AND sp.nm_id = p.nm_id
        WHERE {where_sql}
        """
    )

    items_sql = text(
        f"""
        WITH product_base AS (
            SELECT
                p.nm_id,
                p.vendor_code,
                p.vendor_code_norm,
                p.title,
                p.pics,
                COALESCE(sp.is_active, FALSE) AS is_active
            FROM products p
            LEFT JOIN wb_showcase_product_presence sp
              ON sp.project_id = p.project_id
             AND sp.nm_id = p.nm_id
            WHERE {where_sql}
        ),
        stats AS MATERIALIZED (
            SELECT
                s.nm_id,
                COALESCE(SUM(s.open_count), 0)::bigint AS opens,
                COALESCE(SUM(s.cart_count), 0)::bigint AS cart_count,
                COALESCE(SUM(s.order_count), 0)::bigint AS order_count,
                COALESCE(SUM(s.order_sum), 0)::numeric AS order_sum,
                COALESCE(SUM(s.buyout_count), 0)::bigint AS buyout_count,
                COALESCE(SUM(s.buyout_sum), 0)::numeric AS buyout_sum
            FROM wb_card_stats_daily s
            WHERE s.project_id = :project_id
              AND s.stat_date BETWEEN :period_from AND :period_to
            GROUP BY s.nm_id
        ),
        ctr AS MATERIALIZED (
            SELECT
                c.nm_id,
                COALESCE(SUM(c.impressions), 0)::bigint AS impressions,
                COALESCE(SUM(c.card_clicks), 0)::bigint AS card_clicks
            FROM wb_funnel_ctr_daily c
            WHERE c.project_id = :project_id
              AND c.stat_date BETWEEN :period_from AND :period_to
              AND NOT c.is_deleted
              {ctr_quality_sql}
            GROUP BY c.nm_id
        ),
        reviews AS MATERIALIZED (
            SELECT
                f.nm_id,
                AVG(f.product_valuation)::numeric(5, 2) AS rating,
                COUNT(*)::bigint AS reviews_count
            FROM wb_feedback_snapshots f
            WHERE f.project_id = :project_id
              AND f.created_date IS NOT NULL
            GROUP BY f.nm_id
        ),
        seller_discount AS MATERIALIZED (
            SELECT DISTINCT ON (ps.nm_id)
                ps.nm_id,
                ps.wb_discount AS seller_discount_percent
            FROM price_snapshots ps
            JOIN product_base pb
              ON pb.nm_id = ps.nm_id
            WHERE ps.project_id = :project_id
            ORDER BY ps.nm_id, ps.created_at DESC
        ),
        rrp_run AS (
            SELECT MAX(snapshot_at) AS snapshot_at
            FROM rrp_snapshots
            WHERE project_id = :project_id
        ),
        target_vendor_codes AS (
            SELECT DISTINCT vendor_code_norm
            FROM product_base
            WHERE vendor_code_norm IS NOT NULL
        ),
        rrp AS MATERIALIZED (
            SELECT
                r.vendor_code_norm,
                MAX(r.rrp_price)::numeric AS rrp_price
            FROM rrp_snapshots r
            JOIN rrp_run rr ON rr.snapshot_at = r.snapshot_at
            JOIN target_vendor_codes target
              ON target.vendor_code_norm = r.vendor_code_norm
            WHERE r.project_id = :project_id
            GROUP BY r.vendor_code_norm
        )
        SELECT
            pb.nm_id,
            pb.vendor_code,
            pb.title,
            CASE
                WHEN jsonb_typeof(pb.pics) = 'array' AND jsonb_array_length(pb.pics) > 0
                THEN COALESCE(
                    pb.pics->0->>'big',
                    pb.pics->0->>'original',
                    pb.pics->0->>'url',
                    pb.pics->0->>'c900x1200',
                    pb.pics->0->>'c516x688',
                    pb.pics->>0
                )
                ELSE NULL
            END AS main_photo_url,
            pb.is_active,
            cm.current_price_showcase AS showcase_price,
            cm.current_spp_percent AS spp_percent,
            seller_discount.seller_discount_percent,
            rrp.rrp_price,
            reviews.rating,
            COALESCE(reviews.reviews_count, 0)::bigint AS reviews_count,
            COALESCE(ctr.impressions, 0)::bigint AS impressions,
            COALESCE(ctr.card_clicks, 0)::bigint AS card_clicks,
            CASE
                WHEN COALESCE(ctr.impressions, 0) > 0
                THEN ctr.card_clicks::numeric / ctr.impressions * 100
                ELSE NULL
            END AS ctr_percent,
            COALESCE(stats.opens, 0)::bigint AS opens,
            COALESCE(stats.cart_count, 0)::bigint AS cart_count,
            CASE
                WHEN COALESCE(stats.opens, 0) > 0
                THEN stats.cart_count::numeric / stats.opens
                ELSE NULL
            END AS cart_rate,
            COALESCE(stats.order_count, 0)::bigint AS order_count,
            CASE
                WHEN COALESCE(stats.cart_count, 0) > 0
                THEN stats.order_count::numeric / stats.cart_count
                ELSE NULL
            END AS cart_to_order_rate,
            COALESCE(stats.order_sum, 0)::numeric AS order_sum,
            COALESCE(stats.buyout_count, 0)::bigint AS buyout_count,
            COALESCE(stats.buyout_sum, 0)::numeric AS buyout_sum
        FROM product_base pb
        LEFT JOIN stats ON stats.nm_id = pb.nm_id
        LEFT JOIN ctr ON ctr.nm_id = pb.nm_id
        LEFT JOIN reviews ON reviews.nm_id = pb.nm_id
        LEFT JOIN seller_discount ON seller_discount.nm_id = pb.nm_id
        LEFT JOIN wb_current_metrics cm
          ON cm.project_id = :project_id
         AND cm.nm_id = pb.nm_id
        LEFT JOIN rrp
          ON rrp.vendor_code_norm = pb.vendor_code_norm
        ORDER BY {sort_sql}
        LIMIT :limit OFFSET :offset
        """
    )

    freshness_sql = text(
        """
        SELECT
            (SELECT MAX(updated_at) FROM products WHERE project_id = :project_id) AS products_at,
            (SELECT MAX(last_checked_at) FROM wb_showcase_product_presence WHERE project_id = :project_id) AS showcase_at,
            (SELECT MAX(updated_at) FROM wb_current_metrics WHERE project_id = :project_id) AS prices_at,
            (SELECT MAX(snapshot_at) FROM rrp_snapshots WHERE project_id = :project_id) AS rrp_at,
            (SELECT MAX(stat_date) FROM wb_card_stats_daily WHERE project_id = :project_id) AS analytics_through,
            (SELECT MAX(stat_date) FROM wb_funnel_ctr_daily WHERE project_id = :project_id) AS ctr_through,
            (SELECT MAX(snapshot_at) FROM wb_feedback_snapshots WHERE project_id = :project_id) AS reviews_at
        """
    )

    with engine.connect() as conn:
        total = int(conn.execute(count_sql, params).scalar_one() or 0)
        rows = conn.execute(items_sql, params).mappings().all()
        freshness = conn.execute(
            freshness_sql, {"project_id": int(project_id)}
        ).mappings().one()

    items: List[Dict[str, Any]] = []
    for row in rows:
        items.append(
            {
                "nm_id": int(row["nm_id"]),
                "vendor_code": row.get("vendor_code"),
                "title": row.get("title"),
                "main_photo_url": row.get("main_photo_url"),
                "is_active": bool(row.get("is_active")),
                "showcase_price": float(row["showcase_price"]) if row.get("showcase_price") is not None else None,
                "spp_percent": float(row["spp_percent"]) if row.get("spp_percent") is not None else None,
                "seller_discount_percent": float(row["seller_discount_percent"]) if row.get("seller_discount_percent") is not None else None,
                "rrp_price": float(row["rrp_price"]) if row.get("rrp_price") is not None else None,
                "rating": float(row["rating"]) if row.get("rating") is not None else None,
                "reviews_count": int(row.get("reviews_count") or 0),
                "impressions": int(row.get("impressions") or 0),
                "card_clicks": int(row.get("card_clicks") or 0),
                "ctr_percent": float(row["ctr_percent"]) if row.get("ctr_percent") is not None else None,
                "opens": int(row.get("opens") or 0),
                "cart_count": int(row.get("cart_count") or 0),
                "cart_rate": float(row["cart_rate"]) if row.get("cart_rate") is not None else None,
                "order_count": int(row.get("order_count") or 0),
                "cart_to_order_rate": float(row["cart_to_order_rate"]) if row.get("cart_to_order_rate") is not None else None,
                "order_sum": float(row.get("order_sum") or 0),
                "buyout_count": int(row.get("buyout_count") or 0),
                "buyout_sum": float(row.get("buyout_sum") or 0),
            }
        )

    return {
        "items": items,
        "meta": {
            "page": int(page),
            "page_size": int(page_size),
            "total": total,
            "pages": ceil(total / page_size) if total else 0,
            "period_from": period_from.isoformat(),
            "period_to": period_to.isoformat(),
        },
        "data_freshness": {
            "products_at": _iso(freshness.get("products_at")),
            "showcase_at": _iso(freshness.get("showcase_at")),
            "prices_at": _iso(freshness.get("prices_at")),
            "rrp_at": _iso(freshness.get("rrp_at")),
            "analytics_through": _iso(freshness.get("analytics_through")),
            "ctr_through": _iso(freshness.get("ctr_through")),
            "reviews_at": _iso(freshness.get("reviews_at")),
        },
    }


def get_wb_catalog_product(
    *,
    project_id: int,
    nm_id: int,
    period_from: date,
    period_to: date,
    ctr_mode: str,
) -> Optional[Dict[str, Any]]:
    payload = list_wb_catalog(
        project_id=project_id,
        period_from=period_from,
        period_to=period_to,
        q=None,
        activity="all",
        sort="title",
        order="asc",
        page=1,
        page_size=1,
        ctr_mode=ctr_mode,
        exact_nm_id=nm_id,
    )
    if not payload["items"]:
        return None
    return {
        "item": payload["items"][0],
        "period_from": payload["meta"]["period_from"],
        "period_to": payload["meta"]["period_to"],
        "data_freshness": payload["data_freshness"],
    }
