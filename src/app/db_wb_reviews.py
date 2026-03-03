"""DAO for WB reviews/feedback summary (read-only)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.db import engine


def get_reviews_summary(
    project_id: int,
    period_from: Optional[date] = None,
    period_to: Optional[date] = None,
    nm_id: Optional[int] = None,
    vendor_code: Optional[str] = None,
    wb_category: Optional[str] = None,
    rating_lte: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Reviews summary by nm_id with product metadata and optional product filters."""

    def _first_image_url_from_pics(pics: Any) -> Optional[str]:
        if pics is None:
            return None
        try:
            if isinstance(pics, str):
                pics = json.loads(pics)
            if not isinstance(pics, list) or not pics:
                return None
            first = pics[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                return first.get("url") or first.get("big") or first.get("c128") or None
        except Exception:
            return None
        return None

    params: Dict[str, Any] = {
        "project_id": project_id,
        "period_from": period_from,
        "period_to": period_to,
        "nm_id": nm_id,
        "vendor_code_pattern": f"%{vendor_code.strip()}%" if vendor_code and vendor_code.strip() else None,
        "wb_category": wb_category,
        "rating_lte": rating_lte,
        "has_period": period_from is not None and period_to is not None,
    }

    sql = text("""
        WITH feedback_totals AS (
            SELECT
                fs.nm_id,
                COUNT(*)::int AS reviews_count_total,
                AVG(fs.product_valuation)::numeric(5,2) AS avg_rating,
                CASE
                    WHEN :has_period THEN COUNT(*) FILTER (
                        WHERE fs.created_date::date >= :period_from
                          AND fs.created_date::date <= :period_to
                    )::int
                    ELSE NULL
                END AS new_reviews
            FROM wb_feedback_snapshots fs
            WHERE fs.project_id = :project_id
              AND fs.created_date IS NOT NULL
              AND fs.nm_id IS NOT NULL
            GROUP BY fs.nm_id
        )
        SELECT
            ft.nm_id,
            ft.reviews_count_total,
            ft.avg_rating,
            ft.new_reviews,
            p.title,
            p.subject_name AS wb_category,
            p.vendor_code,
            p.pics
        FROM feedback_totals ft
        LEFT JOIN products p
          ON p.project_id = :project_id
         AND p.nm_id = ft.nm_id
        WHERE (:nm_id IS NULL OR ft.nm_id = :nm_id)
          AND (:vendor_code_pattern IS NULL OR p.vendor_code ILIKE :vendor_code_pattern)
          AND (:wb_category IS NULL OR p.subject_name = :wb_category)
          AND (:rating_lte IS NULL OR ft.avg_rating <= :rating_lte)
        ORDER BY ft.reviews_count_total DESC, ft.nm_id ASC
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()

    return [
        {
            "nm_id": int(r["nm_id"]),
            "title": r.get("title"),
            "wb_category": r.get("wb_category"),
            "image_url": _first_image_url_from_pics(r.get("pics")),
            "vendor_code": r.get("vendor_code"),
            "reviews_count_total": int(r["reviews_count_total"] or 0),
            "avg_rating": float(r["avg_rating"]) if r["avg_rating"] is not None else None,
            "new_reviews": int(r["new_reviews"]) if r["new_reviews"] is not None else None,
        }
        for r in rows
    ]
