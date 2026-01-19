"""Project-scoped Articles Base endpoint.

This endpoint provides a denormalized "article base" table per project, combining:
- products (vendor_code, nm_id)
- latest RRP XML snapshot (rrp_price, rrp_stock)
- latest WB price snapshot (wb_price, wb_discount)
- latest WB stock snapshot (stock_wb)
- latest frontend prices snapshot for project brand_id (showcase_price, spp)

It is designed for the frontend page /app/project/{projectId}/articles-base.
"""

from __future__ import annotations

import time
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import text

from app.db import engine
from app.deps import get_current_active_user, get_project_membership
from app.utils.ttl_cache import (
    delete as cache_delete,
    get_json as cache_get_json,
    set_json as cache_set_json,
)


router = APIRouter(prefix="/api/v1/projects", tags=["articles-base"])


SortField = Literal[
    "vendor_code_norm",
    "nm_id",
    "rrp_price",
    "wb_price",
    "spp",
    "stock_wb",
    "stock_1c",
]


def _parse_sort(sort: Optional[str]) -> tuple[SortField, str]:
    if not sort:
        return ("vendor_code_norm", "asc")
    parts = [p.strip() for p in sort.split(":", 1)]
    field = parts[0] or "vendor_code_norm"
    direction = (parts[1] if len(parts) > 1 else "asc").lower()
    if direction not in ("asc", "desc"):
        direction = "asc"
    allowed = {
        "vendor_code_norm",
        "nm_id",
        "rrp_price",
        "wb_price",
        "spp",
        "stock_wb",
        "stock_1c",
    }
    if field not in allowed:
        field = "vendor_code_norm"
    return (field, direction)  # type: ignore[return-value]


