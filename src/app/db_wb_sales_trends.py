"""Read-only daily sales trends for selected Wildberries products."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

from sqlalchemy import text

from app.db import engine
from app.services.product_identity import WB_PRODUCT_SOURCE_CTES


def get_sales_trends(
    *,
    project_id: int,
    nm_ids: List[int],
    period_from: date,
    period_to: date,
    window_days: int,
) -> List[Dict[str, Any]]:
    """Return zero-filled daily order metrics and trailing moving averages per SKU."""
    selected_ids = list(dict.fromkeys(int(nm_id) for nm_id in nm_ids))
    if not selected_ids:
        return []

    query = text(
        f"""
        WITH {WB_PRODUCT_SOURCE_CTES},
        selected_products AS (
            SELECT
                p.nm_id::bigint AS nm_id,
                MAX(p.vendor_code) AS vendor_code,
                MAX(p.title) AS title
            FROM product_source p
            WHERE p.nm_id = ANY(:nm_ids)
            GROUP BY p.nm_id
        ), dates AS (
            SELECT generate_series(
                CAST(:period_from AS date) - (:window_days - 1) * INTERVAL '1 day',
                CAST(:period_to AS date),
                INTERVAL '1 day'
            )::date AS stat_date
        ), sales_daily AS (
            SELECT
                s.nm_id,
                s.stat_date,
                COALESCE(SUM(s.order_count), 0)::bigint AS orders,
                COALESCE(SUM(s.order_sum), 0)::numeric AS revenue
            FROM wb_card_stats_daily s
            WHERE s.project_id = :project_id
              AND s.nm_id = ANY(:nm_ids)
              AND s.stat_date BETWEEN
                  CAST(:period_from AS date) - (:window_days - 1) * INTERVAL '1 day'
                  AND CAST(:period_to AS date)
            GROUP BY s.nm_id, s.stat_date
        ), traffic_daily AS (
            SELECT
                c.nm_id,
                c.stat_date,
                COALESCE(SUM(c.impressions), 0)::bigint AS impressions,
                COALESCE(SUM(c.card_clicks), 0)::bigint AS card_clicks
            FROM wb_funnel_ctr_daily c
            WHERE c.project_id = :project_id
              AND c.nm_id = ANY(:nm_ids)
              AND c.stat_date BETWEEN
                  CAST(:period_from AS date) - (:window_days - 1) * INTERVAL '1 day'
                  AND CAST(:period_to AS date)
              AND NOT c.is_deleted
              AND NOT (
                  COALESCE(c.quality_flags, ARRAY[]::text[])
                  && ARRAY[
                      'ZERO_IMPRESSIONS_WITH_CLICKS',
                      'CLICKS_EXCEED_IMPRESSIONS',
                      'CTR_EXCEEDS_100',
                      'REPORTED_CTR_MISMATCH',
                      'DELETED_PRODUCT'
                  ]::text[]
              )
            GROUP BY c.nm_id, c.stat_date
        ), zero_filled AS (
            SELECT
                p.nm_id,
                p.vendor_code,
                p.title,
                d.stat_date,
                COALESCE(s.orders, 0)::bigint AS orders,
                COALESCE(s.revenue, 0)::numeric AS revenue,
                COALESCE(t.impressions, 0)::bigint AS impressions,
                COALESCE(t.card_clicks, 0)::bigint AS card_clicks
            FROM selected_products p
            CROSS JOIN dates d
            LEFT JOIN sales_daily s
              ON s.nm_id = p.nm_id
             AND s.stat_date = d.stat_date
            LEFT JOIN traffic_daily t
              ON t.nm_id = p.nm_id
             AND t.stat_date = d.stat_date
        ), calculated AS (
            SELECT
                *,
                AVG(orders) OVER (
                    PARTITION BY nm_id ORDER BY stat_date
                    ROWS BETWEEN :window_preceding PRECEDING AND CURRENT ROW
                ) AS moving_average_orders,
                AVG(revenue) OVER (
                    PARTITION BY nm_id ORDER BY stat_date
                    ROWS BETWEEN :window_preceding PRECEDING AND CURRENT ROW
                ) AS moving_average_revenue,
                AVG(impressions) OVER (
                    PARTITION BY nm_id ORDER BY stat_date
                    ROWS BETWEEN :window_preceding PRECEDING AND CURRENT ROW
                ) AS moving_average_impressions,
                AVG(card_clicks) OVER (
                    PARTITION BY nm_id ORDER BY stat_date
                    ROWS BETWEEN :window_preceding PRECEDING AND CURRENT ROW
                ) AS moving_average_card_clicks,
                CASE
                    WHEN SUM(impressions) OVER (
                        PARTITION BY nm_id ORDER BY stat_date
                        ROWS BETWEEN :window_preceding PRECEDING AND CURRENT ROW
                    ) > 0
                    THEN SUM(card_clicks) OVER (
                        PARTITION BY nm_id ORDER BY stat_date
                        ROWS BETWEEN :window_preceding PRECEDING AND CURRENT ROW
                    )::numeric
                    / SUM(impressions) OVER (
                        PARTITION BY nm_id ORDER BY stat_date
                        ROWS BETWEEN :window_preceding PRECEDING AND CURRENT ROW
                    ) * 100
                    ELSE NULL
                END AS moving_average_ctr_percent
            FROM zero_filled
        )
        SELECT
            nm_id,
            vendor_code,
            title,
            stat_date,
            orders,
            revenue,
            impressions,
            card_clicks,
            CASE
                WHEN impressions > 0
                THEN card_clicks::numeric / impressions * 100
                ELSE NULL
            END AS ctr_percent,
            moving_average_orders,
            moving_average_revenue,
            moving_average_impressions,
            moving_average_card_clicks,
            moving_average_ctr_percent
        FROM calculated
        WHERE stat_date BETWEEN CAST(:period_from AS date) AND CAST(:period_to AS date)
        ORDER BY nm_id, stat_date
        """
    )
    params = {
        "project_id": project_id,
        "nm_ids": selected_ids,
        "period_from": period_from,
        "period_to": period_to,
        "window_days": window_days,
        "window_preceding": window_days - 1,
    }

    with engine.connect() as conn:
        rows = conn.execute(query, params).mappings().all()

    grouped: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        nm_id = int(row["nm_id"])
        series = grouped.setdefault(
            nm_id,
            {
                "nm_id": nm_id,
                "vendor_code": row.get("vendor_code"),
                "title": row.get("title"),
                "points": [],
            },
        )
        stat_date = row["stat_date"]
        series["points"].append(
            {
                "date": stat_date.isoformat() if hasattr(stat_date, "isoformat") else str(stat_date),
                "orders": int(row.get("orders") or 0),
                "revenue": float(row.get("revenue") or 0),
                "impressions": int(row.get("impressions") or 0),
                "card_clicks": int(row.get("card_clicks") or 0),
                "ctr_percent": (
                    float(row["ctr_percent"])
                    if row.get("ctr_percent") is not None
                    else None
                ),
                "moving_average_orders": float(row.get("moving_average_orders") or 0),
                "moving_average_revenue": float(row.get("moving_average_revenue") or 0),
                "moving_average_impressions": float(
                    row.get("moving_average_impressions") or 0
                ),
                "moving_average_card_clicks": float(
                    row.get("moving_average_card_clicks") or 0
                ),
                "moving_average_ctr_percent": (
                    float(row["moving_average_ctr_percent"])
                    if row.get("moving_average_ctr_percent") is not None
                    else None
                ),
            }
        )
    return list(grouped.values())
