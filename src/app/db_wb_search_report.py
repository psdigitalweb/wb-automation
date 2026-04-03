"""DAO for WB Search Report (tabular) snapshots."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.db import engine


def get_keywords_cache_counts_by_nm_id(
    *,
    snapshot_id: int,
    nm_ids: List[int],
) -> Dict[int, int]:
    """Return count of cached keyword lists (rows) per nm_id for a snapshot."""
    ids = [int(x) for x in nm_ids if x is not None]
    if not ids:
        return {}
    sql = text(
        """
        SELECT nm_id::bigint AS nm_id, COUNT(*)::int AS cnt
        FROM wb_search_report_keywords_cache
        WHERE snapshot_id = :snapshot_id
          AND nm_id = ANY(:nm_ids)
        GROUP BY nm_id
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"snapshot_id": int(snapshot_id), "nm_ids": ids}).fetchall()
    out: Dict[int, int] = {}
    for nm_id, cnt in rows:
        if nm_id is None:
            continue
        out[int(nm_id)] = int(cnt or 0)
    return out


def list_search_report_products_all(
    *,
    project_id: int,
    snapshot_id: int,
    q: Optional[str] = None,
    brand_name: Optional[str] = None,
    subject_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """List all products for snapshot (no pagination)."""
    where = ["p.project_id = :project_id", "p.snapshot_id = :snapshot_id"]
    params: Dict[str, Any] = {
        "project_id": int(project_id),
        "snapshot_id": int(snapshot_id),
    }
    if q:
        where.append("(p.name ILIKE :q OR p.vendor_code ILIKE :q OR CAST(p.nm_id AS text) ILIKE :q)")
        params["q"] = f"%{q}%"
    if brand_name:
        where.append("p.brand_name = :brand_name")
        params["brand_name"] = brand_name
    if subject_id is not None:
        # Some WB reports may miss subject_id; fall back to catalog/products table.
        where.append("COALESCE(p.subject_id, pr.subject_id) = :subject_id")
        params["subject_id"] = int(subject_id)

    where_sql = " AND ".join(where)
    sql = text(
        f"""
        SELECT
            p.nm_id, p.vendor_code, p.name, p.brand_name,
            COALESCE(p.subject_id, pr.subject_id) AS subject_id,
            COALESCE(p.subject_name, pr.subject_name, pr.category) AS subject_name,
            p.tag_id, p.tag_name,
            pr.vendor_code_norm AS vendor_code_norm,
            COALESCE(
                (
                    SELECT jsonb_agg(url) FROM (
                        SELECT
                            COALESCE(
                                pic->>'big',
                                pic->>'c246x328',
                                pic->>'square',
                                pic->>'tm',
                                pic->>'hq'
                            ) AS url
                        FROM jsonb_array_elements(COALESCE(pr.pics, '[]'::jsonb)) AS pic
                    ) t
                    WHERE url IS NOT NULL AND url <> ''
                ),
                '[]'::jsonb
            ) AS photos,
            p.metrics, p.raw, p.updated_at
        FROM wb_search_report_products p
        LEFT JOIN products pr
          ON pr.project_id = p.project_id
         AND CAST(pr.nm_id AS bigint) = p.nm_id
        WHERE {where_sql}
        ORDER BY p.nm_id ASC
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
    return [dict(r) for r in rows]


def list_search_report_subjects(
    *,
    project_id: int,
    snapshot_id: int,
    q: Optional[str] = None,
    brand_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List distinct WB categories (subject_id/subject_name) present in the snapshot slice."""
    # Some WB reports may miss subject_id; fall back to catalog/products table.
    where = [
        "p.project_id = :project_id",
        "p.snapshot_id = :snapshot_id",
        "COALESCE(p.subject_id, pr.subject_id) IS NOT NULL",
    ]
    params: Dict[str, Any] = {
        "project_id": int(project_id),
        "snapshot_id": int(snapshot_id),
    }
    if q:
        where.append("(p.name ILIKE :q OR p.vendor_code ILIKE :q OR CAST(p.nm_id AS text) ILIKE :q)")
        params["q"] = f"%{q}%"
    if brand_name:
        where.append("p.brand_name = :brand_name")
        params["brand_name"] = brand_name

    where_sql = " AND ".join(where)
    sql = text(
        f"""
        SELECT
            COALESCE(p.subject_id, pr.subject_id)::int AS subject_id,
            COALESCE(MAX(p.subject_name), MAX(pr.subject_name), MAX(pr.category)) AS subject_name,
            COUNT(*)::int AS products_cnt
        FROM wb_search_report_products p
        LEFT JOIN products pr
          ON pr.project_id = p.project_id
         AND CAST(pr.nm_id AS bigint) = p.nm_id
        WHERE {where_sql}
        GROUP BY COALESCE(p.subject_id, pr.subject_id)
        ORDER BY COALESCE(MAX(p.subject_name), MAX(pr.subject_name), MAX(pr.category)) ASC
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
    return [dict(r) for r in rows]


def create_search_report_snapshot(
    *,
    project_id: int,
    ingest_run_id: int,
    period_from: date,
    period_to: date,
    include_search_texts: bool,
    include_substituted_skus: bool,
    position_cluster: str,
    order_by: Dict[str, Any],
    request_params: Dict[str, Any],
) -> int:
    sql = text(
        """
        INSERT INTO wb_search_report_snapshots (
            project_id, period_from, period_to,
            include_search_texts, include_substituted_skus,
            position_cluster, order_by, request_params,
            ingest_run_id
        ) VALUES (
            :project_id, :period_from, :period_to,
            :include_search_texts, :include_substituted_skus,
            :position_cluster, CAST(:order_by AS jsonb), CAST(:request_params AS jsonb),
            :ingest_run_id
        )
        RETURNING id
        """
    )
    params = {
        "project_id": project_id,
        "period_from": period_from,
        "period_to": period_to,
        "include_search_texts": bool(include_search_texts),
        "include_substituted_skus": bool(include_substituted_skus),
        "position_cluster": str(position_cluster or "all"),
        "order_by": json.dumps(order_by or {}, ensure_ascii=False),
        "request_params": json.dumps(request_params or {}, ensure_ascii=False),
        "ingest_run_id": ingest_run_id,
    }
    with engine.begin() as conn:
        return int(conn.execute(sql, params).scalar_one())


def update_search_report_snapshot(
    *,
    snapshot_id: int,
    raw_main_page: Optional[Dict[str, Any]] = None,
    stats: Optional[Dict[str, Any]] = None,
) -> None:
    sets = []
    params: Dict[str, Any] = {"id": int(snapshot_id)}
    if raw_main_page is not None:
        sets.append("raw_main_page = CAST(:raw_main_page AS jsonb)")
        params["raw_main_page"] = json.dumps(raw_main_page, ensure_ascii=False)
    if stats is not None:
        sets.append("stats = CAST(:stats AS jsonb)")
        params["stats"] = json.dumps(stats, ensure_ascii=False)
    if not sets:
        return
    sql = text(
        f"""
        UPDATE wb_search_report_snapshots
        SET {", ".join(sets)},
            updated_at = NOW()
        WHERE id = :id
        """
    )
    with engine.begin() as conn:
        conn.execute(sql, params)


def delete_search_report_snapshot(*, snapshot_id: int) -> None:
    """Delete snapshot and cascade all related rows (products/scope/keywords cache)."""
    sql = text(
        """
        DELETE FROM wb_search_report_snapshots
        WHERE id = :id
        """
    )
    with engine.begin() as conn:
        conn.execute(sql, {"id": int(snapshot_id)})


def patch_search_report_snapshot_stats(*, snapshot_id: int, patch: Dict[str, Any]) -> None:
    if not patch:
        return
    sql = text(
        """
        UPDATE wb_search_report_snapshots
        SET stats = COALESCE(stats, '{}'::jsonb) || CAST(:patch AS jsonb),
            updated_at = NOW()
        WHERE id = :id
        """
    )
    with engine.begin() as conn:
        conn.execute(sql, {"id": int(snapshot_id), "patch": json.dumps(patch, ensure_ascii=False)})


def _extract_metrics(row: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    metrics: Dict[str, Any] = {}
    for k in (
        "avgPosition",
        "openCard",
        "addToCart",
        "openToCart",
        "orders",
        "cartToOrder",
        "visibility",
        "frequency",
        "weekFrequency",
    ):
        if k in row:
            metrics[k] = row.get(k)
    return metrics


def upsert_search_report_products(
    *,
    snapshot_id: int,
    project_id: int,
    ingest_run_id: int,
    rows: List[Dict[str, Any]],
) -> int:
    if not rows:
        return 0
    sql = text(
        """
        INSERT INTO wb_search_report_products (
            snapshot_id, project_id, nm_id,
            vendor_code, name, brand_name,
            subject_id, subject_name, tag_id, tag_name,
            metrics, raw, ingest_run_id
        ) VALUES (
            :snapshot_id, :project_id, :nm_id,
            :vendor_code, :name, :brand_name,
            :subject_id, :subject_name, :tag_id, :tag_name,
            CAST(:metrics AS jsonb), CAST(:raw AS jsonb), :ingest_run_id
        )
        ON CONFLICT (snapshot_id, nm_id) DO UPDATE SET
            vendor_code = EXCLUDED.vendor_code,
            name = EXCLUDED.name,
            brand_name = EXCLUDED.brand_name,
            subject_id = EXCLUDED.subject_id,
            subject_name = EXCLUDED.subject_name,
            tag_id = EXCLUDED.tag_id,
            tag_name = EXCLUDED.tag_name,
            metrics = EXCLUDED.metrics,
            raw = EXCLUDED.raw,
            ingest_run_id = EXCLUDED.ingest_run_id,
            updated_at = NOW()
        """
    )
    n = 0
    with engine.begin() as conn:
        for r in rows:
            if not isinstance(r, dict):
                continue
            nm_id = r.get("nmId") or r.get("nm_id")
            if nm_id is None:
                continue
            metrics = _extract_metrics(r)
            params = {
                "snapshot_id": int(snapshot_id),
                "project_id": int(project_id),
                "nm_id": int(nm_id),
                "vendor_code": r.get("vendorCode") or r.get("vendor_code"),
                "name": r.get("name") or r.get("productName") or r.get("title"),
                "brand_name": r.get("brandName"),
                "subject_id": r.get("subjectId"),
                "subject_name": r.get("subjectName"),
                "tag_id": r.get("tagId"),
                "tag_name": r.get("tagName"),
                "metrics": json.dumps(metrics or {}, ensure_ascii=False),
                "raw": json.dumps(r or {}, ensure_ascii=False),
                "ingest_run_id": int(ingest_run_id),
            }
            conn.execute(sql, params)
            n += 1
    return n


def list_search_report_snapshots(project_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    sql = text(
        """
        SELECT
            id, project_id, period_from, period_to,
            include_search_texts, include_substituted_skus,
            position_cluster, order_by, stats,
            ingest_run_id, created_at, updated_at
        FROM wb_search_report_snapshots
        WHERE project_id = :project_id
        ORDER BY id DESC
        LIMIT :lim
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"project_id": project_id, "lim": int(limit)}).mappings().all()
    return [dict(r) for r in rows]


def get_search_report_snapshot(project_id: int, snapshot_id: int) -> Optional[Dict[str, Any]]:
    sql = text(
        """
        SELECT
            id, project_id, period_from, period_to,
            include_search_texts, include_substituted_skus,
            position_cluster, order_by, request_params, raw_main_page, stats,
            ingest_run_id, created_at, updated_at
        FROM wb_search_report_snapshots
        WHERE project_id = :project_id AND id = :id
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(sql, {"project_id": project_id, "id": int(snapshot_id)}).mappings().first()
    return dict(row) if row else None


def list_search_report_products(
    *,
    project_id: int,
    snapshot_id: int,
    q: Optional[str] = None,
    brand_name: Optional[str] = None,
    subject_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 50,
) -> Tuple[List[Dict[str, Any]], int]:
    where = ["p.project_id = :project_id", "p.snapshot_id = :snapshot_id"]
    params: Dict[str, Any] = {
        "project_id": int(project_id),
        "snapshot_id": int(snapshot_id),
        "lim": int(page_size),
        "off": int((page - 1) * page_size),
    }
    if q:
        where.append("(p.name ILIKE :q OR p.vendor_code ILIKE :q OR CAST(p.nm_id AS text) ILIKE :q)")
        params["q"] = f"%{q}%"
    if brand_name:
        where.append("p.brand_name = :brand_name")
        params["brand_name"] = brand_name
    if subject_id is not None:
        where.append("p.subject_id = :subject_id")
        params["subject_id"] = int(subject_id)

    where_sql = " AND ".join(where)
    count_sql = text(
        f"""
        SELECT COUNT(*) FROM wb_search_report_products p
        WHERE {where_sql}
        """
    )
    sql = text(
        f"""
        SELECT
            p.nm_id, p.vendor_code, p.name, p.brand_name,
            p.subject_id, p.subject_name, p.tag_id, p.tag_name,
            pr.vendor_code_norm AS vendor_code_norm,
            COALESCE(
                (
                    SELECT jsonb_agg(url) FROM (
                        SELECT
                            COALESCE(
                                pic->>'big',
                                pic->>'c246x328',
                                pic->>'square',
                                pic->>'tm',
                                pic->>'hq'
                            ) AS url
                        FROM jsonb_array_elements(COALESCE(pr.pics, '[]'::jsonb)) AS pic
                    ) t
                    WHERE url IS NOT NULL AND url <> ''
                ),
                '[]'::jsonb
            ) AS photos,
            p.metrics, p.raw, p.updated_at
        FROM wb_search_report_products p
        LEFT JOIN products pr
          ON pr.project_id = p.project_id
         AND CAST(pr.nm_id AS bigint) = p.nm_id
        WHERE {where_sql}
        ORDER BY p.nm_id ASC
        LIMIT :lim OFFSET :off
        """
    )
    with engine.connect() as conn:
        total = int(conn.execute(count_sql, params).scalar() or 0)
        rows = conn.execute(sql, params).mappings().all()
    return ([dict(r) for r in rows], total)


def get_search_report_product_metrics(
    *,
    project_id: int,
    snapshot_id: int,
    nm_id: int,
) -> Optional[Dict[str, Any]]:
    sql = text(
        """
        SELECT metrics
        FROM wb_search_report_products
        WHERE project_id = :project_id AND snapshot_id = :snapshot_id AND nm_id = :nm_id
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(
            sql,
            {"project_id": int(project_id), "snapshot_id": int(snapshot_id), "nm_id": int(nm_id)},
        ).mappings().first()
    if not row:
        return None
    metrics = row.get("metrics")
    return metrics if isinstance(metrics, dict) else None


def rebuild_snapshot_scope_from_stock_daily(
    *,
    snapshot_id: int,
    project_id: int,
    period_from: date,
    period_to: date,
    min_required_qty: int,
) -> Dict[str, Any]:
    """Recompute qualifying nm_ids for snapshot using wb_stock_total_daily_snapshots.

    Qualifies if we have rows for ALL days in [period_from..period_to] and min(qty_total) >= min_required_qty.
    Missing day => not qualified (strict coverage).
    """
    if min_required_qty <= 0:
        raise ValueError("min_required_qty must be positive")
    days_total = (period_to - period_from).days + 1
    delete_sql = text(
        """
        DELETE FROM wb_search_report_snapshot_scope
        WHERE snapshot_id = :snapshot_id
        """
    )
    sql = text(
        """
        INSERT INTO wb_search_report_snapshot_scope (snapshot_id, nm_id, days_present, min_daily_qty, min_required_qty)
        SELECT
            :snapshot_id AS snapshot_id,
            nm_id,
            COUNT(*)::int AS days_present,
            MIN(qty_total)::int AS min_daily_qty,
            CAST(:min_required_qty AS int) AS min_required_qty
        FROM wb_stock_total_daily_snapshots
        WHERE project_id = :project_id
          AND snapshot_date >= :period_from
          AND snapshot_date <= :period_to
        GROUP BY nm_id
        HAVING COUNT(*) = :days_total
           AND MIN(qty_total) >= :min_required_qty
        ON CONFLICT (snapshot_id, nm_id) DO UPDATE SET
            days_present = EXCLUDED.days_present,
            min_daily_qty = EXCLUDED.min_daily_qty,
            min_required_qty = EXCLUDED.min_required_qty
        """
    )
    count_sql = text(
        """
        SELECT COUNT(*) FROM wb_search_report_snapshot_scope
        WHERE snapshot_id = :snapshot_id
        """
    )
    with engine.begin() as conn:
        conn.execute(delete_sql, {"snapshot_id": int(snapshot_id)})
        conn.execute(
            sql,
            {
                "snapshot_id": int(snapshot_id),
                "project_id": int(project_id),
                "period_from": period_from,
                "period_to": period_to,
                "days_total": int(days_total),
                "min_required_qty": int(min_required_qty),
            },
        )
        qualified_count = int(conn.execute(count_sql, {"snapshot_id": int(snapshot_id)}).scalar() or 0)
    return {"ok": True, "days_total": days_total, "qualified_count": qualified_count}


def get_keywords_cache(
    *,
    project_id: int,
    snapshot_id: int,
    nm_id: int,
    top_order_by: str,
    max_age_hours: int = 24,
) -> Optional[Dict[str, Any]]:
    """Return cached keyword items if fresh enough."""
    sql = text(
        """
        SELECT
            id, items, fetched_at, "limit"
        FROM wb_search_report_keywords_cache
        WHERE project_id = :project_id
          AND snapshot_id = :snapshot_id
          AND nm_id = :nm_id
          AND top_order_by = :top_order_by
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(
            sql,
            {
                "project_id": int(project_id),
                "snapshot_id": int(snapshot_id),
                "nm_id": int(nm_id),
                "top_order_by": str(top_order_by),
            },
        ).mappings().first()
    if not row:
        return None
    fetched_at = row.get("fetched_at")
    items = row.get("items") or []
    # If WB returned empty list, treat it as short-lived to avoid "sticky empty" cache.
    # In practice, empty often happens due to transient WB backend issues / rate limits.
    if max_age_hours > 0 and isinstance(items, list) and len(items) == 0 and isinstance(fetched_at, datetime):
        if fetched_at < (datetime.now(timezone.utc) - timedelta(minutes=10)):
            return None
    if isinstance(fetched_at, datetime) and max_age_hours > 0:
        if fetched_at < (datetime.now(timezone.utc) - timedelta(hours=int(max_age_hours))):
            return None
    return {"id": int(row["id"]), "items": items, "fetched_at": fetched_at, "limit": row.get("limit")}


def upsert_keywords_cache(
    *,
    project_id: int,
    snapshot_id: int,
    nm_id: int,
    top_order_by: str,
    limit: int,
    items: List[Dict[str, Any]],
    ingest_run_id: Optional[int] = None,
) -> None:
    sql = text(
        """
        INSERT INTO wb_search_report_keywords_cache (
            project_id, snapshot_id, nm_id, top_order_by,
            "limit", items, fetched_at, ingest_run_id
        ) VALUES (
            :project_id, :snapshot_id, :nm_id, :top_order_by,
            :lim, CAST(:items AS jsonb), NOW(), :ingest_run_id
        )
        ON CONFLICT (snapshot_id, nm_id, top_order_by) DO UPDATE SET
            "limit" = EXCLUDED."limit",
            items = EXCLUDED.items,
            fetched_at = NOW(),
            ingest_run_id = EXCLUDED.ingest_run_id,
            updated_at = NOW()
        """
    )
    with engine.begin() as conn:
        conn.execute(
            sql,
            {
                "project_id": int(project_id),
                "snapshot_id": int(snapshot_id),
                "nm_id": int(nm_id),
                "top_order_by": str(top_order_by),
                "lim": int(limit),
                "items": json.dumps(items or [], ensure_ascii=False),
                "ingest_run_id": int(ingest_run_id) if ingest_run_id is not None else None,
            },
        )