@router.get("/{project_id}/articles-base")
async def get_project_articles_base(
    project_id: int = Path(..., description="Project ID"),
    q: Optional[str] = Query(None, description="Search by vendor_code_norm (ILIKE) or nm_id if numeric"),
    only_in_stock_wb: bool = Query(False, description="[DEPRECATED] Use has_fbs_stock. Filter: FBS stock qty > 0"),
    only_in_stock_1c: bool = Query(False, description="[DEPRECATED] 1C is not part of current UI schema"),
    any_missing: bool = Query(False, description="Filter: missing any of (rrp/wb_stock/wb_price/front)"),
    missing_rrp: bool = Query(False, description="Filter: missing RRP (by vendor_code_norm)"),
    missing_wb_stock: bool = Query(False, description="[DEPRECATED] Alias for missing_fbs_stock"),
    missing_wb_price: bool = Query(False, description="Filter: missing WB price snapshot (by nm_id)"),
    missing_front: bool = Query(False, description="Filter: missing frontend price (by nm_id + brand_id run)"),
    has_fbs_stock: bool = Query(False, description="Filter: FBS stock qty > 0 (WB merchant availability)"),
    missing_fbs_stock: bool = Query(False, description="Filter: missing FBS stock (qty = 0)"),
    has_fbo_stock: bool = Query(False, description="Filter: FBO stock qty > 0 (WB warehouses / supplier stocks)"),
    missing_fbo_stock: bool = Query(False, description="Filter: missing FBO stock (qty = 0)"),
    any_missing_stock: bool = Query(False, description="Filter: missing both FBS and FBO stock (qty = 0 for both)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    sort: Optional[str] = Query(None, description="Sort like 'nm_id:desc'"),
    debug: int = Query(0, ge=0, le=1, description="Include debug fields (elapsed_ms)"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    sort_field, sort_dir = _parse_sort(sort)
    # IMPORTANT: ordering must happen before heavy joins. Therefore, we only order
    # by fields available in the "keys" phase (vendor_code_norm/nm_id/rrp/stock).
    # For other sort fields we fall back to nm_id.
    sort_map_keys = {
        "vendor_code_norm": "p.vendor_code_norm",
        "nm_id": "p.nm_id",
        "rrp_price": "p.rrp_price",
        "wb_price": "p.nm_id",
        "spp": "p.nm_id",
        # stock_wb is deprecated naming; in Phase-1 we model it as FBS qty
        "stock_wb": "p.fbs_stock_qty",
        "stock_1c": "p.rrp_stock",
    }
    sort_map_final = {
        "vendor_code_norm": "k.vendor_code_norm",
        "nm_id": "k.nm_id",
        "rrp_price": "k.rrp_price",
        "wb_price": "k.nm_id",
        "spp": "k.nm_id",
        "stock_wb": "k.fbs_stock_qty",
        "stock_1c": "k.rrp_stock",
    }
    order_by_keys = f"{sort_map_keys[sort_field]} {sort_dir.upper()}, p.nm_id, p.vendor_code_norm"
    order_by_final = f"{sort_map_final[sort_field]} {sort_dir.upper()}, k.nm_id, k.vendor_code_norm"

    offset = (page - 1) * page_size

    qnum: Optional[int] = None
    qpat: Optional[str] = None
    if q:
        qpat = f"%{q.strip()}%"
        try:
            qnum = int(q.strip())
        except Exception:
            qnum = None

    # Backwards-compat aliases
    # - old "missing_wb_stock" was based on stock_snapshots => treat as missing_fbs_stock
    if missing_wb_stock and not missing_fbs_stock:
        missing_fbs_stock = True
    # - old "only_in_stock_wb" meant stock_snapshots qty > 0 => treat as has_fbs_stock
    if only_in_stock_wb and not has_fbs_stock:
        has_fbs_stock = True

    # Two-phase query:
    # 1) Build a small "keys" page (vendor_code_norm + nm_id) with LIMIT/OFFSET and filters.
    # 2) Join heavy tables ONLY for those keys.
    #
    # NOTE: This expects a stored/generated column products.vendor_code_norm with an index.
    sql = text(
        f"""
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
        wb_price_keys AS (
            SELECT ps.nm_id::bigint AS nm_id
            FROM price_snapshots ps
            WHERE ps.project_id = :project_id
            GROUP BY ps.nm_id
        ),
        front_keys AS (
            SELECT f.nm_id::bigint AS nm_id
            FROM frontend_catalog_price_snapshots f
            JOIN brand b ON b.brand_id IS NOT NULL
            JOIN front_run r ON f.snapshot_at = r.run_at
            WHERE f.query_type = 'brand'
              AND f.query_value = b.brand_id
            GROUP BY f.nm_id
        ),
        prod_nm_ids AS (
            SELECT DISTINCT p.nm_id::bigint AS nm_id
            FROM products p
            WHERE p.project_id = :project_id
        ),
        fbo_wh_latest AS (
            SELECT DISTINCT ON (s.nm_id, s.warehouse_name)
                s.nm_id::bigint AS nm_id,
                s.warehouse_name,
                s.quantity::bigint AS quantity,
                COALESCE(s.last_change_date, s.snapshot_at) AS updated_at
            FROM supplier_stock_snapshots s
            JOIN prod_nm_ids pn ON pn.nm_id = s.nm_id
            WHERE s.nm_id IS NOT NULL
            ORDER BY s.nm_id, s.warehouse_name, COALESCE(s.last_change_date, s.snapshot_at) DESC
        ),
        fbo_latest AS (
            SELECT
                nm_id,
                SUM(COALESCE(quantity, 0))::bigint AS fbo_stock_qty,
                MAX(updated_at) AS fbo_stock_updated_at
            FROM fbo_wh_latest
            GROUP BY nm_id
        ),
        stock_latest AS (
            SELECT ss.nm_id::bigint AS nm_id,
                   SUM(COALESCE(ss.quantity, 0))::bigint AS stock_wb
            FROM stock_snapshots ss
            JOIN stock_run r ON ss.snapshot_at = r.run_at
            WHERE ss.project_id = :project_id
            GROUP BY ss.nm_id
        ),
        rrp_latest AS (
            SELECT s.vendor_code_norm,
                   MAX(s.rrp_price) AS rrp_price,
                   MAX(s.rrp_stock) AS rrp_stock
            FROM rrp_snapshots s
            JOIN rrp_run r ON s.snapshot_at = r.run_at
            WHERE s.project_id = :project_id
            GROUP BY s.vendor_code_norm
        ),
        prod_base AS (
            SELECT
                p.nm_id::bigint AS nm_id,
                p.vendor_code AS vendor_code_raw,
                p.vendor_code_norm AS vendor_code_norm
            FROM products p
            WHERE p.project_id = :project_id
              AND p.vendor_code_norm IS NOT NULL
              AND (
                :qpat IS NULL
                OR p.vendor_code_norm ILIKE :qpat
                OR (:qnum IS NOT NULL AND p.nm_id = :qnum)
              )
        ),
        prod_filtered AS (
            SELECT
                p.vendor_code_raw,
                p.vendor_code_norm,
                p.nm_id,
                COALESCE(sl.stock_wb, 0)::bigint AS fbs_stock_qty,
                (COALESCE(sl.stock_wb, 0) > 0) AS has_fbs_stock,
                COALESCE(fl.fbo_stock_qty, 0)::bigint AS fbo_stock_qty,
                (COALESCE(fl.fbo_stock_qty, 0) > 0) AS has_fbo_stock,
                fl.fbo_stock_updated_at AS fbo_stock_updated_at,
                rl.rrp_price,
                rl.rrp_stock
            FROM prod_base p
            LEFT JOIN stock_latest sl ON sl.nm_id = p.nm_id
            LEFT JOIN fbo_latest fl ON fl.nm_id = p.nm_id
            LEFT JOIN rrp_latest rl ON rl.vendor_code_norm = p.vendor_code_norm
            LEFT JOIN wb_price_keys wpk ON wpk.nm_id = p.nm_id
            LEFT JOIN front_keys fpk ON fpk.nm_id = p.nm_id
            WHERE (:only_wb = FALSE OR COALESCE(sl.stock_wb, 0) > 0)
              AND (:only_1c = FALSE OR COALESCE(rl.rrp_stock, 0) > 0)
              AND (
                :any_missing = FALSE
                OR rl.vendor_code_norm IS NULL
                OR COALESCE(sl.stock_wb, 0) <= 0
                OR COALESCE(fl.fbo_stock_qty, 0) <= 0
                OR wpk.nm_id IS NULL
                OR fpk.nm_id IS NULL
              )
              AND (:missing_rrp = FALSE OR rl.vendor_code_norm IS NULL)
              AND (:missing_wb_price = FALSE OR wpk.nm_id IS NULL)
              AND (:missing_front = FALSE OR fpk.nm_id IS NULL)
              AND (:has_fbs_stock = FALSE OR COALESCE(sl.stock_wb, 0) > 0)
              AND (:missing_fbs_stock = FALSE OR COALESCE(sl.stock_wb, 0) <= 0)
              AND (:has_fbo_stock = FALSE OR COALESCE(fl.fbo_stock_qty, 0) > 0)
              AND (:missing_fbo_stock = FALSE OR COALESCE(fl.fbo_stock_qty, 0) <= 0)
              AND (
                :any_missing_stock = FALSE
                OR (COALESCE(sl.stock_wb, 0) <= 0 AND COALESCE(fl.fbo_stock_qty, 0) <= 0)
              )
        ),
        keys AS (
            SELECT
                p.vendor_code_raw,
                p.vendor_code_norm,
                p.nm_id,
                p.fbs_stock_qty,
                p.has_fbs_stock,
                p.fbo_stock_qty,
                p.has_fbo_stock,
                p.fbo_stock_updated_at,
                p.rrp_price,
                p.rrp_stock,
                COUNT(*) OVER() AS total_count
            FROM prod_filtered p
            ORDER BY {order_by_keys}
            LIMIT :limit OFFSET :offset
        ),
        wb_price AS (
            SELECT DISTINCT ON (ps.nm_id)
                ps.nm_id::bigint AS nm_id,
                ps.wb_price,
                ps.wb_discount,
                ps.created_at
            FROM price_snapshots ps
            JOIN keys k ON k.nm_id = ps.nm_id
            WHERE ps.project_id = :project_id
            ORDER BY ps.nm_id, ps.created_at DESC
        ),
        supplier_latest AS (
            SELECT DISTINCT ON (s.nm_id)
                s.nm_id::bigint AS nm_id,
                s.barcode,
                s.last_change_date
            FROM supplier_stock_snapshots s
            JOIN keys k ON k.nm_id = s.nm_id
            WHERE s.nm_id IS NOT NULL
            ORDER BY s.nm_id, s.last_change_date DESC NULLS LAST
        ),
        front AS (
            SELECT DISTINCT ON (f.nm_id)
                f.nm_id::bigint AS nm_id,
                f.price_product AS showcase_price,
                f.discount_calc_percent AS spp
            FROM frontend_catalog_price_snapshots f
            JOIN keys k ON k.nm_id = f.nm_id
            JOIN brand b ON b.brand_id IS NOT NULL
            JOIN front_run r ON f.snapshot_at = r.run_at
            WHERE f.query_type = 'brand'
              AND f.query_value = b.brand_id
            ORDER BY f.nm_id, f.snapshot_at DESC
        )
        SELECT
            k.vendor_code_norm AS "Артикул",
            k.nm_id AS "NMid",
            supplier_latest.barcode AS "ШК",
            k.rrp_price AS "Наша цена (РРЦ)",
            front.showcase_price AS "Цена на витрине",
            wb_price.wb_discount AS "Скидка наша",
            front.spp AS "СПП",
            k.fbs_stock_qty AS "Остаток WB", -- DEPRECATED alias for FBS
            k.rrp_stock AS "Остаток 1С",
            (SELECT run_at FROM stock_run) AS "Обновлено WB", -- DEPRECATED alias for FBS
            (SELECT run_at FROM rrp_run) AS "Обновлено 1С",
            (SELECT run_at FROM front_run) AS "Обновлено фронт",
            wb_price.created_at AS "Обновлено WB API",
            wb_price.wb_price AS "WB Price",
            k.fbs_stock_qty AS fbs_stock_qty,
            (SELECT run_at FROM stock_run) AS fbs_stock_updated_at,
            k.has_fbs_stock AS has_fbs_stock,
            k.fbo_stock_qty AS fbo_stock_qty,
            k.fbo_stock_updated_at AS fbo_stock_updated_at,
            k.has_fbo_stock AS has_fbo_stock,
            k.total_count AS total_count
        FROM keys k
        LEFT JOIN supplier_latest ON supplier_latest.nm_id = k.nm_id
        LEFT JOIN wb_price ON wb_price.nm_id = k.nm_id
        LEFT JOIN front ON front.nm_id = k.nm_id
        ORDER BY {order_by_final}
        """
    )

    params = {
        "project_id": project_id,
        "qpat": qpat,
        "qnum": qnum,
        "only_wb": only_in_stock_wb,
        "only_1c": only_in_stock_1c,
        "any_missing": any_missing,
        "missing_rrp": missing_rrp,
        "missing_wb_price": missing_wb_price,
        "missing_front": missing_front,
        "has_fbs_stock": has_fbs_stock,
        "missing_fbs_stock": missing_fbs_stock,
        "has_fbo_stock": has_fbo_stock,
        "missing_fbo_stock": missing_fbo_stock,
        "any_missing_stock": any_missing_stock,
        "limit": page_size,
        "offset": offset,
    }

    t0 = time.perf_counter()
    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    print(
        f"articles-base: project_id={project_id} page={page} page_size={page_size} "
        f"filters={{q:{bool(q)}, wb:{only_in_stock_wb}, 1c:{only_in_stock_1c}, "
        f"any_missing:{any_missing}, missing_rrp:{missing_rrp}, missing_wb_price:{missing_wb_price}, missing_front:{missing_front}, "
        f"has_fbs_stock:{has_fbs_stock}, missing_fbs_stock:{missing_fbs_stock}, "
        f"has_fbo_stock:{has_fbo_stock}, missing_fbo_stock:{missing_fbo_stock}, any_missing_stock:{any_missing_stock}}} "
        f"rows={len(rows)} elapsed_ms={elapsed_ms:.1f}"
    )

    total = int(rows[0]["total_count"]) if rows else 0
    items = []
    for r in rows:
        d = dict(r)
        d.pop("total_count", None)
        items.append(d)

    # Lightweight "data completeness" for current page (doesn't scan full dataset).
    with_wb_price = sum(1 for it in items if it.get("WB Price") is not None)
    with_front = sum(
        1
        for it in items
        if it.get("Цена на витрине") is not None or it.get("СПП") is not None
    )
    with_fbs_stock = sum(1 for it in items if bool(it.get("has_fbs_stock")))
    with_fbo_stock = sum(1 for it in items if bool(it.get("has_fbo_stock")))

    response = {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
        "completeness": {
            "page_items": len(items),
            "with_wb_price": with_wb_price,
            "with_front": with_front,
            "with_fbs_stock": with_fbs_stock,
            "with_fbo_stock": with_fbo_stock,
        },
    }
    if debug:
        response["elapsed_ms"] = round(elapsed_ms, 1)
    return response


@router.get("/{project_id}/articles-base/summary")
async def get_articles_base_summary(
    project_id: int = Path(..., description="Project ID"),
    ttl_s: int = Query(120, ge=60, le=300, description="Cache TTL seconds (60-300)"),
    force: int = Query(0, ge=0, le=1, description="Invalidate cache and recompute"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    cache_key = f"articles_base:summary:v1:project:{project_id}"
    if force:
        cache_delete(cache_key)
    cached = cache_get_json(cache_key)
    if cached:
        return cached

    sql = text(
        """
        WITH
        brand AS (
            SELECT pm.settings_json->>'brand_id' AS brand_id
            FROM project_marketplaces pm
            JOIN marketplaces m ON m.id = pm.marketplace_id
            WHERE pm.project_id = :project_id
              AND m.code = 'wildberries'
            LIMIT 1
        ),
        totals AS (
            SELECT
                COUNT(*)::bigint AS total_products,
                COUNT(DISTINCT vendor_code_norm)::bigint AS total_vendor_code_norm
            FROM products
            WHERE project_id = :project_id
              AND vendor_code_norm IS NOT NULL
        ),
        rrp_at AS (
            SELECT MAX(snapshot_at) AS rrp_at
            FROM rrp_snapshots
            WHERE project_id = :project_id
        ),
        wb_prices_at AS (
            SELECT MAX(created_at) AS wb_prices_at
            FROM price_snapshots
            WHERE project_id = :project_id
        ),
        wb_stocks_at AS (
            SELECT MAX(snapshot_at) AS fbs_stock_at
            FROM stock_snapshots
            WHERE project_id = :project_id
        ),
        fbo_stock_at AS (
            SELECT MAX(COALESCE(s.last_change_date, s.snapshot_at)) AS fbo_stock_at
            FROM supplier_stock_snapshots s
            JOIN products p
              ON p.project_id = :project_id
             AND p.nm_id = s.nm_id
        ),
        frontend_prices_at AS (
            SELECT MAX(f.snapshot_at) AS frontend_prices_at
            FROM frontend_catalog_price_snapshots f
            JOIN brand b ON b.brand_id IS NOT NULL
            WHERE f.query_type = 'brand'
              AND f.query_value = b.brand_id
        ),
        rrp_run AS (
            SELECT MAX(snapshot_at) AS run_at
            FROM rrp_snapshots
            WHERE project_id = :project_id
        ),
        rrp_latest AS (
            SELECT s.vendor_code_norm,
                   MAX(s.rrp_price) AS rrp_price,
                   MAX(s.rrp_stock) AS rrp_stock
            FROM rrp_snapshots s
            JOIN rrp_run r ON s.snapshot_at = r.run_at
            WHERE s.project_id = :project_id
            GROUP BY s.vendor_code_norm
        ),
        stock_run AS (
            SELECT MAX(snapshot_at) AS run_at
            FROM stock_snapshots
            WHERE project_id = :project_id
        ),
        stock_latest AS (
            SELECT ss.nm_id::bigint AS nm_id,
                   SUM(COALESCE(ss.quantity, 0))::bigint AS stock_wb
            FROM stock_snapshots ss
            JOIN stock_run r ON ss.snapshot_at = r.run_at
            WHERE ss.project_id = :project_id
            GROUP BY ss.nm_id
        ),
        prod_nm_ids AS (
            SELECT DISTINCT p.nm_id::bigint AS nm_id
            FROM products p
            WHERE p.project_id = :project_id
        ),
        fbo_wh_latest AS (
            SELECT DISTINCT ON (s.nm_id, s.warehouse_name)
                s.nm_id::bigint AS nm_id,
                s.warehouse_name,
                s.quantity::bigint AS quantity,
                COALESCE(s.last_change_date, s.snapshot_at) AS updated_at
            FROM supplier_stock_snapshots s
            JOIN prod_nm_ids pn ON pn.nm_id = s.nm_id
            WHERE s.nm_id IS NOT NULL
            ORDER BY s.nm_id, s.warehouse_name, COALESCE(s.last_change_date, s.snapshot_at) DESC
        ),
        fbo_latest AS (
            SELECT
                nm_id,
                SUM(COALESCE(quantity, 0))::bigint AS fbo_stock_qty
            FROM fbo_wh_latest
            GROUP BY nm_id
        ),
        wb_price_latest AS (
            SELECT DISTINCT ON (ps.nm_id)
                ps.nm_id::bigint AS nm_id,
                ps.wb_price,
                ps.created_at
            FROM price_snapshots ps
            WHERE ps.project_id = :project_id
            ORDER BY ps.nm_id, ps.created_at DESC
        ),
        front_run AS (
            SELECT MAX(f.snapshot_at) AS run_at
            FROM frontend_catalog_price_snapshots f
            JOIN brand b ON b.brand_id IS NOT NULL
            WHERE f.query_type = 'brand'
              AND f.query_value = b.brand_id
        ),
        front_latest AS (
            SELECT DISTINCT ON (f.nm_id)
                f.nm_id::bigint AS nm_id,
                f.price_product AS front_price
            FROM frontend_catalog_price_snapshots f
            JOIN brand b ON b.brand_id IS NOT NULL
            JOIN front_run r ON f.snapshot_at = r.run_at
            WHERE f.query_type = 'brand'
              AND f.query_value = b.brand_id
            ORDER BY f.nm_id, f.snapshot_at DESC
        ),
        prod_codes AS (
            SELECT DISTINCT vendor_code_norm
            FROM products
            WHERE project_id = :project_id
              AND vendor_code_norm IS NOT NULL
        ),
        prod_nm AS (
            SELECT DISTINCT nm_id::bigint AS nm_id
            FROM products
            WHERE project_id = :project_id
        ),
        counts AS (
            SELECT
              (SELECT COUNT(*) FROM prod_codes pc JOIN rrp_latest r ON r.vendor_code_norm = pc.vendor_code_norm AND r.rrp_price IS NOT NULL) AS with_rrp_price,
              (SELECT COUNT(*) FROM prod_codes pc JOIN rrp_latest r ON r.vendor_code_norm = pc.vendor_code_norm AND r.rrp_stock IS NOT NULL) AS with_rrp_stock,
              (SELECT COUNT(*) FROM prod_nm pn JOIN stock_latest s ON s.nm_id = pn.nm_id WHERE COALESCE(s.stock_wb, 0) > 0) AS with_fbs_stock,
              (SELECT COUNT(*) FROM prod_nm pn JOIN fbo_latest f ON f.nm_id = pn.nm_id WHERE COALESCE(f.fbo_stock_qty, 0) > 0) AS with_fbo_stock,
              (SELECT COUNT(*) FROM prod_nm pn JOIN wb_price_latest w ON w.nm_id = pn.nm_id AND w.wb_price IS NOT NULL) AS with_wb_price,
              (SELECT COUNT(*) FROM prod_nm pn JOIN front_latest f ON f.nm_id = pn.nm_id AND f.front_price IS NOT NULL) AS with_front_price
        )
        SELECT
          totals.total_products,
          totals.total_vendor_code_norm,
          counts.with_rrp_price,
          counts.with_rrp_stock,
          counts.with_fbs_stock,
          counts.with_fbo_stock,
          counts.with_wb_price,
          counts.with_front_price,
          wb_stocks_at.fbs_stock_at,
          fbo_stock_at.fbo_stock_at,
          wb_prices_at.wb_prices_at,
          frontend_prices_at.frontend_prices_at,
          rrp_at.rrp_at
        FROM totals, counts, wb_stocks_at, fbo_stock_at, wb_prices_at, frontend_prices_at, rrp_at;
        """
    )

    with engine.connect() as conn:
        row = conn.execute(sql, {"project_id": project_id}).mappings().first()
        if not row:
            payload = {"totals": {"total_products": 0, "total_vendor_code_norm": 0}}
            cache_set_json(cache_key, payload, ttl_s)
            return payload

        total_vendor_code_norm = int(row["total_vendor_code_norm"] or 0)

        def pct(x: int, denom: int) -> float:
            if denom <= 0:
                return 0.0
            return round((x / denom) * 100.0, 1)

        counts = {
            "with_rrp_price": int(row["with_rrp_price"] or 0),
            "with_rrp_stock": int(row["with_rrp_stock"] or 0),
            "with_fbs_stock": int(row["with_fbs_stock"] or 0),
            "with_fbo_stock": int(row["with_fbo_stock"] or 0),
            "with_wb_price": int(row["with_wb_price"] or 0),
            "with_front_price": int(row["with_front_price"] or 0),
            # deprecated aliases (do not use in new UI)
            "with_wb_stock": int(row["with_fbs_stock"] or 0),
            "with_supplier_stock": int(row["with_fbo_stock"] or 0),
        }

        payload = {
            "totals": {
                "total_products": int(row["total_products"] or 0),
                "total_vendor_code_norm": total_vendor_code_norm,
            },
            "counts": counts,
            "percents": {
                k: pct(v, total_vendor_code_norm if k.startswith("with_rrp") else int(row["total_products"] or 0))
                for k, v in counts.items()
            },
            "last_snapshots": {
                "fbs_stock_at": row["fbs_stock_at"].isoformat() if row["fbs_stock_at"] else None,
                "fbo_stock_at": row["fbo_stock_at"].isoformat() if row["fbo_stock_at"] else None,
                "wb_prices_at": row["wb_prices_at"].isoformat() if row["wb_prices_at"] else None,
                "frontend_prices_at": row["frontend_prices_at"].isoformat() if row["frontend_prices_at"] else None,
                "rrp_at": row["rrp_at"].isoformat() if row["rrp_at"] else None,
                # deprecated aliases (do not use in new UI)
                "wb_stocks_at": row["fbs_stock_at"].isoformat() if row["fbs_stock_at"] else None,
                "supplier_stocks_at": row["fbo_stock_at"].isoformat() if row["fbo_stock_at"] else None,
            },
        }

    cache_set_json(cache_key, payload, ttl_s)
    return payload


@router.get("/{project_id}/articles-base/coverage")
async def get_articles_base_coverage(
    project_id: int = Path(..., description="Project ID"),
    limit: int = Query(50, ge=1, le=200),
    ttl_s: int = Query(120, ge=60, le=300, description="Cache TTL seconds (60-300)"),
    force: int = Query(0, ge=0, le=1, description="Invalidate cache and recompute"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    cache_key = f"articles_base:coverage:v1:project:{project_id}:limit:{limit}"
    if force:
        cache_delete(cache_key)
    cached = cache_get_json(cache_key)
    if cached:
        return cached

    # CTE helpers for latest runs
    base_cte = """
    WITH
    rrp_run AS (
        SELECT MAX(snapshot_at) AS run_at
        FROM rrp_snapshots
        WHERE project_id = :project_id
    ),
    rrp_latest AS (
        SELECT s.vendor_code_norm,
               MAX(s.rrp_price) AS rrp_price,
               MAX(s.rrp_stock) AS rrp_stock
        FROM rrp_snapshots s
        JOIN rrp_run r ON s.snapshot_at = r.run_at
        WHERE s.project_id = :project_id
        GROUP BY s.vendor_code_norm
    ),
    stock_run AS (
        SELECT MAX(snapshot_at) AS run_at
        FROM stock_snapshots
        WHERE project_id = :project_id
    ),
    stock_latest AS (
        SELECT ss.nm_id::bigint AS nm_id,
               SUM(COALESCE(ss.quantity, 0))::bigint AS stock_wb
        FROM stock_snapshots ss
        JOIN stock_run r ON ss.snapshot_at = r.run_at
        WHERE ss.project_id = :project_id
        GROUP BY ss.nm_id
    ),
    wb_price_latest AS (
        SELECT DISTINCT ON (ps.nm_id)
            ps.nm_id::bigint AS nm_id
        FROM price_snapshots ps
        WHERE ps.project_id = :project_id
        ORDER BY ps.nm_id, ps.created_at DESC
    ),
    brand AS (
        SELECT pm.settings_json->>'brand_id' AS brand_id
        FROM project_marketplaces pm
        JOIN marketplaces m ON m.id = pm.marketplace_id
        WHERE pm.project_id = :project_id
          AND m.code = 'wildberries'
        LIMIT 1
    ),
    front_run AS (
        SELECT MAX(f.snapshot_at) AS run_at
        FROM frontend_catalog_price_snapshots f
        JOIN brand b ON b.brand_id IS NOT NULL
        WHERE f.query_type = 'brand'
          AND f.query_value = b.brand_id
    ),
    front_latest AS (
        SELECT DISTINCT ON (f.nm_id)
            f.nm_id::bigint AS nm_id
        FROM frontend_catalog_price_snapshots f
        JOIN brand b ON b.brand_id IS NOT NULL
        JOIN front_run r ON f.snapshot_at = r.run_at
        WHERE f.query_type = 'brand'
          AND f.query_value = b.brand_id
        ORDER BY f.nm_id, f.snapshot_at DESC
    )
    ,
    prod_nm_ids AS (
        SELECT DISTINCT p.nm_id::bigint AS nm_id
        FROM products p
        WHERE p.project_id = :project_id
    ),
    fbo_wh_latest AS (
        SELECT DISTINCT ON (s.nm_id, s.warehouse_name)
            s.nm_id::bigint AS nm_id,
            s.warehouse_name,
            s.quantity::bigint AS quantity,
            COALESCE(s.last_change_date, s.snapshot_at) AS updated_at
        FROM supplier_stock_snapshots s
        JOIN prod_nm_ids pn ON pn.nm_id = s.nm_id
        WHERE s.nm_id IS NOT NULL
        ORDER BY s.nm_id, s.warehouse_name, COALESCE(s.last_change_date, s.snapshot_at) DESC
    ),
    fbo_latest AS (
        SELECT
            nm_id,
            SUM(COALESCE(quantity, 0))::bigint AS fbo_stock_qty,
            MAX(updated_at) AS fbo_stock_updated_at
        FROM fbo_wh_latest
        GROUP BY nm_id
    )
    """

    params = {"project_id": project_id, "limit": limit}

    def q(sql_body: str):
        with engine.connect() as conn:
            rows = conn.execute(text(base_cte + sql_body), params).mappings().all()
        return [dict(r) for r in rows]

    def q_count(sql_body: str) -> int:
        with engine.connect() as conn:
            return int(conn.execute(text(base_cte + sql_body), params).scalar_one() or 0)

    payload = {
        "in_products_missing_rrp": {
            "total_count": q_count(
                """
                SELECT COUNT(*) FROM (
                  SELECT DISTINCT p.vendor_code_norm
                  FROM products p
                  WHERE p.project_id = :project_id AND p.vendor_code_norm IS NOT NULL
                  EXCEPT
                  SELECT r.vendor_code_norm FROM rrp_latest r
                ) t
                """
            ),
            "items": q(
                """
                SELECT
                  p.vendor_code_norm,
                  MIN(p.vendor_code) AS vendor_code_raw_sample,
                  MIN(p.nm_id)::bigint AS nm_id_sample
                FROM products p
                LEFT JOIN rrp_latest r ON r.vendor_code_norm = p.vendor_code_norm
                WHERE p.project_id = :project_id
                  AND p.vendor_code_norm IS NOT NULL
                  AND r.vendor_code_norm IS NULL
                GROUP BY p.vendor_code_norm
                ORDER BY p.vendor_code_norm
                LIMIT :limit
                """
            ),
        },
        "in_rrp_missing_products": {
            "total_count": q_count(
                """
                SELECT COUNT(*) FROM (
                  SELECT r.vendor_code_norm
                  FROM rrp_latest r
                  EXCEPT
                  SELECT DISTINCT p.vendor_code_norm
                  FROM products p
                  WHERE p.project_id = :project_id AND p.vendor_code_norm IS NOT NULL
                ) t
                """
            ),
            "items": q(
                """
                SELECT r.vendor_code_norm
                FROM rrp_latest r
                LEFT JOIN (
                  SELECT DISTINCT vendor_code_norm
                  FROM products
                  WHERE project_id = :project_id AND vendor_code_norm IS NOT NULL
                ) p ON p.vendor_code_norm = r.vendor_code_norm
                WHERE p.vendor_code_norm IS NULL
                ORDER BY r.vendor_code_norm
                LIMIT :limit
                """
            ),
        },
        "in_products_missing_fbs_stock": {
            "total_count": q_count(
                """
                SELECT COUNT(*) FROM (
                  SELECT DISTINCT p.nm_id::bigint AS nm_id
                  FROM products p
                  LEFT JOIN stock_latest s ON s.nm_id = p.nm_id
                  WHERE p.project_id = :project_id
                    AND COALESCE(s.stock_wb, 0) <= 0
                ) t
                """
            ),
            "items": q(
                """
                SELECT
                  p.nm_id::bigint AS nm_id,
                  MIN(p.vendor_code) AS vendor_code_raw_sample,
                  MIN(p.vendor_code_norm) AS vendor_code_norm
                FROM products p
                LEFT JOIN stock_latest s ON s.nm_id = p.nm_id
                WHERE p.project_id = :project_id
                  AND COALESCE(s.stock_wb, 0) <= 0
                GROUP BY p.nm_id
                ORDER BY nm_id
                LIMIT :limit
                """
            ),
        },
        "in_products_missing_fbo_stock": {
            "total_count": q_count(
                """
                SELECT COUNT(*) FROM (
                  SELECT DISTINCT p.nm_id::bigint AS nm_id
                  FROM products p
                  LEFT JOIN fbo_latest f ON f.nm_id = p.nm_id
                  WHERE p.project_id = :project_id
                    AND COALESCE(f.fbo_stock_qty, 0) <= 0
                ) t
                """
            ),
            "items": q(
                """
                SELECT
                  p.nm_id::bigint AS nm_id,
                  MIN(p.vendor_code) AS vendor_code_raw_sample,
                  MIN(p.vendor_code_norm) AS vendor_code_norm
                FROM products p
                LEFT JOIN fbo_latest f ON f.nm_id = p.nm_id
                WHERE p.project_id = :project_id
                  AND COALESCE(f.fbo_stock_qty, 0) <= 0
                GROUP BY p.nm_id
                ORDER BY nm_id
                LIMIT :limit
                """
            ),
        },
        "in_products_missing_wb_price": {
            "total_count": q_count(
                """
                SELECT COUNT(*) FROM (
                  SELECT DISTINCT p.nm_id::bigint AS nm_id
                  FROM products p
                  WHERE p.project_id = :project_id
                  EXCEPT
                  SELECT w.nm_id FROM wb_price_latest w
                ) t
                """
            ),
            "items": q(
                """
                SELECT
                  p.nm_id::bigint AS nm_id,
                  MIN(p.vendor_code) AS vendor_code_raw_sample,
                  MIN(p.vendor_code_norm) AS vendor_code_norm
                FROM products p
                LEFT JOIN wb_price_latest w ON w.nm_id = p.nm_id
                WHERE p.project_id = :project_id
                  AND w.nm_id IS NULL
                GROUP BY p.nm_id
                ORDER BY nm_id
                LIMIT :limit
                """
            ),
        },
        "in_products_missing_front": {
            "total_count": q_count(
                """
                SELECT COUNT(*) FROM (
                  SELECT DISTINCT p.nm_id::bigint AS nm_id
                  FROM products p
                  WHERE p.project_id = :project_id
                  EXCEPT
                  SELECT f.nm_id FROM front_latest f
                ) t
                """
            ),
            "items": q(
                """
                SELECT
                  p.nm_id::bigint AS nm_id,
                  MIN(p.vendor_code) AS vendor_code_raw_sample,
                  MIN(p.vendor_code_norm) AS vendor_code_norm
                FROM products p
                LEFT JOIN front_latest f ON f.nm_id = p.nm_id
                WHERE p.project_id = :project_id
                  AND f.nm_id IS NULL
                GROUP BY p.nm_id
                ORDER BY nm_id
                LIMIT :limit
                """
            ),
        },
        "duplicates_vendor_code_norm": {
            "total_count": q_count(
                """
                SELECT COUNT(*) FROM (
                  SELECT p.vendor_code_norm
                  FROM products p
                  WHERE p.project_id = :project_id AND p.vendor_code_norm IS NOT NULL
                  GROUP BY p.vendor_code_norm
                  HAVING COUNT(*) > 1
                ) t
                """
            ),
            "items": q(
                """
                SELECT
                  p.vendor_code_norm,
                  COUNT(*)::int AS cnt,
                  MIN(p.vendor_code) AS vendor_code_raw_sample,
                  (ARRAY_AGG(p.nm_id ORDER BY p.nm_id))[1:5] AS nm_ids_sample
                FROM products p
                WHERE p.project_id = :project_id
                  AND p.vendor_code_norm IS NOT NULL
                GROUP BY p.vendor_code_norm
                HAVING COUNT(*) > 1
                ORDER BY cnt DESC, p.vendor_code_norm
                LIMIT :limit
                """
            ),
        },
    }

    # Backwards-compat alias (old name used "wb_stock" for stock_snapshots => FBS)
    payload["in_products_missing_wb_stock"] = payload["in_products_missing_fbs_stock"]

    cache_set_json(cache_key, payload, ttl_s)
    return payload

