"""Project-scoped Wildberries price discrepancies endpoints.

This module exposes:
- GET /api/v1/projects/{project_id}/wildberries/price-discrepancies
- GET /api/v1/projects/{project_id}/wildberries/price-discrepancies/export.csv
- GET /api/v1/projects/{project_id}/wildberries/categories

Data is aggregated from:
- products (article, nm_id, title, category, photos)
- rrp_snapshots (RRP price + stock from XML/1C)
- price_snapshots (WB admin price + WB discount)
- frontend_catalog_price_snapshots (showcase_price + spp from WB frontend)
- stock_snapshots (WB stock quantities)

All heavy joins and computations (diff_rub/diff_percent/is_below_rrp) are done
in SQL so that filtering and sorting are correct at the database layer.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy import text

from app.db import engine
from app.deps import get_current_active_user, get_project_membership

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/projects", tags=["wb-price-discrepancies"])


SortKey = Literal[
    "diff_rub_desc",
    "diff_rub_asc",
    "diff_percent_desc",
    "diff_percent_asc",
    "rrp_price_desc",
    "rrp_price_asc",
    "showcase_price_desc",
    "showcase_price_asc",
    "nm_id_desc",
    "nm_id_asc",
]


def _parse_sort(sort: Optional[str]) -> SortKey:
    """Parse sort string into an internal sort key with sane default."""
    default: SortKey = "diff_rub_desc"
    if not sort:
        return default
    sort_normalized = sort.strip().lower()
    mapping: Dict[str, SortKey] = {
        "diff_rub_desc": "diff_rub_desc",
        "diff_rub_asc": "diff_rub_asc",
        "diff_percent_desc": "diff_percent_desc",
        "diff_percent_asc": "diff_percent_asc",
        "rrp_price_desc": "rrp_price_desc",
        "rrp_price_asc": "rrp_price_asc",
        "showcase_price_desc": "showcase_price_desc",
        "showcase_price_asc": "showcase_price_asc",
        "nm_id_desc": "nm_id_desc",
        "nm_id_asc": "nm_id_asc",
    }
    return mapping.get(sort_normalized, default)


def _sort_to_order_clause(sort: SortKey) -> str:
    """Map internal sort key to SQL ORDER BY clause (without 'ORDER BY')."""
    if sort == "diff_rub_desc":
        return "diff_rub DESC NULLS LAST, nm_id"
    if sort == "diff_rub_asc":
        return "diff_rub ASC NULLS LAST, nm_id"
    if sort == "diff_percent_desc":
        return "diff_percent DESC NULLS LAST, nm_id"
    if sort == "diff_percent_asc":
        return "diff_percent ASC NULLS LAST, nm_id"
    if sort == "rrp_price_desc":
        return "rrp_price DESC NULLS LAST, nm_id"
    if sort == "rrp_price_asc":
        return "rrp_price ASC NULLS LAST, nm_id"
    if sort == "showcase_price_desc":
        return "showcase_price DESC NULLS LAST, nm_id"
    if sort == "showcase_price_asc":
        return "showcase_price ASC NULLS LAST, nm_id"
    if sort == "nm_id_desc":
        return "nm_id DESC"
    if sort == "nm_id_asc":
        return "nm_id ASC"
    # Fallback – should not be hit if mapping is exhaustive
    return "diff_rub DESC NULLS LAST, nm_id"


@dataclass
class DiscrepancyFilters:
    q: Optional[str]
    category_ids: List[int]
    only_below_rrp: bool
    has_wb_stock: Literal["any", "true", "false"]
    has_enterprise_stock: Literal["any", "true", "false"]
    sort: SortKey
    page: int
    page_size: int


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


def _build_discrepancies_sql(
    project_id: int, filters: DiscrepancyFilters
) -> Tuple[str, Dict[str, Any]]:
    """Return parametrized SQL and params for list/export queries.

    The query performs:
    - per-project scoping (project_id)
    - per-brand scoping for frontend snapshots via project_marketplaces/settings
    - latest snapshots for RRP/WB prices/frontend/stock
    - diff_rub/diff_percent/is_below_rrp computation in SQL
    - server-side filtering and sorting
    """
    order_clause = _sort_to_order_clause(filters.sort)

    where_clauses: List[str] = ["1=1"]
    params: Dict[str, Any] = {
        "project_id": project_id,
        "limit": filters.page_size,
        "offset": (filters.page - 1) * filters.page_size,
        "qpat": None,
        "category_ids": filters.category_ids or None,
    }

    # Search by article / nm_id / title
    if filters.q:
        q = filters.q.strip()
        params["qpat"] = f"%{q}%"
        # Try to parse numeric nm_id for more efficient filter
        try:
            qnum = int(q)
        except ValueError:
            qnum = None
        params["qnum"] = qnum
        where_clauses.append(
            """
            (
                (:qpat IS NOT NULL AND (
                    p.vendor_code_norm ILIKE :qpat
                    OR p.vendor_code ILIKE :qpat
                    OR p.title ILIKE :qpat
                ))
                OR (:qnum IS NOT NULL AND p.nm_id = :qnum)
            )
            """
        )
    else:
        params["qnum"] = None

    # Category filter (subject_id from products)
    if filters.category_ids:
        where_clauses.append("p.subject_id = ANY(:category_ids)")

    # Stock filters
    if filters.has_wb_stock == "true":
        where_clauses.append("COALESCE(stock_latest.wb_stock_qty, 0) > 0")
    elif filters.has_wb_stock == "false":
        where_clauses.append("COALESCE(stock_latest.wb_stock_qty, 0) <= 0")

    if filters.has_enterprise_stock == "true":
        where_clauses.append("COALESCE(rrp_latest.rrp_stock, 0) > 0")
    elif filters.has_enterprise_stock == "false":
        where_clauses.append("COALESCE(rrp_latest.rrp_stock, 0) <= 0")

    # Only below RRP – strictly handled on computed diff
    only_below_rrp_expr = ""
    if filters.only_below_rrp:
        only_below_rrp_expr = "AND computed.is_below_rrp = TRUE"

    where_sql = " AND ".join(where_clauses)

    sql = f"""
    WITH
    brand AS (
        SELECT pm.settings_json->>'brand_id' AS brand_id
        FROM project_marketplaces pm
        JOIN marketplaces m ON m.id = pm.marketplace_id
        WHERE pm.project_id = :project_id
          AND m.code = 'wildberries'
        LIMIT 1
    ),
    rrp_run AS (
        SELECT MAX(snapshot_at) AS run_at
        FROM rrp_snapshots
        WHERE project_id = :project_id
    ),
    stock_run AS (
        SELECT MAX(snapshot_at) AS run_at
        FROM stock_snapshots
        WHERE project_id = :project_id
    ),
    front_run AS (
        SELECT MAX(f.snapshot_at) AS run_at
        FROM frontend_catalog_price_snapshots f
        JOIN brand b ON b.brand_id IS NOT NULL
        WHERE f.query_type = 'brand'
          AND f.query_value = b.brand_id
    ),
    -- Latest RRP per vendor_code_norm
    rrp_latest AS (
        SELECT s.vendor_code_norm,
               MAX(s.rrp_price) AS rrp_price,
               MAX(s.rrp_stock) AS rrp_stock
        FROM rrp_snapshots s
        JOIN rrp_run r ON s.snapshot_at = r.run_at
        WHERE s.project_id = :project_id
        GROUP BY s.vendor_code_norm
    ),
    -- Latest WB admin price per nm_id
    wb_price_latest AS (
        SELECT DISTINCT ON (ps.nm_id)
            ps.nm_id::bigint AS nm_id,
            ps.wb_price        AS wb_admin_price,
            ps.wb_discount     AS wb_discount_percent,
            ps.created_at      AS wb_price_updated_at
        FROM price_snapshots ps
        WHERE ps.project_id = :project_id
        ORDER BY ps.nm_id, ps.created_at DESC
    ),
    -- Latest frontend showcase price per nm_id for this brand run
    front_latest AS (
        SELECT DISTINCT ON (f.nm_id)
            f.nm_id::bigint AS nm_id,
            f.price_product        AS showcase_price,
            f.discount_calc_percent AS spp_percent,
            f.snapshot_at          AS showcase_updated_at
        FROM frontend_catalog_price_snapshots f
        JOIN brand b ON b.brand_id IS NOT NULL
        JOIN front_run r ON f.snapshot_at = r.run_at
        WHERE f.query_type = 'brand'
          AND f.query_value = b.brand_id
        ORDER BY f.nm_id, f.snapshot_at DESC
    ),
    -- Latest WB stock per nm_id for this project
    stock_latest AS (
        SELECT ss.nm_id::bigint AS nm_id,
               SUM(COALESCE(ss.quantity, 0))::bigint AS wb_stock_qty
        FROM stock_snapshots ss
        JOIN stock_run r ON ss.snapshot_at = r.run_at
        WHERE ss.project_id = :project_id
        GROUP BY ss.nm_id
    ),
    base AS (
        SELECT
            p.nm_id::bigint AS nm_id,
            p.vendor_code_norm AS article,
            p.vendor_code AS article_raw,
            p.title AS title,
            p.subject_id AS category_id,
            p.subject_name AS category_name,
            p.pics AS pics_json,
            rrp_latest.rrp_price AS rrp_price,
            rrp_latest.rrp_stock AS enterprise_stock_qty,
            wb_price_latest.wb_admin_price,
            wb_price_latest.wb_discount_percent,
            front_latest.showcase_price,
            front_latest.spp_percent,
            stock_latest.wb_stock_qty,
            rrp_run.run_at     AS rrp_updated_at,
            stock_run.run_at   AS stock_updated_at,
            front_run.run_at   AS showcase_run_at,
            wb_price_latest.wb_price_updated_at
        FROM products p
        LEFT JOIN rrp_latest ON rrp_latest.vendor_code_norm = p.vendor_code_norm
        LEFT JOIN wb_price_latest ON wb_price_latest.nm_id = p.nm_id
        LEFT JOIN front_latest ON front_latest.nm_id = p.nm_id
        LEFT JOIN stock_latest ON stock_latest.nm_id = p.nm_id
        LEFT JOIN rrp_run ON TRUE
        LEFT JOIN stock_run ON TRUE
        LEFT JOIN front_run ON TRUE
        WHERE p.project_id = :project_id
          AND p.vendor_code_norm IS NOT NULL
          AND {where_sql}
    ),
    computed AS (
        SELECT
            b.*,
            CASE
                WHEN b.rrp_price IS NOT NULL
                 AND b.showcase_price IS NOT NULL
                THEN (b.rrp_price - b.showcase_price)
                ELSE NULL
            END AS diff_rub,
            CASE
                WHEN b.rrp_price IS NOT NULL
                 AND b.rrp_price > 0
                 AND b.showcase_price IS NOT NULL
                THEN ((b.rrp_price - b.showcase_price) / b.rrp_price) * 100.0
                ELSE NULL
            END AS diff_percent,
            CASE
                WHEN b.rrp_price IS NOT NULL
                 AND b.rrp_price > 0
                 AND b.wb_admin_price IS NOT NULL
                 AND b.wb_admin_price > 0
                 AND b.showcase_price IS NOT NULL
                 AND b.showcase_price > 0
                THEN ROUND(b.rrp_price * b.wb_admin_price / b.showcase_price)
                ELSE NULL
            END AS recommended_wb_admin_price,
            CASE
                WHEN b.rrp_price IS NOT NULL
                 AND b.rrp_price > 0
                 AND b.wb_admin_price IS NOT NULL
                 AND b.wb_admin_price > 0
                 AND b.showcase_price IS NOT NULL
                 AND b.showcase_price > 0
                THEN ROUND(b.rrp_price * b.wb_admin_price / b.showcase_price) - b.wb_admin_price
                ELSE NULL
            END AS delta_recommended,
            CASE
                WHEN b.rrp_price IS NOT NULL
                 AND b.rrp_price > 0
                 AND b.wb_admin_price IS NOT NULL
                 AND b.wb_admin_price > 0
                 AND b.showcase_price IS NOT NULL
                 AND b.showcase_price > 0
                THEN ROUND((ROUND(b.rrp_price * b.wb_admin_price / b.showcase_price)) * b.showcase_price / b.wb_admin_price)
                ELSE NULL
            END AS expected_showcase_price,
            CASE
                WHEN b.rrp_price IS NOT NULL
                 AND b.showcase_price IS NOT NULL
                 AND b.showcase_price < b.rrp_price
                THEN TRUE
                ELSE FALSE
            END AS is_below_rrp
        FROM base b
    ),
    filtered AS (
        SELECT *
        FROM computed
        WHERE 1=1
        {only_below_rrp_expr}
    ),
    counted AS (
        SELECT
            *,
            COUNT(*) OVER() AS total_count
        FROM filtered
    )
    SELECT
        nm_id,
        article,
        article_raw,
        title,
        category_id,
        category_name,
        pics_json,
        wb_admin_price,
        rrp_price,
        showcase_price,
        wb_discount_percent,
        spp_percent,
        wb_stock_qty,
        enterprise_stock_qty,
        diff_rub,
        diff_percent,
        recommended_wb_admin_price,
        delta_recommended,
        expected_showcase_price,
        is_below_rrp,
        rrp_updated_at,
        stock_updated_at,
        showcase_run_at,
        wb_price_updated_at,
        total_count
    FROM counted
    ORDER BY {order_clause}
    LIMIT :limit OFFSET :offset
    """

    return sql, params


def _row_to_item(row: Dict[str, Any]) -> Dict[str, Any]:
    """Transform a raw DB row into the API response item structure."""
    # Photos from products.pics (JSONB) -> list of URLs (first one is thumbnail)
    photos: List[str] = []
    raw_pics = row.get("pics_json")
    if raw_pics:
        try:
            # raw_pics may already be a Python list/dict if driver decodes JSONB
            if isinstance(raw_pics, str):
                import json

                pics_val = json.loads(raw_pics)
            else:
                pics_val = raw_pics
            if isinstance(pics_val, list):
                for pic in pics_val:
                    if isinstance(pic, dict):
                        url = pic.get("url") or pic.get("big") or pic.get("c128")
                        if url:
                            photos.append(str(url))
                    elif isinstance(pic, str):
                        photos.append(pic)
        except Exception:
            # Best-effort: if parsing fails, just skip photos
            photos = []

    prices = {
        "wb_admin_price": float(row["wb_admin_price"]) if row.get("wb_admin_price") is not None else None,
        "rrp_price": float(row["rrp_price"]) if row.get("rrp_price") is not None else None,
        "showcase_price": float(row["showcase_price"]) if row.get("showcase_price") is not None else None,
    }
    discounts = {
        "wb_discount_percent": float(row["wb_discount_percent"])
        if row.get("wb_discount_percent") is not None
        else None,
        "spp_percent": float(row["spp_percent"]) if row.get("spp_percent") is not None else None,
    }
    stocks = {
        "wb_stock_qty": int(row["wb_stock_qty"]) if row.get("wb_stock_qty") is not None else 0,
        "enterprise_stock_qty": int(row["enterprise_stock_qty"])
        if row.get("enterprise_stock_qty") is not None
        else 0,
    }
    computed = {
        "is_below_rrp": bool(row.get("is_below_rrp", False)),
        "diff_rub": float(row["diff_rub"]) if row.get("diff_rub") is not None else None,
        "diff_percent": float(row["diff_percent"]) if row.get("diff_percent") is not None else None,
        "recommended_wb_admin_price": float(row["recommended_wb_admin_price"])
        if row.get("recommended_wb_admin_price") is not None
        else None,
        "delta_recommended": float(row["delta_recommended"])
        if row.get("delta_recommended") is not None
        else None,
        "expected_showcase_price": float(row["expected_showcase_price"])
        if row.get("expected_showcase_price") is not None
        else None,
    }

    category = None
    if row.get("category_id") is not None or row.get("category_name") is not None:
        category = {
            "id": row.get("category_id"),
            "name": row.get("category_name"),
        }

    return {
        "article": row.get("article"),
        "nm_id": int(row["nm_id"]) if row.get("nm_id") is not None else None,
        "title": row.get("title"),
        "category": category,
        "photos": photos,
        "prices": prices,
        "discounts": discounts,
        "stocks": stocks,
        "computed": computed,
    }


def _get_updated_at(project_id: int) -> str:
    """Return ISO8601 updated_at for meta based on latest snapshot timestamps.

    If no data is available at all, fallback to `datetime.now(timezone.utc)`.
    """
    # We intentionally keep this as a separate lightweight query instead of
    # complicating the main aggregation SQL.
    with engine.connect() as conn:
        rrp_max = conn.execute(
            text("SELECT MAX(snapshot_at) FROM rrp_snapshots WHERE project_id = :project_id"),
            {"project_id": project_id},
        ).scalar()
        stock_max = conn.execute(
            text("SELECT MAX(snapshot_at) FROM stock_snapshots WHERE project_id = :project_id"),
            {"project_id": project_id},
        ).scalar()
        price_max = conn.execute(
            text("SELECT MAX(created_at) FROM price_snapshots WHERE project_id = :project_id"),
            {"project_id": project_id},
        ).scalar()
        front_max = conn.execute(
            text(
                """
                SELECT MAX(f.snapshot_at)
                FROM frontend_catalog_price_snapshots f
                JOIN project_marketplaces pm ON pm.project_id = :project_id
                JOIN marketplaces m ON m.id = pm.marketplace_id
                WHERE m.code = 'wildberries'
                  AND f.query_type = 'brand'
                  AND f.query_value = pm.settings_json->>'brand_id'
                """
            ),
            {"project_id": project_id},
        ).scalar()

    candidates = [
        ts
        for ts in [rrp_max, stock_max, price_max, front_max]
        if ts is not None
    ]
    if not candidates:
        return datetime.now(timezone.utc).isoformat()
    latest = max(candidates)
    # SQLAlchemy usually returns datetime with tzinfo; guard just in case.
    if isinstance(latest, datetime):
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        return latest.isoformat()
    return datetime.now(timezone.utc).isoformat()


@router.get("/{project_id}/wildberries/price-discrepancies")
async def get_wb_price_discrepancies(
    project_id: int = Path(..., description="Project ID"),
    q: Optional[str] = Query(None, description="Search by article/nmID/title"),
    category_ids: Optional[str] = Query(
        None,
        description='Comma-separated WB category/subject IDs, e.g. "1,2,3"',
        example="12,34,56",
    ),
    only_below_rrp: bool = Query(
        True,
        description="Filter: only items where showcase_price < rrp_price",
    ),
    has_wb_stock: Literal["any", "true", "false"] = Query(
        "any", description="Filter by WB stock quantity"
    ),
    has_enterprise_stock: Literal["any", "true", "false"] = Query(
        "any", description="Filter by enterprise (1C/XML) stock quantity"
    ),
    sort: Optional[str] = Query(
        "diff_rub_desc",
        description="Sort key, e.g. diff_rub_desc, diff_percent_desc, nm_id_asc",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Return price discrepancies between RRP and WB showcase price for a project.

    Always returns HTTP 200 with items/meta (never 404), even if no data is available.
    """
    start_time = datetime.now(timezone.utc)
    logger.info(
        f"get_wb_price_discrepancies: starting for project_id={project_id} "
        f"page={page} page_size={page_size} only_below_rrp={only_below_rrp}"
    )
    
    filters = DiscrepancyFilters(
        q=q,
        category_ids=_parse_category_ids(category_ids),
        only_below_rrp=only_below_rrp,
        has_wb_stock=has_wb_stock,
        has_enterprise_stock=has_enterprise_stock,
        sort=_parse_sort(sort),
        page=page,
        page_size=page_size,
    )

    sql, params = _build_discrepancies_sql(project_id, filters)

    items: List[Dict[str, Any]] = []
    total_count = 0
    
    # #region agent log
    import json
    try:
        with open(r'd:\Work\EcomCore\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "H1",
                "location": "api_wb_price_discrepancies.py:578",
                "message": "get_wb_price_discrepancies: before SQL execution",
                "data": {
                    "project_id": project_id,
                    "filters_only_below_rrp": filters.only_below_rrp,
                },
                "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion
    
    with engine.connect() as conn:
        # #region agent log
        # Diagnostic: Check data availability at each step
        try:
            # Check rrp_run (critical for JOIN)
            rrp_run_check = conn.execute(
                text("SELECT MAX(snapshot_at) AS run_at FROM rrp_snapshots WHERE project_id = :project_id"),
                {"project_id": project_id},
            ).scalar()
            
            # Check rrp_snapshots count
            rrp_count = conn.execute(
                text("SELECT COUNT(*) FROM rrp_snapshots WHERE project_id = :project_id"),
                {"project_id": project_id},
            ).scalar() or 0
            
            # Check products count
            products_count = conn.execute(
                text("SELECT COUNT(*) FROM products WHERE project_id = :project_id AND vendor_code_norm IS NOT NULL"),
                {"project_id": project_id},
            ).scalar() or 0
            
            # Check frontend prices count
            brand_check = conn.execute(
                text("""
                    SELECT pm.settings_json->>'brand_id' AS brand_id
                    FROM project_marketplaces pm
                    JOIN marketplaces m ON m.id = pm.marketplace_id
                    WHERE pm.project_id = :project_id AND m.code = 'wildberries'
                    LIMIT 1
                """),
                {"project_id": project_id},
            ).mappings().first()
            
            frontend_count = 0
            if brand_check and brand_check.get("brand_id"):
                frontend_count = conn.execute(
                    text("""
                        SELECT COUNT(*) FROM frontend_catalog_price_snapshots
                        WHERE query_type = 'brand' AND query_value = :brand_id
                    """),
                    {"brand_id": str(brand_check.get("brand_id"))},
                ).scalar() or 0
            
            # Check Internal Data availability
            internal_data_count = conn.execute(
                text("""
                    SELECT COUNT(*) FROM internal_product_prices ipp
                    JOIN internal_data_snapshots ids ON ipp.snapshot_id = ids.id
                    WHERE ids.project_id = :project_id AND ipp.rrp IS NOT NULL
                """),
                {"project_id": project_id},
            ).scalar() or 0
            
            # Check mapping: products with vendor_code_norm that match internal_sku
            mapping_count = conn.execute(
                text("""
                    SELECT COUNT(DISTINCT p.vendor_code_norm) FROM products p
                    JOIN internal_products ip ON ip.internal_sku = p.vendor_code_norm
                    JOIN internal_product_prices ipp ON ipp.internal_product_id = ip.id
                    JOIN internal_data_snapshots ids ON ipp.snapshot_id = ids.id
                    WHERE ids.project_id = :project_id AND p.project_id = :project_id
                      AND ipp.rrp IS NOT NULL
                """),
                {"project_id": project_id},
            ).scalar() or 0
            
            with open(r'd:\Work\EcomCore\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H1",
                    "location": "api_wb_price_discrepancies.py:620",
                    "message": "get_wb_price_discrepancies: data availability check",
                    "data": {
                        "project_id": project_id,
                        "rrp_snapshots_count": rrp_count,
                        "rrp_run_max_snapshot_at": rrp_run_check.isoformat() if rrp_run_check else None,
                        "products_with_vendor_code_norm": products_count,
                        "frontend_catalog_price_snapshots_count": frontend_count,
                        "internal_data_rrp_count": internal_data_count,
                        "products_mapped_to_internal_data": mapping_count,
                    },
                    "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            try:
                with open(r'd:\Work\EcomCore\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "H1",
                        "location": "api_wb_price_discrepancies.py:650",
                        "message": "get_wb_price_discrepancies: data availability check ERROR",
                        "data": {"error": str(e)},
                        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                    }, ensure_ascii=False) + "\n")
            except Exception:
                pass
        # #endregion
        
        result = conn.execute(text(sql), params).mappings().all()
        
        # #region agent log
        try:
            with open(r'd:\Work\EcomCore\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H2",
                    "location": "api_wb_price_discrepancies.py:680",
                    "message": "get_wb_price_discrepancies: SQL result rows",
                    "data": {
                        "project_id": project_id,
                        "rows_returned": len(result),
                    },
                    "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass
        # #endregion
        
        for row in result:
            row_dict = dict(row)
            total_count = int(row_dict.get("total_count", total_count or 0))
            items.append(_row_to_item(row_dict))
        
        # #region agent log
        # If no data, check intermediate CTE results
        if total_count == 0:
            try:
                # Test rrp_latest CTE directly
                rrp_latest_test = conn.execute(
                    text("""
                        WITH
                        rrp_run AS (
                            SELECT MAX(snapshot_at) AS run_at FROM rrp_snapshots WHERE project_id = :project_id
                        ),
                        rrp_latest AS (
                            SELECT s.vendor_code_norm, MAX(s.rrp_price) AS rrp_price
                            FROM rrp_snapshots s
                            JOIN rrp_run r ON s.snapshot_at = r.run_at
                            WHERE s.project_id = :project_id
                            GROUP BY s.vendor_code_norm
                        )
                        SELECT COUNT(*) AS count FROM rrp_latest
                    """),
                    {"project_id": project_id},
                ).scalar() or 0
                
                # Test base CTE (products with joins)
                base_test = conn.execute(
                    text("""
                        WITH
                        brand AS (
                            SELECT pm.settings_json->>'brand_id' AS brand_id
                            FROM project_marketplaces pm
                            JOIN marketplaces m ON m.id = pm.marketplace_id
                            WHERE pm.project_id = :project_id AND m.code = 'wildberries'
                            LIMIT 1
                        ),
                        rrp_run AS (
                            SELECT MAX(snapshot_at) AS run_at FROM rrp_snapshots WHERE project_id = :project_id
                        ),
                        front_run AS (
                            SELECT MAX(f.snapshot_at) AS run_at
                            FROM frontend_catalog_price_snapshots f
                            JOIN brand b ON b.brand_id IS NOT NULL
                            WHERE f.query_type = 'brand' AND f.query_value = b.brand_id
                        ),
                        rrp_latest AS (
                            SELECT s.vendor_code_norm, MAX(s.rrp_price) AS rrp_price
                            FROM rrp_snapshots s
                            JOIN rrp_run r ON s.snapshot_at = r.run_at
                            WHERE s.project_id = :project_id
                            GROUP BY s.vendor_code_norm
                        ),
                        front_latest AS (
                            SELECT DISTINCT ON (f.nm_id) f.nm_id::bigint AS nm_id, f.price_product AS showcase_price
                            FROM frontend_catalog_price_snapshots f
                            JOIN brand b ON b.brand_id IS NOT NULL
                            JOIN front_run r ON f.snapshot_at = r.run_at
                            WHERE f.query_type = 'brand' AND f.query_value = b.brand_id
                            ORDER BY f.nm_id, f.snapshot_at DESC
                        )
                        SELECT 
                            COUNT(*) AS products_total,
                            COUNT(rrp_latest.vendor_code_norm) AS products_with_rrp,
                            COUNT(front_latest.nm_id) AS products_with_frontend,
                            COUNT(CASE WHEN rrp_latest.vendor_code_norm IS NOT NULL AND front_latest.nm_id IS NOT NULL THEN 1 END) AS products_with_both
                        FROM products p
                        LEFT JOIN rrp_latest ON rrp_latest.vendor_code_norm = p.vendor_code_norm
                        LEFT JOIN front_latest ON front_latest.nm_id = p.nm_id
                        WHERE p.project_id = :project_id AND p.vendor_code_norm IS NOT NULL
                    """),
                    {"project_id": project_id},
                ).mappings().first()
                
                with open(r'd:\Work\EcomCore\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "H3",
                        "location": "api_wb_price_discrepancies.py:720",
                        "message": "get_wb_price_discrepancies: CTE analysis (empty result)",
                        "data": {
                            "project_id": project_id,
                            "rrp_latest_count": rrp_latest_test,
                            "products_total": base_test.get("products_total") if base_test else 0,
                            "products_with_rrp": base_test.get("products_with_rrp") if base_test else 0,
                            "products_with_frontend": base_test.get("products_with_frontend") if base_test else 0,
                            "products_with_both": base_test.get("products_with_both") if base_test else 0,
                            "only_below_rrp_filter": filters.only_below_rrp,
                        },
                        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                    }, ensure_ascii=False) + "\n")
            except Exception as e:
                try:
                    with open(r'd:\Work\EcomCore\.cursor\debug.log', 'a', encoding='utf-8') as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "H3",
                            "location": "api_wb_price_discrepancies.py:750",
                            "message": "get_wb_price_discrepancies: CTE analysis ERROR",
                            "data": {"error": str(e)},
                            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                        }, ensure_ascii=False) + "\n")
                except Exception:
                    pass
        # #endregion
    
    end_time = datetime.now(timezone.utc)
    elapsed_ms = (end_time - start_time).total_seconds() * 1000
    
    logger.info(
        f"get_wb_price_discrepancies: completed for project_id={project_id} "
        f"total_count={total_count} items_returned={len(items)} "
        f"elapsed={elapsed_ms:.2f}ms"
    )
    
    # If no data, check what's missing and add diagnostic info to response
    diagnostic_info = None
    if total_count == 0:
        logger.warning(
            f"get_wb_price_discrepancies: no data found for project_id={project_id}. "
            "Consider running diagnose_data_availability task to check prerequisites."
        )
        
        # Collect diagnostic information about missing data
        try:
            with engine.connect() as conn:
                # Check brand_id
                brand_check = conn.execute(
                    text("""
                        SELECT pm.settings_json->>'brand_id' AS brand_id, pm.is_enabled
                        FROM project_marketplaces pm
                        JOIN marketplaces m ON m.id = pm.marketplace_id
                        WHERE pm.project_id = :project_id AND m.code = 'wildberries'
                        LIMIT 1
                    """),
                    {"project_id": project_id},
                ).mappings().first()
                
                # Check table counts
                rrp_count = conn.execute(
                    text("SELECT COUNT(*) FROM rrp_snapshots WHERE project_id = :project_id"),
                    {"project_id": project_id},
                ).scalar() or 0
                
                price_count = conn.execute(
                    text("SELECT COUNT(*) FROM price_snapshots WHERE project_id = :project_id"),
                    {"project_id": project_id},
                ).scalar() or 0
                
                products_count = conn.execute(
                    text("SELECT COUNT(*) FROM products WHERE project_id = :project_id"),
                    {"project_id": project_id},
                ).scalar() or 0
                
                frontend_count = 0
                if brand_check and brand_check.get("brand_id"):
                    frontend_count = conn.execute(
                        text("""
                            SELECT COUNT(*) FROM frontend_catalog_price_snapshots
                            WHERE query_type = 'brand' AND query_value = :brand_id
                        """),
                        {"brand_id": str(brand_check.get("brand_id"))},
                    ).scalar() or 0
                
                stock_count = conn.execute(
                    text("SELECT COUNT(*) FROM stock_snapshots WHERE project_id = :project_id"),
                    {"project_id": project_id},
                ).scalar() or 0
                
                # Check how many products have both RRP and showcase prices
                products_with_both = conn.execute(
                    text("""
                        WITH
                        brand AS (
                            SELECT pm.settings_json->>'brand_id' AS brand_id
                            FROM project_marketplaces pm
                            JOIN marketplaces m ON m.id = pm.marketplace_id
                            WHERE pm.project_id = :project_id AND m.code = 'wildberries'
                            LIMIT 1
                        ),
                        rrp_run AS (
                            SELECT MAX(snapshot_at) AS run_at FROM rrp_snapshots WHERE project_id = :project_id
                        ),
                        front_run AS (
                            SELECT MAX(f.snapshot_at) AS run_at
                            FROM frontend_catalog_price_snapshots f
                            JOIN brand b ON b.brand_id IS NOT NULL
                            WHERE f.query_type = 'brand' AND f.query_value = b.brand_id
                        ),
                        rrp_latest AS (
                            SELECT s.vendor_code_norm, MAX(s.rrp_price) AS rrp_price
                            FROM rrp_snapshots s
                            JOIN rrp_run r ON s.snapshot_at = r.run_at
                            WHERE s.project_id = :project_id
                            GROUP BY s.vendor_code_norm
                        ),
                        front_latest AS (
                            SELECT DISTINCT ON (f.nm_id) f.nm_id::bigint AS nm_id, f.price_product AS showcase_price
                            FROM frontend_catalog_price_snapshots f
                            JOIN brand b ON b.brand_id IS NOT NULL
                            JOIN front_run r ON f.snapshot_at = r.run_at
                            WHERE f.query_type = 'brand' AND f.query_value = b.brand_id
                            ORDER BY f.nm_id, f.snapshot_at DESC
                        )
                        SELECT COUNT(*) AS count
                        FROM products p
                        LEFT JOIN rrp_latest ON rrp_latest.vendor_code_norm = p.vendor_code_norm
                        LEFT JOIN front_latest ON front_latest.nm_id = p.nm_id
                        WHERE p.project_id = :project_id
                          AND p.vendor_code_norm IS NOT NULL
                          AND rrp_latest.rrp_price IS NOT NULL
                          AND front_latest.showcase_price IS NOT NULL
                    """),
                    {"project_id": project_id},
                ).scalar() or 0
                
                # Safely extract brand_id
                brand_id_value = None
                if brand_check and brand_check.get("brand_id"):
                    try:
                        brand_id_value = int(brand_check.get("brand_id"))
                    except (ValueError, TypeError):
                        brand_id_value = None
                
                diagnostic_info = {
                    "data_availability": {
                        "brand_id_configured": brand_id_value is not None,
                        "brand_id": brand_id_value,
                        "rrp_snapshots_count": rrp_count,
                        "price_snapshots_count": price_count,
                        "products_count": products_count,
                        "frontend_catalog_price_snapshots_count": frontend_count,
                        "stock_snapshots_count": stock_count,
                        "products_with_both_rrp_and_showcase": products_with_both,
                    },
                    "issues": [],
                    "recommendations": [],
                }
                
                # Identify issues
                if not brand_check or not brand_check.get("brand_id"):
                    diagnostic_info["issues"].append("brand_id not configured in project_marketplaces.settings_json")
                    diagnostic_info["recommendations"].append("Configure brand_id in project marketplace settings")
                
                if rrp_count == 0:
                    diagnostic_info["issues"].append("No RRP snapshots found")
                    diagnostic_info["recommendations"].append("Run RRP XML ingestion: POST /api/v1/projects/{project_id}/ingest/run with domain='rrp_xml'")
                
                if frontend_count == 0 and brand_check and brand_check.get("brand_id"):
                    diagnostic_info["issues"].append("No frontend catalog price snapshots found")
                    diagnostic_info["recommendations"].append("Run frontend prices ingestion: POST /api/v1/projects/{project_id}/ingest/run with domain='frontend_prices'")
                
                if products_count == 0:
                    diagnostic_info["issues"].append("No products found")
                    diagnostic_info["recommendations"].append("Run products ingestion: POST /api/v1/projects/{project_id}/ingest/run with domain='products'")
                
                if products_with_both == 0 and rrp_count > 0 and frontend_count > 0:
                    diagnostic_info["issues"].append("No products have both RRP and showcase prices (mapping issue)")
                    diagnostic_info["recommendations"].append("Check vendor_code_norm mapping between products and rrp_snapshots")
        except Exception as e:
            logger.error(
                f"get_wb_price_discrepancies: error collecting diagnostic info for project_id={project_id}: {e}",
                exc_info=True
            )
            # Don't fail the request if diagnostic collection fails
            diagnostic_info = None

    updated_at_iso = _get_updated_at(project_id)

    response = {
        "meta": {
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "updated_at": updated_at_iso,
        },
        "items": items,
    }
    
    # Add diagnostic info if no data
    if diagnostic_info:
        response["diagnostic"] = diagnostic_info
    
    return response


