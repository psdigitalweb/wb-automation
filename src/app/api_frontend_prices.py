"""API endpoints for frontend catalog prices."""

# region agent log
import json as _json
import time as _time

_DEBUG_LOG_PATH = r"d:\Work\EcomCore\.cursor\debug.log"


def _dbg(*, hypothesisId: str, location: str, message: str, data: dict) -> None:
    try:
        payload = {
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": hypothesisId,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(_time.time() * 1000),
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(_json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


# endregion

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import text

from app.db import engine
from app.deps import get_current_active_user, get_project_membership
from app.ingest_frontend_prices import resolve_base_url

router = APIRouter(prefix="/api/v1", tags=["frontend-prices"])


def _serialize_row(row: dict) -> dict:
    """Serialize row for JSON response (handle Decimal, datetime, etc.)."""
    result = {}
    for key, value in row.items():
        if value is None:
            result[key] = None
        elif isinstance(value, bool):
            result[key] = value
        elif isinstance(value, int):
            # Keep ints as ints (important for percent fields)
            result[key] = value
        elif hasattr(value, 'isoformat'):  # datetime
            result[key] = value.isoformat()
        elif hasattr(value, '__float__'):  # Decimal
            result[key] = float(value)
        else:
            result[key] = value
    return result


def _run_at_iso(run_row: dict) -> str | None:
    """Pick a stable timestamp for UI/meta (prefer run_at if exists, else created_at).

    NOTE: For as-of joins we also use run_at/created_at only (per requirements).
    """
    if not run_row:
        return None
    dt = run_row.get("run_at") or run_row.get("created_at")
    return dt.isoformat() if dt is not None and hasattr(dt, "isoformat") else None


@router.get("/projects/{project_id}/frontend-prices/resolved-url")
async def get_frontend_prices_resolved_url(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Return the resolved base URL for frontend prices (template with {brand_id} replaced).
    Use this to verify that the URL points to the correct brand before running ingest.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT pm.settings_json->>'brand_id' AS brand_id,
                       pm.settings_json->'frontend_prices'->>'base_url_template' AS base_url_template
                FROM project_marketplaces pm
                JOIN marketplaces m ON m.id = pm.marketplace_id
                WHERE pm.project_id = :project_id AND m.code = 'wildberries'
                LIMIT 1
            """),
            {"project_id": project_id},
        ).mappings().first()
        brand_id_str = (row or {}).get("brand_id")
        base_url_template = (row or {}).get("base_url_template")
        if not base_url_template or not str(base_url_template).strip():
            base_url_template = conn.execute(
                text("SELECT value->>'url' AS url FROM app_settings WHERE key = 'frontend_prices.brand_base_url'")
            ).scalar_one_or_none()
    if not brand_id_str:
        raise HTTPException(
            status_code=400,
            detail="brand_id not configured for this project (Wildberries marketplace settings).",
        )
    try:
        brand_id = int(brand_id_str)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid brand_id in project settings.")
    if not base_url_template or not str(base_url_template).strip():
        raise HTTPException(
            status_code=400,
            detail="base_url_template not configured (project or app_settings). Add frontend_prices.base_url_template with {brand_id}.",
        )
    try:
        resolved_url = resolve_base_url(str(base_url_template).strip(), brand_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "project_id": project_id,
        "brand_id": brand_id,
        "base_url_template": str(base_url_template).strip(),
        "resolved_url": resolved_url,
    }


@router.get("/projects/{project_id}/frontend-prices")
async def get_project_frontend_prices(
    project_id: int = Path(..., description="Project ID"),
    run_id: int | None = Query(None, description="Ingest run id to show (defaults to latest)"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Project-scoped report for WB frontend prices.

    - Finds last run for (project, marketplace_code='wildberries', job_code='frontend_prices', brand_id)
    - Returns count for last run and rows for selected run (default: last)
    """
    _dbg(
        hypothesisId="H2",
        location="api_frontend_prices.py:get_project_frontend_prices:entry",
        message="handler entry",
        data={"project_id": project_id, "requested_run_id": run_id, "limit": limit, "offset": offset},
    )

    with engine.connect() as conn:
        # region agent log
        try:
            total_runs_any = conn.execute(
                text(
                    """
                    SELECT COUNT(*)::bigint
                    FROM ingest_runs
                    WHERE project_id = :project_id
                      AND marketplace_code = 'wildberries'
                      AND job_code = 'frontend_prices'
                    """
                ),
                {"project_id": project_id},
            ).scalar()
            _dbg(
                hypothesisId="H4",
                location="api_frontend_prices.py:get_project_frontend_prices:run_inventory",
                message="ingest_runs inventory (unfiltered)",
                data={"project_id": project_id, "runs_any_count": int(total_runs_any or 0)},
            )
        except Exception:
            pass
        # endregion

        pm_row = conn.execute(
            text(
                """
                SELECT pm.settings_json AS settings_json
                FROM project_marketplaces pm
                JOIN marketplaces m ON m.id = pm.marketplace_id
                WHERE pm.project_id = :project_id
                  AND m.code = 'wildberries'
                LIMIT 1
                """
            ),
            {"project_id": project_id},
        ).mappings().first()
        settings = (pm_row or {}).get("settings_json") or {}
        if isinstance(settings, str):
            import json as _json_mod
            try:
                settings = _json_mod.loads(settings)
            except Exception:
                settings = {}
        if not isinstance(settings, dict):
            settings = {}
        brand_ids_set: set[str] = set()
        legacy_brand = settings.get("brand_id")
        if legacy_brand is not None:
            brand_ids_set.add(str(legacy_brand))
        fp = settings.get("frontend_prices")
        if isinstance(fp, dict) and isinstance(fp.get("brands"), list):
            for b in fp["brands"]:
                if isinstance(b, dict) and b.get("brand_id") is not None:
                    brand_ids_set.add(str(b["brand_id"]))
        brand_ids_list = sorted(brand_ids_set) if brand_ids_set else []

        # If no brand_ids configured, return empty result but keep contract stable.
        if not brand_ids_list:
            _dbg(
                hypothesisId="H2",
                location="api_frontend_prices.py:get_project_frontend_prices:brand_id_missing",
                message="brand_id missing in project marketplace settings",
                data={"project_id": project_id},
            )
            return {
                "meta": {
                    "brand_id": None,
                    "last_run_id": None,
                    "last_run_at": None,
                    "count_last_run": 0,
                    "selected_run_id": None,
                    "selected_run_at": None,
                    "runs": [],
                },
                "data": [],
                "limit": limit,
                "offset": offset,
                "count": 0,
                "total": 0,
            }

        # Last runs for dropdown + to pick default run.
        # We only list runs that actually have rows linked via ingest_run_id (so counts/\"last update\" are meaningful).
        # Match: legacy single-brand (stats_json.brand_id) OR multi-brand (succeeded_brands[].brand_id).
        runs_sql = text(
            """
            SELECT
              r.id,
              r.status,
              r.created_at,
              s.rows_count
            FROM ingest_runs r
            JOIN (
              SELECT ingest_run_id, COUNT(*)::bigint AS rows_count
              FROM frontend_catalog_price_snapshots
              WHERE ingest_run_id IS NOT NULL
              GROUP BY ingest_run_id
            ) s ON s.ingest_run_id = r.id
            WHERE r.project_id = :project_id
              AND r.marketplace_code = 'wildberries'
              AND r.job_code = 'frontend_prices'
              AND (
                r.stats_json->>'brand_id' = ANY(:brand_ids)
                OR r.params_json->>'brand_id' = ANY(:brand_ids)
                OR EXISTS (
                  SELECT 1 FROM jsonb_array_elements(COALESCE(r.stats_json->'succeeded_brands', '[]'::jsonb)) AS elem
                  WHERE elem->>'brand_id' = ANY(:brand_ids)
                )
              )
            ORDER BY r.created_at DESC
            LIMIT 50
            """
        )
        runs_raw = conn.execute(
            runs_sql, {"project_id": project_id, "brand_ids": brand_ids_list}
        ).mappings().all()
        runs = [dict(r) for r in runs_raw]

        last_run = runs[0] if runs else None
        last_run_id = int(last_run["id"]) if last_run else None
        last_run_at = _run_at_iso(last_run) if last_run else None

        selected_run_id = int(run_id) if run_id is not None else last_run_id
        selected_run = None
        if selected_run_id is not None:
            selected_run = next((r for r in runs if int(r["id"]) == int(selected_run_id)), None)
            if selected_run is None:
                # Avoid leaking other projects' runs.
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="ingest run not found for this project/job/brand",
                )

        # Count for last run (metric above table)
        count_last_run = int(last_run.get("rows_count") or 0) if last_run else 0

        # as-of timestamp: prefer ingest_runs.run_at if the column exists, else created_at.
        # Per requirements: do NOT use started_at/finished_at for as-of joins.
        as_of_at = None
        if selected_run_id is not None:
            # Avoid probing non-existent columns (would abort txn on Postgres).
            has_run_at = False
            try:
                has_run_at = (
                    conn.execute(
                        text(
                            """
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_name = 'ingest_runs'
                              AND column_name = 'run_at'
                            LIMIT 1
                            """
                        )
                    ).scalar_one_or_none()
                    is not None
                )
            except Exception:
                has_run_at = False

            if has_run_at:
                as_of_row = conn.execute(
                    text(
                        """
                        SELECT id, run_at, created_at
                        FROM ingest_runs
                        WHERE id = :id
                        """
                    ),
                    {"id": selected_run_id},
                ).mappings().first()
                if as_of_row:
                    as_of_at = as_of_row.get("run_at") or as_of_row.get("created_at")
            else:
                as_of_row = conn.execute(
                    text(
                        """
                        SELECT id, created_at
                        FROM ingest_runs
                        WHERE id = :id
                        """
                    ),
                    {"id": selected_run_id},
                ).mappings().first()
                if as_of_row:
                    as_of_at = as_of_row.get("created_at")

        # region agent log
        try:
            base_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*)::bigint
                    FROM frontend_catalog_price_snapshots
                    WHERE ingest_run_id = :run_id
                    """
                ),
                {"run_id": selected_run_id},
            ).scalar()
            _dbg(
                hypothesisId="H4",
                location="api_frontend_prices.py:get_project_frontend_prices:base_count",
                message="base rows count by ingest_run_id",
                data={
                    "project_id": project_id,
                    "selected_run_id": selected_run_id,
                    "as_of_at": as_of_at.isoformat() if hasattr(as_of_at, "isoformat") else None,
                    "meta_runs_len": len(runs),
                    "base_count": int(base_count or 0),
                },
            )
        except Exception:
            pass
        # endregion

        _dbg(
            hypothesisId="H3",
            location="api_frontend_prices.py:get_project_frontend_prices:after_runs_query",
            message="runs selected",
            data={
                "project_id": project_id,
                "requested_run_id": run_id,
                "last_run_id": last_run_id,
                "runs_len": len(runs),
                "count_last_run": count_last_run,
                "as_of_at": as_of_at.isoformat() if hasattr(as_of_at, "isoformat") else None,
            },
        )

        # Data for selected run
        rows: list[dict] = []
        total_items = 0
        if selected_run_id is not None:
            total_items = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM frontend_catalog_price_snapshots
                        WHERE ingest_run_id = :run_id
                        """
                    ),
                    {"run_id": selected_run_id},
                ).scalar()
                or 0
            )
            # Join enrichment:
            # f (selected run) -> price_snapshots (as-of) -> products -> rrp_prices
            query_sql = text(
                """
                WITH
                f_page AS (
                    SELECT
                        id,
                        snapshot_at,
                        source,
                        query_type,
                        query_value,
                        page,
                        nm_id,
                        vendor_code,
                        name,
                        price_basic,
                        price_product,
                        sale_percent,
                        discount_calc_percent
                    FROM frontend_catalog_price_snapshots
                    WHERE ingest_run_id = :run_id
                    ORDER BY nm_id
                    LIMIT :limit OFFSET :offset
                ),
                wb_price_latest AS (
                    SELECT DISTINCT ON (ps.nm_id)
                        ps.nm_id::bigint AS nm_id,
                        ps.wb_price,
                        ps.wb_discount,
                        ps.customer_price
                    FROM price_snapshots ps
                    WHERE ps.project_id = :project_id
                      AND ps.created_at <= :as_of_at
                    ORDER BY ps.nm_id, ps.created_at DESC
                )
                SELECT
                    f_page.*,
                    rrp.rrp_price AS rrp_price,
                    wb.wb_price AS wb_price,
                    wb.wb_discount AS wb_discount,
                    f_page.price_product AS final_price,
                    CASE
                        WHEN wb.customer_price IS NULL OR wb.customer_price <= 0 OR f_page.price_product IS NULL
                            THEN NULL
                        ELSE CAST(ROUND((1 - (f_page.price_product / wb.customer_price)) * 100) AS INTEGER)
                    END AS spp_percent,
                    CASE
                        WHEN rrp.rrp_price IS NULL OR rrp.rrp_price <= 0 OR f_page.price_product IS NULL
                            THEN NULL
                        ELSE CAST(ROUND((1 - (f_page.price_product / rrp.rrp_price)) * 100) AS INTEGER)
                    END AS total_discount_percent
                FROM f_page
                LEFT JOIN wb_price_latest wb
                  ON wb.nm_id = f_page.nm_id
                LEFT JOIN products p
                  ON p.project_id = :project_id
                 AND p.nm_id = f_page.nm_id
                LEFT JOIN rrp_prices rrp
                  ON rrp.project_id = :project_id
                 AND rrp.sku = p.vendor_code_norm
                ORDER BY f_page.nm_id
                """
            )
            if as_of_at is None:
                # No as-of → can't join to price_snapshots meaningfully; still return f rows.
                query_sql = text(
                    """
                    SELECT
                        id,
                        snapshot_at,
                        source,
                        query_type,
                        query_value,
                        page,
                        nm_id,
                        vendor_code,
                        name,
                        price_basic,
                        price_product,
                        sale_percent,
                        discount_calc_percent,
                        NULL::numeric AS rrp_price,
                        NULL::numeric AS wb_price,
                        NULL::numeric AS wb_discount,
                        price_product AS final_price,
                        NULL::int AS spp_percent,
                        NULL::int AS total_discount_percent
                    FROM frontend_catalog_price_snapshots
                    WHERE ingest_run_id = :run_id
                    ORDER BY nm_id
                    LIMIT :limit OFFSET :offset
                    """
                )
                rows_raw = conn.execute(
                    query_sql, {"run_id": selected_run_id, "limit": limit, "offset": offset}
                ).mappings().all()
            else:
                rows_raw = conn.execute(
                    query_sql,
                    {
                        "run_id": selected_run_id,
                        "project_id": project_id,
                        "as_of_at": as_of_at,
                        "limit": limit,
                        "offset": offset,
                    },
                ).mappings().all()

            rows = [dict(r) for r in rows_raw]

        # region agent log
        try:
            _dbg(
                hypothesisId="H4",
                location="api_frontend_prices.py:get_project_frontend_prices:response_counts",
                message="response counts",
                data={
                    "project_id": project_id,
                    "selected_run_id": selected_run_id,
                    "meta_runs_len": len(runs),
                    "total_items": int(total_items or 0),
                    "returned_rows_count": int(len(rows)),
                },
            )
        except Exception:
            pass
        # endregion

        return {
            "meta": {
                "brand_id": brand_ids_list[0] if brand_ids_list else None,
                "last_run_id": last_run_id,
                "last_run_at": last_run_at,
                "count_last_run": count_last_run,
                "selected_run_id": selected_run_id,
                "selected_run_at": as_of_at.isoformat() if hasattr(as_of_at, "isoformat") else None,
                "runs": [_serialize_row(r) for r in runs],
            },
            "data": [_serialize_row(row) for row in rows],
            "limit": limit,
            "offset": offset,
            "count": len(rows),
            "total": total_items,
        }


