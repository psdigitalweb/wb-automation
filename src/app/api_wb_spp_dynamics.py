"""Project-scoped Wildberries SPP dynamics endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import text

from app.db import engine
from app.deps import get_current_active_user, get_project_membership


router = APIRouter(prefix="/api/v1/projects", tags=["wb-spp-dynamics"])

SortKey = Literal[
    "delta_desc",
    "delta_asc",
    "events_desc",
    "events_asc",
    "last_spp_desc",
    "last_spp_asc",
    "nm_id_asc",
    "nm_id_desc",
]


def _resolve_period(
    date_from: Optional[datetime],
    date_to: Optional[datetime],
) -> Tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    end = date_to or now
    start = date_from or (end - timedelta(days=30))

    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if start > end:
        raise HTTPException(status_code=400, detail="date_from must be before date_to")

    return start, end


def _parse_sort(sort: Optional[str]) -> SortKey:
    allowed: set[str] = {
        "delta_desc",
        "delta_asc",
        "events_desc",
        "events_asc",
        "last_spp_desc",
        "last_spp_asc",
        "nm_id_asc",
        "nm_id_desc",
    }
    value = (sort or "delta_desc").strip().lower()
    return value if value in allowed else "delta_desc"  # type: ignore[return-value]


def _sort_to_order(sort: SortKey) -> str:
    mapping = {
        "delta_desc": "abs_delta_spp DESC NULLS LAST, nm_id",
        "delta_asc": "abs_delta_spp ASC NULLS LAST, nm_id",
        "events_desc": "events_count DESC NULLS LAST, abs_delta_spp DESC NULLS LAST, nm_id",
        "events_asc": "events_count ASC NULLS LAST, abs_delta_spp DESC NULLS LAST, nm_id",
        "last_spp_desc": "last_spp_percent DESC NULLS LAST, nm_id",
        "last_spp_asc": "last_spp_percent ASC NULLS LAST, nm_id",
        "nm_id_asc": "nm_id ASC",
        "nm_id_desc": "nm_id DESC",
    }
    return mapping[sort]


def _parse_category_ids(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    result: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.append(int(part))
        except ValueError:
            continue
    return result


def _parse_product_photos(raw_pics: Any) -> List[str]:
    photos: List[str] = []
    if not raw_pics:
        return photos
    try:
        pics_val = json.loads(raw_pics) if isinstance(raw_pics, str) else raw_pics
        if isinstance(pics_val, list):
            for pic in pics_val:
                if isinstance(pic, dict):
                    url = pic.get("url") or pic.get("big") or pic.get("c128")
                    if url:
                        photos.append(str(url))
                elif isinstance(pic, str):
                    photos.append(pic)
    except (TypeError, ValueError):
        return []
    return photos


def _items_base_sql(search_clause: str, having_clause: str = "") -> str:
    return f"""
        WITH product_scope AS (
            SELECT DISTINCT
                p.nm_id::bigint AS nm_id,
                p.vendor_code,
                p.vendor_code_norm,
                p.category,
                p.subject_name,
                p.pics AS pics_json
            FROM products p
            WHERE p.project_id = :project_id
              AND p.nm_id IS NOT NULL
              {search_clause}
        ),
        period_points AS (
            SELECT
                s.project_id,
                s.nm_id::bigint AS nm_id,
                s.snapshot_at,
                s.spp_percent,
                s.price_showcase
            FROM wb_showcase_price_snapshots s
            JOIN product_scope ps ON ps.nm_id = s.nm_id
            WHERE s.project_id = :project_id
              AND s.snapshot_at >= :date_from
              AND s.snapshot_at <= :date_to
        ),
        first_points AS (
            SELECT DISTINCT ON (nm_id)
                nm_id,
                spp_percent AS first_spp_percent,
                price_showcase AS first_price_showcase,
                snapshot_at AS first_snapshot_at
            FROM period_points
            ORDER BY nm_id, snapshot_at ASC
        ),
        last_points AS (
            SELECT DISTINCT ON (nm_id)
                nm_id,
                spp_percent AS last_spp_percent,
                price_showcase AS last_price_showcase,
                snapshot_at AS last_snapshot_at
            FROM period_points
            ORDER BY nm_id, snapshot_at DESC
        ),
        point_stats AS (
            SELECT
                nm_id,
                MIN(spp_percent) AS min_spp_percent,
                ROUND(AVG(spp_percent)::numeric, 2) AS avg_spp_percent,
                MAX(spp_percent) AS max_spp_percent,
                COUNT(*)::bigint AS points_count
            FROM period_points
            GROUP BY nm_id
        ),
        event_stats AS (
            SELECT
                e.nm_id::bigint AS nm_id,
                COUNT(*)::bigint AS events_count,
                MAX(ABS(e.spp_percent - COALESCE(e.prev_spp_percent, e.spp_percent))) AS max_event_delta,
                MAX(e.changed_at) AS last_changed_at
            FROM wb_spp_events e
            JOIN product_scope ps ON ps.nm_id = e.nm_id
            WHERE e.project_id = :project_id
              AND e.changed_at >= :date_from
              AND e.changed_at <= :date_to
            GROUP BY e.nm_id
        ),
        latest_front_names AS (
            SELECT DISTINCT ON (f.nm_id)
                f.nm_id::bigint AS nm_id,
                f.name
            FROM frontend_catalog_price_snapshots f
            JOIN product_scope ps ON ps.nm_id = f.nm_id
            WHERE f.name IS NOT NULL
            ORDER BY f.nm_id, f.snapshot_at DESC
        ),
        item_rows AS (
            SELECT
                ps.nm_id,
                COALESCE(ps.vendor_code_norm, ps.vendor_code) AS vendor_code,
                COALESCE(lfn.name, ps.category, ps.subject_name) AS name,
                ps.category,
                ps.subject_name,
                ps.pics_json,
                fp.first_spp_percent,
                lp.last_spp_percent,
                (lp.last_spp_percent - fp.first_spp_percent) AS delta_spp,
                ABS(lp.last_spp_percent - fp.first_spp_percent) AS abs_delta_spp,
                pst.min_spp_percent,
                pst.avg_spp_percent,
                pst.max_spp_percent,
                pst.points_count,
                COALESCE(es.events_count, 0)::bigint AS events_count,
                es.max_event_delta,
                es.last_changed_at,
                fp.first_price_showcase,
                lp.last_price_showcase,
                fp.first_snapshot_at,
                lp.last_snapshot_at
            FROM product_scope ps
            JOIN first_points fp ON fp.nm_id = ps.nm_id
            JOIN last_points lp ON lp.nm_id = ps.nm_id
            JOIN point_stats pst ON pst.nm_id = ps.nm_id
            LEFT JOIN event_stats es ON es.nm_id = ps.nm_id
            LEFT JOIN latest_front_names lfn ON lfn.nm_id = ps.nm_id
        )
        SELECT *
        FROM item_rows
        {having_clause}
    """


@router.get("/{project_id}/wildberries/spp-dynamics/summary")
async def get_spp_dynamics_summary(
    project_id: int = Path(..., description="Project ID"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    category_ids: Optional[str] = Query(None, description="Comma-separated WB subject/category IDs"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
) -> Dict[str, Any]:
    start, end = _resolve_period(date_from, date_to)
    parsed_category_ids = _parse_category_ids(category_ids)
    category_clause = "AND subject_id = ANY(:category_ids)" if parsed_category_ids else ""
    sql = text(
        f"""
        WITH product_scope AS (
            SELECT DISTINCT nm_id::bigint AS nm_id
            FROM products
            WHERE project_id = :project_id
              AND nm_id IS NOT NULL
              {category_clause}
        ),
        period_points AS (
            SELECT s.nm_id::bigint AS nm_id, s.snapshot_at, s.spp_percent
            FROM wb_showcase_price_snapshots s
            JOIN product_scope ps ON ps.nm_id = s.nm_id
            WHERE s.project_id = :project_id
              AND s.snapshot_at >= :date_from
              AND s.snapshot_at <= :date_to
        ),
        first_points AS (
            SELECT DISTINCT ON (nm_id) nm_id, spp_percent
            FROM period_points
            ORDER BY nm_id, snapshot_at ASC
        ),
        last_points AS (
            SELECT DISTINCT ON (nm_id) nm_id, spp_percent
            FROM period_points
            ORDER BY nm_id, snapshot_at DESC
        ),
        item_deltas AS (
            SELECT
                fp.nm_id,
                fp.spp_percent AS first_spp_percent,
                lp.spp_percent AS last_spp_percent,
                ABS(lp.spp_percent - fp.spp_percent) AS abs_delta_spp
            FROM first_points fp
            JOIN last_points lp ON lp.nm_id = fp.nm_id
        ),
        events AS (
            SELECT e.nm_id::bigint AS nm_id
            FROM wb_spp_events e
            JOIN product_scope ps ON ps.nm_id = e.nm_id
            WHERE e.project_id = :project_id
              AND e.changed_at >= :date_from
              AND e.changed_at <= :date_to
        )
        SELECT
            (SELECT COUNT(*) FROM product_scope)::bigint AS total_products,
            (SELECT COUNT(*) FROM item_deltas)::bigint AS products_with_spp,
            (SELECT COUNT(DISTINCT nm_id) FROM events)::bigint AS products_with_events,
            (SELECT COUNT(*) FROM events)::bigint AS events_count,
            ROUND((SELECT AVG(first_spp_percent)::numeric FROM item_deltas), 2) AS avg_spp_start,
            ROUND((SELECT AVG(last_spp_percent)::numeric FROM item_deltas), 2) AS avg_spp_end,
            (SELECT MAX(abs_delta_spp) FROM item_deltas) AS max_abs_delta_spp
        """
    )
    with engine.connect() as conn:
        row = conn.execute(
            sql,
            {
                "project_id": project_id,
                "date_from": start,
                "date_to": end,
                "category_ids": parsed_category_ids,
            },
        ).mappings().one()

    return {
        "period": {"date_from": start.isoformat(), "date_to": end.isoformat()},
        "total_products": int(row["total_products"] or 0),
        "products_with_spp": int(row["products_with_spp"] or 0),
        "products_with_events": int(row["products_with_events"] or 0),
        "events_count": int(row["events_count"] or 0),
        "avg_spp_start": float(row["avg_spp_start"]) if row["avg_spp_start"] is not None else None,
        "avg_spp_end": float(row["avg_spp_end"]) if row["avg_spp_end"] is not None else None,
        "max_abs_delta_spp": int(row["max_abs_delta_spp"]) if row["max_abs_delta_spp"] is not None else None,
    }


@router.get("/{project_id}/wildberries/spp-dynamics/items")
async def get_spp_dynamics_items(
    project_id: int = Path(..., description="Project ID"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    q: Optional[str] = Query(None, description="Search by vendor code, nmId, or product name"),
    category_ids: Optional[str] = Query(None, description="Comma-separated WB subject/category IDs"),
    only_changed: bool = Query(False),
    min_delta: int = Query(0, ge=0, le=100),
    sort: Optional[str] = Query("delta_desc"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
) -> Dict[str, Any]:
    start, end = _resolve_period(date_from, date_to)
    sort_key = _parse_sort(sort)
    order_clause = _sort_to_order(sort_key)

    params: Dict[str, Any] = {
        "project_id": project_id,
        "date_from": start,
        "date_to": end,
        "limit": limit,
        "offset": offset,
        "min_delta": min_delta,
    }

    search_parts: List[str] = []
    if q and q.strip():
        query = q.strip()
        params["q_pat"] = f"%{query}%"
        try:
            params["q_nm_id"] = int(query)
        except ValueError:
            params["q_nm_id"] = None
        search_parts.append(
            """
                (
                p.vendor_code ILIKE :q_pat
                OR p.vendor_code_norm ILIKE :q_pat
                OR p.category ILIKE :q_pat
                OR p.subject_name ILIKE :q_pat
                OR (:q_nm_id IS NOT NULL AND p.nm_id = :q_nm_id)
                )
            """
        )

    parsed_category_ids = _parse_category_ids(category_ids)
    if parsed_category_ids:
        params["category_ids"] = parsed_category_ids
        search_parts.append("p.subject_id = ANY(:category_ids)")

    search_clause = ""
    if search_parts:
        search_clause = "AND " + " AND ".join(search_parts)

    having_parts = ["abs_delta_spp >= :min_delta"]
    if only_changed:
        having_parts.append("(events_count > 0 OR abs_delta_spp > 0)")
    having_clause = "WHERE " + " AND ".join(having_parts)

    base_sql = _items_base_sql(search_clause=search_clause, having_clause=having_clause)
    list_sql = text(
        f"""
        {base_sql}
        ORDER BY {order_clause}
        LIMIT :limit OFFSET :offset
        """
    )
    count_sql = text(f"SELECT COUNT(*)::bigint AS total FROM ({base_sql}) counted")

    with engine.connect() as conn:
        rows = conn.execute(list_sql, params).mappings().all()
        total = conn.execute(count_sql, params).scalar_one()

    items = []
    for row in rows:
        items.append(
            {
                "nm_id": int(row["nm_id"]),
                "vendor_code": row.get("vendor_code"),
                "name": row.get("name"),
                "category": row.get("category"),
                "subject_name": row.get("subject_name"),
                "photos": _parse_product_photos(row.get("pics_json")),
                "first_spp_percent": int(row["first_spp_percent"]) if row["first_spp_percent"] is not None else None,
                "last_spp_percent": int(row["last_spp_percent"]) if row["last_spp_percent"] is not None else None,
                "delta_spp": int(row["delta_spp"]) if row["delta_spp"] is not None else None,
                "abs_delta_spp": int(row["abs_delta_spp"]) if row["abs_delta_spp"] is not None else None,
                "min_spp_percent": int(row["min_spp_percent"]) if row["min_spp_percent"] is not None else None,
                "avg_spp_percent": float(row["avg_spp_percent"]) if row["avg_spp_percent"] is not None else None,
                "max_spp_percent": int(row["max_spp_percent"]) if row["max_spp_percent"] is not None else None,
                "points_count": int(row["points_count"] or 0),
                "events_count": int(row["events_count"] or 0),
                "max_event_delta": int(row["max_event_delta"]) if row["max_event_delta"] is not None else None,
                "last_changed_at": row["last_changed_at"].isoformat() if row.get("last_changed_at") else None,
                "first_price_showcase": float(row["first_price_showcase"]) if row["first_price_showcase"] is not None else None,
                "last_price_showcase": float(row["last_price_showcase"]) if row["last_price_showcase"] is not None else None,
                "first_snapshot_at": row["first_snapshot_at"].isoformat() if row.get("first_snapshot_at") else None,
                "last_snapshot_at": row["last_snapshot_at"].isoformat() if row.get("last_snapshot_at") else None,
            }
        )

    return {
        "period": {"date_from": start.isoformat(), "date_to": end.isoformat()},
        "items": items,
        "meta": {"total": int(total or 0), "limit": limit, "offset": offset, "sort": sort_key},
    }


@router.get("/{project_id}/wildberries/spp-dynamics/items/{nm_id}/series")
async def get_spp_dynamics_item_series(
    project_id: int = Path(..., description="Project ID"),
    nm_id: int = Path(..., description="Wildberries nmId"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
) -> Dict[str, Any]:
    start, end = _resolve_period(date_from, date_to)
    params = {"project_id": project_id, "nm_id": nm_id, "date_from": start, "date_to": end}

    product_sql = text(
        """
        SELECT
            p.nm_id::bigint AS nm_id,
            COALESCE(p.vendor_code_norm, p.vendor_code) AS vendor_code,
            p.category,
            p.subject_name,
            (
                SELECT f.name
                FROM frontend_catalog_price_snapshots f
                WHERE f.nm_id = p.nm_id
                  AND f.name IS NOT NULL
                ORDER BY f.snapshot_at DESC
                LIMIT 1
            ) AS frontend_name
        FROM products p
        WHERE p.project_id = :project_id
          AND p.nm_id = :nm_id
        LIMIT 1
        """
    )
    points_sql = text(
        """
        SELECT snapshot_at, spp_percent, price_showcase
        FROM wb_showcase_price_snapshots
        WHERE project_id = :project_id
          AND nm_id = :nm_id
          AND snapshot_at >= :date_from
          AND snapshot_at <= :date_to
        ORDER BY snapshot_at
        """
    )
    admin_price_sql = text(
        """
        SELECT created_at, wb_price
        FROM price_snapshots
        WHERE project_id = :project_id
          AND nm_id = :nm_id
          AND created_at >= :date_from
          AND created_at <= :date_to
          AND wb_price IS NOT NULL
        ORDER BY created_at
        """
    )
    events_sql = text(
        """
        SELECT changed_at, prev_spp_percent, spp_percent, ingest_run_id
        FROM wb_spp_events
        WHERE project_id = :project_id
          AND nm_id = :nm_id
          AND changed_at >= :date_from
          AND changed_at <= :date_to
        ORDER BY changed_at
        """
    )
    sales_sql = text(
        """
        WITH sales_raw AS (
            SELECT
                COALESCE(
                    (r.payload->>'sale_dt')::date,
                    (r.payload->>'saleDt')::date,
                    (r.payload->>'rr_dt')::date,
                    rf.period_to
                ) AS sale_date,
                COALESCE(
                    NULLIF(
                        CASE
                            WHEN COALESCE(r.payload->>'quantity', '') ~ '^[0-9]+(\\.[0-9]+)?$'
                            THEN (r.payload->>'quantity')::numeric
                            ELSE NULL
                        END,
                        0
                    ),
                    NULLIF(
                        CASE
                            WHEN COALESCE(r.payload->>'qty', '') ~ '^[0-9]+(\\.[0-9]+)?$'
                            THEN (r.payload->>'qty')::numeric
                            ELSE NULL
                        END,
                        0
                    ),
                    1
                ) AS qty,
                CASE
                    WHEN COALESCE(r.payload->>'retail_amount', '') ~ '^-?[0-9]+(\\.[0-9]+)?$'
                    THEN (r.payload->>'retail_amount')::numeric
                    ELSE 0
                END AS retail_amount
            FROM wb_finance_report_lines r
            JOIN wb_finance_reports rf ON rf.project_id = r.project_id
                AND rf.report_id = r.report_id
                AND rf.marketplace_code = 'wildberries'
            WHERE r.project_id = :project_id
              AND rf.period_from <= :date_to_date
              AND rf.period_to >= :date_from_date
              AND COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$'
              AND COALESCE(r.payload->>'nm_id', r.payload->>'nmId')::bigint = :nm_id
              AND COALESCE(r.payload->>'supplier_oper_name', r.payload->>'supplierOperName') = 'Продажа'
              AND COALESCE(r.payload->>'doc_type_name', r.payload->>'docTypeName', '') != 'Возврат'
        )
        SELECT
            sale_date,
            COALESCE(SUM(qty), 0)::numeric AS units_sold,
            COALESCE(SUM(retail_amount), 0)::numeric AS gross_sales
        FROM sales_raw
        WHERE sale_date >= :date_from_date
          AND sale_date <= :date_to_date
        GROUP BY sale_date
        ORDER BY sale_date
        """
    )

    with engine.connect() as conn:
        product = conn.execute(product_sql, params).mappings().fetchone()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found in this project")
        points = conn.execute(points_sql, params).mappings().all()
        admin_prices = conn.execute(admin_price_sql, params).mappings().all()
        events = conn.execute(events_sql, params).mappings().all()
        sales = conn.execute(
            sales_sql,
            {**params, "date_from_date": start.date(), "date_to_date": end.date()},
        ).mappings().all()

    return {
        "period": {"date_from": start.isoformat(), "date_to": end.isoformat()},
        "product": {
            "nm_id": int(product["nm_id"]),
            "vendor_code": product.get("vendor_code"),
            "name": product.get("frontend_name") or product.get("category") or product.get("subject_name"),
            "category": product.get("category"),
            "subject_name": product.get("subject_name"),
        },
        "points": [
            {
                "snapshot_at": row["snapshot_at"].isoformat(),
                "spp_percent": int(row["spp_percent"]) if row["spp_percent"] is not None else None,
                "price_showcase": float(row["price_showcase"]) if row["price_showcase"] is not None else None,
            }
            for row in points
        ],
        "admin_price_points": [
            {
                "created_at": row["created_at"].isoformat(),
                "wb_price": float(row["wb_price"]) if row["wb_price"] is not None else None,
            }
            for row in admin_prices
        ],
        "events": [
            {
                "changed_at": row["changed_at"].isoformat(),
                "prev_spp_percent": int(row["prev_spp_percent"]) if row["prev_spp_percent"] is not None else None,
                "spp_percent": int(row["spp_percent"]),
                "ingest_run_id": int(row["ingest_run_id"]) if row["ingest_run_id"] is not None else None,
            }
            for row in events
        ],
        "sales_daily": [
            {
                "date": row["sale_date"].isoformat(),
                "units_sold": float(row["units_sold"] or 0),
                "gross_sales": float(row["gross_sales"] or 0),
            }
            for row in sales
        ],
    }