@router.get("/{project_id}/wildberries/price-discrepancies/export.csv")
async def export_wb_price_discrepancies_csv(
    project_id: int = Path(..., description="Project ID"),
    q: Optional[str] = Query(None, description="Search by article/nmID/title"),
    category_ids: Optional[str] = Query(
        None,
        description='Comma-separated WB category/subject IDs, e.g. "1,2,3"',
        example="12,34,56",
    ),
    only_below_rrp: bool = Query(
        True,
        description="Filter: only items where showcase_price < rrp_price",
    ),
    has_wb_stock: Literal["any", "true", "false"] = Query(
        "any", description="Filter by WB stock quantity"
    ),
    has_enterprise_stock: Literal["any", "true", "false"] = Query(
        "any", description="Filter by enterprise (1C/XML) stock quantity"
    ),
    sort: Optional[str] = Query(
        "diff_rub_desc",
        description="Sort key, e.g. diff_rub_desc, diff_percent_desc, nm_id_asc",
    ),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Export price discrepancies as CSV with current filters and sort applied."""
    # Reuse the same SQL builder, but remove pagination limits for export.
    filters = DiscrepancyFilters(
        q=q,
        category_ids=_parse_category_ids(category_ids),
        only_below_rrp=only_below_rrp,
        has_wb_stock=has_wb_stock,
        has_enterprise_stock=has_enterprise_stock,
        sort=_parse_sort(sort),
        page=1,
        page_size=1000000,  # large upper bound; DB will still stream
    )
    sql, params = _build_discrepancies_sql(project_id, filters)
    # For export, we don't need COUNT(*) OVER(); but it's harmless to keep it.

    rows: List[Dict[str, Any]] = []
    with engine.connect() as conn:
        result = conn.execute(text(sql), params).mappings().all()
        for row in result:
            rows.append(dict(row))

    # Build CSV in memory
    import io
    import csv

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "article",
            "nm_id",
            "title",
            "wb_admin_price",
            "rrp_price",
            "showcase_price",
            "wb_discount_percent",
            "spp_percent",
            "diff_rub",
            "diff_percent",
            "recommended_wb_admin_price",
            "delta_recommended",
            "expected_showcase_price",
            "wb_stock_qty",
            "enterprise_stock_qty",
            "category_name",
        ]
    )

    for row in rows:
        item = _row_to_item(row)
        prices = item["prices"]
        discounts = item["discounts"]
        stocks = item["stocks"]
        computed = item["computed"]
        category = item.get("category") or {}

        writer.writerow(
            [
                item.get("article") or "",
                item.get("nm_id") or "",
                item.get("title") or "",
                prices.get("wb_admin_price") if prices.get("wb_admin_price") is not None else "",
                prices.get("rrp_price") if prices.get("rrp_price") is not None else "",
                prices.get("showcase_price") if prices.get("showcase_price") is not None else "",
                discounts.get("wb_discount_percent")
                if discounts.get("wb_discount_percent") is not None
                else "",
                discounts.get("spp_percent") if discounts.get("spp_percent") is not None else "",
                computed.get("diff_rub") if computed.get("diff_rub") is not None else "",
                computed.get("diff_percent") if computed.get("diff_percent") is not None else "",
                computed.get("recommended_wb_admin_price")
                if computed.get("recommended_wb_admin_price") is not None
                else "",
                computed.get("delta_recommended")
                if computed.get("delta_recommended") is not None
                else "",
                computed.get("expected_showcase_price")
                if computed.get("expected_showcase_price") is not None
                else "",
                stocks.get("wb_stock_qty") if stocks.get("wb_stock_qty") is not None else "",
                stocks.get("enterprise_stock_qty")
                if stocks.get("enterprise_stock_qty") is not None
                else "",
                category.get("name") or "",
            ]
        )

    csv_bytes = output.getvalue().encode("utf-8-sig")  # BOM for Excel-friendly CSV
    headers = {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="wb_price_discrepancies.csv"',
    }
    return Response(content=csv_bytes, media_type="text/csv", headers=headers)


@router.post("/{project_id}/wildberries/price-discrepancies/diagnose")
async def diagnose_price_discrepancies(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Trigger diagnostic task for price discrepancies data availability.
    
    This endpoint enqueues a Celery task to check:
    - brand_id configuration
    - RRP snapshots availability
    - Price snapshots availability
    - Frontend catalog price snapshots availability
    - Stock snapshots availability
    - Products availability
    - Mapping between products and RRP snapshots
    
    Returns task_id for tracking.
    """
    from app.tasks.price_discrepancies import diagnose_data_availability
    
    logger.info(f"diagnose_price_discrepancies: triggering diagnostics for project_id={project_id}")
    
    result = diagnose_data_availability.delay(project_id)
    
    return {
        "task_id": result.id,
        "status": "queued",
        "message": "Diagnostic task queued. Check worker logs for results.",
    }


@router.get("/{project_id}/wildberries/categories")
async def get_wb_categories(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Return list of WB categories for a project.

    If we don't have a dedicated categories table, fall back to distinct
    subject_id/subject_name from products for this project.
    """
    sql = text(
        """
        SELECT DISTINCT
            p.subject_id AS id,
            p.subject_name AS name
        FROM products p
        WHERE p.project_id = :project_id
          AND p.subject_id IS NOT NULL
        ORDER BY name NULLS LAST, id
        """
    )

    with engine.connect() as conn:
        result = conn.execute(sql, {"project_id": project_id}).mappings().all()
        items = [
            {
                "id": int(row["id"]),
                "name": row["name"],
            }
            for row in result
            if row.get("id") is not None
        ]

    return {"items": items}