@router.get("/frontend-prices/latest")
async def get_latest_frontend_prices(
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
):
    """Get latest frontend catalog price snapshots with pagination.
    
    Returns the most recent snapshots, sorted by snapshot_at in descending order.
    """
    query_sql = text("""
        SELECT 
            id,
            snapshot_at,
            source,
            query_type,
            query_value,
            page,
            nm_id,
            vendor_code,
            name,
            price_basic,
            price_product,
            sale_percent,
            discount_calc_percent
        FROM frontend_catalog_price_snapshots
        ORDER BY snapshot_at DESC, nm_id
        LIMIT :limit OFFSET :offset
    """)
    
    total_count_sql = text("SELECT COUNT(*) FROM frontend_catalog_price_snapshots")
    
    try:
        with engine.connect() as conn:
            total_result = conn.execute(total_count_sql).scalar()
            total_items = total_result if total_result is not None else 0
            
            result = conn.execute(query_sql, {"limit": limit, "offset": offset}).mappings().all()
            rows = [dict(row) for row in result]
    except Exception as e:
        print(f"get_latest_frontend_prices: error: {e}")
        total_items = 0
        rows = []
    
    return {
        "data": [_serialize_row(row) for row in rows],
        "limit": limit,
        "offset": offset,
        "count": len(rows),
        "total": total_items
    }


@router.get("/frontend-prices/latest/by-nm")
async def get_latest_frontend_prices_by_nm(
    nm_id: int = Query(..., description="Product nm_id"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of records to return"),
):
    """Get latest frontend catalog price snapshots for a specific nm_id.
    
    Returns the most recent snapshots for the given product, sorted by snapshot_at in descending order.
    """
    query_sql = text("""
        SELECT 
            id,
            snapshot_at,
            source,
            query_type,
            query_value,
            page,
            nm_id,
            vendor_code,
            name,
            price_basic,
            price_product,
            sale_percent,
            discount_calc_percent
        FROM frontend_catalog_price_snapshots
        WHERE nm_id = :nm_id
        ORDER BY snapshot_at DESC
        LIMIT :limit
    """)
    
    try:
        with engine.connect() as conn:
            result = conn.execute(query_sql, {"nm_id": nm_id, "limit": limit}).mappings().all()
            rows = [dict(row) for row in result]
    except Exception as e:
        print(f"get_latest_frontend_prices_by_nm: error: {e}")
        rows = []
    
    return {
        "data": [_serialize_row(row) for row in rows],
        "nm_id": nm_id,
        "count": len(rows)
    }

