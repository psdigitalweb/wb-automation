"""DAO for WB reviews/feedback summary and detail feed (read-only)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.db import engine
from app.db_stocks import (
    get_latest_enterprise_stock_by_vendor_code_norm,
    get_latest_fbo_stock_totals_by_nm_id,
)


def _clean_optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _photo_urls_from_raw(raw: Any) -> List[str]:
    if raw is None:
        return []
    try:
        if isinstance(raw, str):
            raw = json.loads(raw)
        photo_links = raw.get("photoLinks") if isinstance(raw, dict) else None
        if not isinstance(photo_links, list):
            return []
        urls: List[str] = []
        for item in photo_links:
            if isinstance(item, str):
                candidate = item.strip()
            elif isinstance(item, dict):
                candidate = (
                    item.get("fullSize")
                    or item.get("big")
                    or item.get("miniSize")
                    or item.get("url")
                )
                candidate = str(candidate).strip() if candidate is not None else ""
            else:
                candidate = ""
            if candidate and candidate not in urls:
                urls.append(candidate)
        return urls
    except Exception:
        return []


def _answer_text_from_raw(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    try:
        if isinstance(raw, str):
            raw = json.loads(raw)
        answer = raw.get("answer") if isinstance(raw, dict) else None
        if isinstance(answer, dict):
            return _clean_optional_text(answer.get("text"))
        return _clean_optional_text(answer)
    except Exception:
        return None


def get_reviews_summary(
    project_id: int,
    period_from: Optional[date] = None,
    period_to: Optional[date] = None,
    nm_id: Optional[int] = None,
    vendor_code: Optional[str] = None,
    wb_category: Optional[str] = None,
    rating_lte: Optional[float] = None,
    only_enterprise_gt0: bool = False,
    only_fbo_gt0: bool = False,
    only_with_reviews_in_period: bool = False,
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
        "only_with_reviews_in_period": only_with_reviews_in_period,
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
          AND (
              :only_with_reviews_in_period = FALSE
              OR :has_period = FALSE
              OR COALESCE(ft.new_reviews, 0) > 0
          )
        ORDER BY ft.reviews_count_total DESC, ft.nm_id ASC
    """)
    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()

    items = [
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

    if not items or not (only_enterprise_gt0 or only_fbo_gt0):
        return items

    fbo_map: Dict[int, tuple[int, Any]] = {}
    if only_fbo_gt0:
        fbo_map = get_latest_fbo_stock_totals_by_nm_id([item["nm_id"] for item in items])

    enterprise_map: Dict[str, int] = {}
    if only_enterprise_gt0:
        vendor_codes = [
            str(item["vendor_code"]).strip()
            for item in items
            if item.get("vendor_code") is not None and str(item.get("vendor_code")).strip() != ""
        ]
        enterprise_map, _ = get_latest_enterprise_stock_by_vendor_code_norm(project_id, vendor_codes)

    filtered: List[Dict[str, Any]] = []
    for item in items:
        if only_fbo_gt0:
            fbo_qty = fbo_map.get(item["nm_id"], (0, None))[0]
            if int(fbo_qty or 0) <= 0:
                continue
        if only_enterprise_gt0:
            vendor_code_value = str(item.get("vendor_code") or "").strip()
            if int(enterprise_map.get(vendor_code_value, 0) or 0) <= 0:
                continue
        filtered.append(item)
    return filtered


def list_reviews_by_nm_id(
    project_id: int,
    nm_id: int,
    period_from: Optional[date] = None,
    period_to: Optional[date] = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict[str, Any]:
    """Detailed reviews feed for one nm_id with pagination."""

    params: Dict[str, Any] = {
        "project_id": project_id,
        "nm_id": nm_id,
        "period_from": period_from,
        "period_to": period_to,
        "has_period": period_from is not None and period_to is not None,
        "limit": limit,
        "offset": offset,
    }

    count_sql = text("""
        SELECT COUNT(*)::int
        FROM wb_feedback_snapshots fs
        WHERE fs.project_id = :project_id
          AND fs.nm_id = :nm_id
          AND (
              NOT :has_period
              OR (
                  fs.created_date IS NOT NULL
                  AND fs.created_date::date >= :period_from
                  AND fs.created_date::date <= :period_to
              )
          )
    """)

    list_sql = text("""
        SELECT
            fs.external_id,
            fs.nm_id,
            fs.created_date,
            fs.product_valuation,
            fs.is_answered,
            fs.has_media,
            fs.is_archived,
            fs.source_endpoint,
            fs.raw
        FROM wb_feedback_snapshots fs
        WHERE fs.project_id = :project_id
          AND fs.nm_id = :nm_id
          AND (
              NOT :has_period
              OR (
                  fs.created_date IS NOT NULL
                  AND fs.created_date::date >= :period_from
                  AND fs.created_date::date <= :period_to
              )
          )
        ORDER BY fs.created_date DESC NULLS LAST, fs.id DESC
        LIMIT :limit
        OFFSET :offset
    """)

    with engine.connect() as conn:
        total = int(conn.execute(count_sql, params).scalar() or 0)
        rows = conn.execute(list_sql, params).mappings().all()

    items: List[Dict[str, Any]] = []
    for row in rows:
        raw = row.get("raw")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = None
        items.append({
            "external_id": str(row["external_id"]),
            "nm_id": int(row["nm_id"]),
            "created_date": (
                row.get("created_date").isoformat()
                if getattr(row.get("created_date"), "isoformat", None)
                else None
            ),
            "rating": int(row["product_valuation"]) if row.get("product_valuation") is not None else None,
            "user_name": _clean_optional_text((raw or {}).get("userName") if isinstance(raw, dict) else None),
            "text": _clean_optional_text((raw or {}).get("text") if isinstance(raw, dict) else None),
            "pros": _clean_optional_text((raw or {}).get("pros") if isinstance(raw, dict) else None),
            "cons": _clean_optional_text((raw or {}).get("cons") if isinstance(raw, dict) else None),
            "answer_text": _answer_text_from_raw(raw),
            "photo_urls": _photo_urls_from_raw(raw),
            "video_url": _clean_optional_text(
                ((raw or {}).get("video") or {}).get("link")
                if isinstance((raw or {}).get("video"), dict)
                else None
            ),
            "is_answered": bool(row.get("is_answered")),
            "has_media": bool(row.get("has_media")),
            "is_archived": bool(row.get("is_archived")),
            "source_endpoint": _clean_optional_text(row.get("source_endpoint")),
        })

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < total,
    }
