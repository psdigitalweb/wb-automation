"""Project-scoped Wildberries stock without photos endpoint.

This module exposes:
- GET /api/v1/projects/{project_id}/wildberries/stock-without-photos

Returns products that:
- Have FBW (FBO) stock on WB warehouses (stock > min_stock)
- Have no photos in products.pics (photos_count == 0 or pics IS NULL)

Uses only database (supplier_stock_snapshots for FBW, no WB API calls).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import text

from app.db import engine
from app.deps import get_current_active_user, get_project_membership

router = APIRouter(prefix="/api/v1/projects", tags=["wb-stock-without-photos"])


@router.get("/{project_id}/wildberries/stock-without-photos")
async def get_stock_without_photos(
    project_id: int = Path(..., description="Project ID"),
    search: Optional[str] = Query(None, description="Search by our_sku (vendor_code) or nmId"),
    min_stock: int = Query(1, ge=0, description="Minimum stock quantity (default: 1)"),
    warehouse_id: Optional[int] = Query(None, description="Filter by warehouse ID (maps to warehouse name)"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Get products with FBW stock on WB warehouses but without photos.

    Returns products that:
    - Have FBW (FBO) stock >= min_stock on WB warehouses (from supplier_stock_snapshots)
    - Have no photos in products.pics (pics IS NULL OR jsonb_array_length(pics) = 0)
    - Exist in products table for this project

    Note: Only includes products that exist in products table (ingested cards).
    Products not in DB are excluded (cannot determine if they have photos).
    Only FBW stocks are considered (FBS stocks are excluded).
    Uses only database - no WB API calls.
    """
    # Build search clause
    search_clause = ""
    params: Dict[str, Any] = {
        "project_id": project_id,
        "min_stock": min_stock,
    }

    if search:
        search = search.strip()
        params["search_pat"] = f"%{search}%"
        try:
            search_num = int(search)
            params["search_num"] = search_num
        except ValueError:
            params["search_num"] = None
        search_clause = """
            AND (
                (:search_pat IS NOT NULL AND (
                    p.vendor_code ILIKE :search_pat
                    OR (p.vendor_code_norm IS NOT NULL AND p.vendor_code_norm ILIKE :search_pat)
                ))
                OR (:search_num IS NOT NULL AND p.nm_id = :search_num)
            )
        """
    else:
        params["search_pat"] = None
        params["search_num"] = None

    # Warehouse filter: map warehouse_id to warehouse_name
    warehouse_filter = ""
    if warehouse_id:
        params["warehouse_id"] = warehouse_id
        warehouse_filter = """
            AND EXISTS (
                SELECT 1 FROM wb_warehouses ww
                WHERE ww.wb_id = :warehouse_id
                  AND ww.name = s.warehouse_name
            )
        """

    # Single optimized SQL query:
    # 1. Get latest FBW stocks per (nm_id, warehouse_name) from supplier_stock_snapshots
    # 2. Join with products to filter by project_id and photos
    # 3. Aggregate by nm_id with json_agg for warehouses
    # 4. Filter by min_stock
    sql = text(
        f"""
        WITH
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
              AND s.quantity > 0
              {warehouse_filter}
            ORDER BY s.nm_id, s.warehouse_name, COALESCE(s.last_change_date, s.snapshot_at) DESC
        ),
        fbo_aggregated AS (
            SELECT
                nm_id,
                SUM(COALESCE(quantity, 0))::bigint AS total_qty,
                json_agg(
                    json_build_object(
                        'warehouse_name', warehouse_name,
                        'qty', quantity
                    )
                    ORDER BY quantity DESC
                ) AS by_warehouse
            FROM fbo_wh_latest
            GROUP BY nm_id
            HAVING SUM(COALESCE(quantity, 0)) >= :min_stock
        )
        SELECT
            p.nm_id,
            p.vendor_code AS our_sku,
            p.vendor_code_norm AS our_sku_norm,
            (
                SELECT ps.rrc
                FROM price_snapshots ps
                WHERE ps.nm_id = p.nm_id
                  AND ps.project_id = :project_id
                ORDER BY ps.created_at DESC
                LIMIT 1
            ) AS rrc,
            fa.total_qty AS wb_stock_total,
            fa.by_warehouse AS wb_stock_by_warehouse
        FROM products p
        INNER JOIN fbo_aggregated fa ON fa.nm_id = p.nm_id
        WHERE p.project_id = :project_id
          AND (
            p.pics IS NULL
            OR jsonb_array_length(COALESCE(p.pics, '[]'::jsonb)) = 0
          )
          {search_clause}
        ORDER BY fa.total_qty DESC, p.nm_id
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()

    # Build response
    items = []
    for row in rows:
        # Parse JSON array for warehouses
        by_warehouse_raw = row.get("wb_stock_by_warehouse")
        by_warehouse: List[Dict[str, Any]] = []
        if by_warehouse_raw:
            if isinstance(by_warehouse_raw, list):
                by_warehouse = by_warehouse_raw
            elif isinstance(by_warehouse_raw, str):
                import json
                try:
                    by_warehouse = json.loads(by_warehouse_raw)
                except (json.JSONDecodeError, TypeError):
                    by_warehouse = []

        items.append({
            "nm_id": int(row["nm_id"]),
            "our_sku": row.get("our_sku_norm") or row.get("our_sku"),
            "rrc": float(row["rrc"]) if row.get("rrc") is not None else None,
            "wb_stock_total": int(row["wb_stock_total"]),
            "wb_stock_by_warehouse": by_warehouse,
        })

    # Get meta counts (separate optimized query for counts only)
    meta_sql = text(
        f"""
        WITH
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
              AND s.quantity > 0
              {warehouse_filter}
            ORDER BY s.nm_id, s.warehouse_name, COALESCE(s.last_change_date, s.snapshot_at) DESC
        ),
        fbo_aggregated AS (
            SELECT
                nm_id,
                SUM(COALESCE(quantity, 0))::bigint AS total_qty
            FROM fbo_wh_latest
            GROUP BY nm_id
            HAVING SUM(COALESCE(quantity, 0)) >= :min_stock
        ),
        products_with_stock AS (
            SELECT p.nm_id::bigint AS nm_id
            FROM products p
            INNER JOIN fbo_aggregated fa ON fa.nm_id = p.nm_id
            WHERE p.project_id = :project_id
              {search_clause}
        ),
        products_without_photos AS (
            SELECT p.nm_id::bigint AS nm_id
            FROM products p
            INNER JOIN fbo_aggregated fa ON fa.nm_id = p.nm_id
            WHERE p.project_id = :project_id
              AND (
                p.pics IS NULL
                OR jsonb_array_length(COALESCE(p.pics, '[]'::jsonb)) = 0
              )
              {search_clause}
        )
        SELECT
            (SELECT COUNT(*) FROM fbo_aggregated) AS total_in_stocks,
            (SELECT COUNT(*) FROM products_with_stock) AS total_candidates_after_filters,
            (SELECT COUNT(*) FROM products_without_photos) AS total_without_photos
        """
    )

    with engine.connect() as conn:
        meta_row = conn.execute(meta_sql, params).mappings().fetchone()

    meta = {
        "total_in_stocks": int(meta_row["total_in_stocks"]) if meta_row else 0,
        "total_candidates_after_filters": int(meta_row["total_candidates_after_filters"]) if meta_row else 0,
        "total_without_photos": int(meta_row["total_without_photos"]) if meta_row else 0,
    }

    return {
        "items": items,
        "meta": meta,
    }
