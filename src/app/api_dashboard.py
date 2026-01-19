"""Dashboard API endpoints for frontend."""

from fastapi import APIRouter, Query, Path, Depends
from sqlalchemy import text

from app.db import engine
from app.deps import get_current_active_user, get_project_membership

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/projects/{project_id}/metrics")
async def get_dashboard_metrics(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership)
):
    """Get dashboard metrics: counts and max dates for a specific project.
    
    Always returns 200 OK, even if some metrics fail.
    Each metric is wrapped in try/except to prevent one failure from breaking the entire endpoint.
    Requires project membership.
    """
    counts = {
        "products": 0,
        "warehouses": 0,
        "stock_snapshots": 0,
        "supplier_stock_snapshots": 0,
        "prices": 0,
        "frontend_prices": 0,
        "frontend_prices_rows": 0,
        "frontend_prices_uniq_nm": 0,
        "rrp_xml": 0,
    }
    max_dates = {
        "stock_snapshots": None,
        "supplier_stock_snapshots": None,
        "price_snapshots": None,
        "frontend_price_snapshots": None,
        "rrp_xml": None,
    }
    
    # Query each table separately to handle missing tables gracefully
    tables = [
        ("products", "products"),
        ("wb_warehouses", "warehouses"),
        ("stock_snapshots", "stock_snapshots"),
        ("supplier_stock_snapshots", "supplier_stock_snapshots"),
    ]
    
    with engine.connect() as conn:
        def _safe_execute(stmt, params=None):
            """Execute a statement and rollback on error to avoid 'InFailedSqlTransaction'."""
            try:
                if params is None:
                    return conn.execute(stmt)
                return conn.execute(stmt, params)
            except Exception:
                # psycopg2 aborts the current transaction on error; rollback so subsequent
                # metrics can still be computed.
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise

        # Get counts - each wrapped in try/except
        for table_name, count_key in tables:
            try:
                # Filter by project_id if column exists
                if table_name == "products":
                    sql = text(f"SELECT COUNT(*) AS cnt FROM {table_name} WHERE project_id = :project_id")
                    result = _safe_execute(sql, {"project_id": project_id}).mappings().all()
                elif table_name in ("stock_snapshots", "supplier_stock_snapshots"):
                    if table_name == "stock_snapshots":
                        sql = text("SELECT COUNT(*) AS cnt FROM stock_snapshots WHERE project_id = :project_id")
                        result = _safe_execute(sql, {"project_id": project_id}).mappings().all()
                    else:
                        # supplier_stock_snapshots doesn't have project_id
                        sql = text("""
                            SELECT COUNT(*) AS cnt
                            FROM supplier_stock_snapshots s
                            JOIN products p
                              ON p.project_id = :project_id
                             AND p.nm_id = s.nm_id
                        """)
                        result = _safe_execute(sql, {"project_id": project_id}).mappings().all()
                else:
                    sql = text(f"SELECT COUNT(*) AS cnt FROM {table_name}")
                    result = _safe_execute(sql).mappings().all()
                    
                if result:
                    counts[count_key] = result[0].get("cnt", 0)
            except Exception as e:
                print(f"WARNING: api_dashboard: failed to get count for {table_name}: {type(e).__name__}: {e}")
                # Keep default value 0
        
        # Get max dates - each wrapped in try/except
        try:
            sql = text("SELECT MAX(snapshot_at) AS max_date FROM stock_snapshots WHERE project_id = :project_id")
            result = _safe_execute(sql, {"project_id": project_id}).mappings().all()
            if result and result[0].get("max_date"):
                max_dates["stock_snapshots"] = result[0]["max_date"].isoformat()
        except Exception as e:
            print(f"WARNING: api_dashboard: failed to get max date for stock_snapshots: {type(e).__name__}: {e}")
            # Keep default value None
        
        try:
            # supplier_stock_snapshots doesn't always have project_id; derive by joining products (project_id,nm_id)
            sql = text("""
                SELECT MAX(COALESCE(s.last_change_date, s.snapshot_at)) AS max_date
                FROM supplier_stock_snapshots s
                JOIN products p
                  ON p.project_id = :project_id
                 AND p.nm_id = s.nm_id
            """)
            result = _safe_execute(sql, {"project_id": project_id}).mappings().all()
            if result and result[0].get("max_date"):
                max_dates["supplier_stock_snapshots"] = result[0]["max_date"].isoformat()
        except Exception as e:
            print(f"WARNING: api_dashboard: failed to get max date for supplier_stock_snapshots: {type(e).__name__}: {e}")
            # Keep default value None
        
        # Get prices count - check if table exists first, then use simple COUNT(DISTINCT)
        try:
            # First check if table exists
            check_sql = text("SELECT 1 FROM price_snapshots LIMIT 1")
            _safe_execute(check_sql).scalar_one_or_none()
            
            # Table exists, get count of distinct nm_id filtered by project_id
            sql = text("SELECT COUNT(DISTINCT nm_id) AS cnt FROM price_snapshots WHERE project_id = :project_id")
            result = _safe_execute(sql, {"project_id": project_id}).mappings().all()
            if result:
                counts["prices"] = result[0].get("cnt", 0)
        except Exception as e:
            print(f"WARNING: api_dashboard: failed to get prices count: {type(e).__name__}: {e}")
            # Keep default value 0
        
        # Get max price snapshot date - wrapped in try/except
        try:
            # Check if table exists first
            check_sql = text("SELECT 1 FROM price_snapshots LIMIT 1")
            _safe_execute(check_sql).scalar_one_or_none()
            
            # Table exists, get max date filtered by project_id
            sql = text("SELECT MAX(created_at) AS max_date FROM price_snapshots WHERE project_id = :project_id")
            result = _safe_execute(sql, {"project_id": project_id}).mappings().all()
            if result and result[0].get("max_date"):
                max_dates["price_snapshots"] = result[0]["max_date"].isoformat()
        except Exception as e:
            print(f"WARNING: api_dashboard: failed to get max date for price_snapshots: {type(e).__name__}: {e}")
            # Keep default value None
        
        # Get frontend prices counts - wrapped in try/except
        # Note: frontend_catalog_price_snapshots doesn't have project_id; derive by project brand_id (project_marketplaces.settings_json.brand_id)
        try:
            check_sql = text("SELECT 1 FROM frontend_catalog_price_snapshots LIMIT 1")
            _safe_execute(check_sql).scalar_one_or_none()

            # Get brand_id from project_marketplaces for wildberries
            brand_sql = text("""
                SELECT pm.settings_json->>'brand_id' AS brand_id
                FROM project_marketplaces pm
                JOIN marketplaces m ON m.id = pm.marketplace_id
                WHERE pm.project_id = :project_id
                  AND m.code = 'wildberries'
                LIMIT 1
            """)
            brand_row = _safe_execute(brand_sql, {"project_id": project_id}).mappings().first()
            brand_id = brand_row.get("brand_id") if brand_row else None

            if brand_id:
                sql = text("""
                    SELECT COUNT(*) AS cnt, COUNT(DISTINCT nm_id) AS uniq
                    FROM frontend_catalog_price_snapshots
                    WHERE query_type = 'brand' AND query_value = :brand_id
                """)
                row = _safe_execute(sql, {"brand_id": str(brand_id)}).mappings().first()
                if row:
                    counts["frontend_prices"] = row.get("cnt", 0)
                    counts["frontend_prices_rows"] = row.get("cnt", 0)
                    counts["frontend_prices_uniq_nm"] = row.get("uniq", 0)
            else:
                # Can't attribute to a project without brand_id
                pass
        except Exception as e:
            print(f"WARNING: api_dashboard: failed to get frontend_prices counts: {type(e).__name__}: {e}")
            # Keep default values 0
        
        # Get max frontend price snapshot date - wrapped in try/except
        try:
            check_sql = text("SELECT 1 FROM frontend_catalog_price_snapshots LIMIT 1")
            _safe_execute(check_sql).scalar_one_or_none()

            brand_sql = text("""
                SELECT pm.settings_json->>'brand_id' AS brand_id
                FROM project_marketplaces pm
                JOIN marketplaces m ON m.id = pm.marketplace_id
                WHERE pm.project_id = :project_id
                  AND m.code = 'wildberries'
                LIMIT 1
            """)
            brand_row = _safe_execute(brand_sql, {"project_id": project_id}).mappings().first()
            brand_id = brand_row.get("brand_id") if brand_row else None

            if brand_id:
                sql = text("""
                    SELECT MAX(snapshot_at) AS max_date
                    FROM frontend_catalog_price_snapshots
                    WHERE query_type = 'brand' AND query_value = :brand_id
                """)
                result = _safe_execute(sql, {"brand_id": str(brand_id)}).mappings().all()
            else:
                result = []
                
            if result and result[0].get("max_date"):
                max_dates["frontend_price_snapshots"] = result[0]["max_date"].isoformat()
        except Exception as e:
            print(f"WARNING: api_dashboard: failed to get max date for frontend_price_snapshots: {type(e).__name__}: {e}")
            # Keep default value None

        # RRP XML metrics (project-scoped table rrp_prices)
        try:
            check_sql = text("SELECT 1 FROM rrp_prices LIMIT 1")
            _safe_execute(check_sql).scalar_one_or_none()

            sql = text("SELECT COUNT(*) AS cnt FROM rrp_prices WHERE project_id = :project_id")
            row = _safe_execute(sql, {"project_id": project_id}).mappings().first()
            if row:
                counts["rrp_xml"] = row.get("cnt", 0)
        except Exception as e:
            print(f"WARNING: api_dashboard: failed to get rrp_xml count: {type(e).__name__}: {e}")

        try:
            check_sql = text("SELECT 1 FROM rrp_prices LIMIT 1")
            _safe_execute(check_sql).scalar_one_or_none()

            sql = text("SELECT MAX(updated_at) AS max_date FROM rrp_prices WHERE project_id = :project_id")
            row = _safe_execute(sql, {"project_id": project_id}).mappings().first()
            if row and row.get("max_date"):
                max_dates["rrp_xml"] = row["max_date"].isoformat()
        except Exception as e:
            print(f"WARNING: api_dashboard: failed to get rrp_xml max date: {type(e).__name__}: {e}")
    
    return {
        "counts": counts,
        "max_dates": max_dates,
    }


@router.get("/projects/{project_id}/kpis")
async def get_dashboard_kpis(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Project dashboard KPIs (business meaning).

    Definitions:
    - FBS stock: WB merchant availability (stock_snapshots, latest snapshot_at run)
    - FBO stock: WB warehouses (supplier_stock_snapshots, latest per nm_id+warehouse then summed)
    - WB prices: price_snapshots, latest created_at run
    - Storefront: frontend_catalog_price_snapshots for project brand_id, latest snapshot_at run
    - RRP XML: rrp_snapshots, latest snapshot_at run
    """
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
        wb_products AS (
            SELECT COUNT(*)::bigint AS total
            FROM products
            WHERE project_id = :project_id
        ),
        wb_warehouses AS (
            SELECT COUNT(*)::bigint AS total
            FROM wb_warehouses
        ),
        fbs_run AS (
            SELECT MAX(snapshot_at) AS run_at
            FROM stock_snapshots
            WHERE project_id = :project_id
        ),
        fbs_latest AS (
            SELECT ss.nm_id::bigint AS nm_id,
                   SUM(COALESCE(ss.quantity, 0))::bigint AS qty
            FROM stock_snapshots ss
            JOIN fbs_run r ON ss.snapshot_at = r.run_at
            WHERE ss.project_id = :project_id
            GROUP BY ss.nm_id
        ),
        fbs_in_stock AS (
            SELECT COUNT(*)::bigint AS cnt
            FROM fbs_latest
            WHERE qty > 0
        ),
        prod_nm_ids AS (
            SELECT DISTINCT p.nm_id::bigint AS nm_id
            FROM products p
            WHERE p.project_id = :project_id
        ),
        fbo_run AS (
            SELECT MAX(COALESCE(s.last_change_date, s.snapshot_at)) AS run_at
            FROM supplier_stock_snapshots s
            JOIN products p
              ON p.project_id = :project_id
             AND p.nm_id = s.nm_id
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
                SUM(COALESCE(quantity, 0))::bigint AS qty,
                MAX(updated_at) AS updated_at
            FROM fbo_wh_latest
            GROUP BY nm_id
        ),
        fbo_in_stock AS (
            SELECT COUNT(*)::bigint AS cnt
            FROM fbo_latest
            WHERE qty > 0
        ),
        wb_price_run AS (
            SELECT MAX(created_at) AS run_at
            FROM price_snapshots
            WHERE project_id = :project_id
        ),
        wb_prices_latest AS (
            SELECT COUNT(DISTINCT ps.nm_id)::bigint AS cnt
            FROM price_snapshots ps
            JOIN wb_price_run r ON ps.created_at = r.run_at
            WHERE ps.project_id = :project_id
        ),
        storefront_run AS (
            SELECT MAX(f.snapshot_at) AS run_at
            FROM frontend_catalog_price_snapshots f
            JOIN brand b ON b.brand_id IS NOT NULL
            WHERE f.query_type = 'brand'
              AND f.query_value = b.brand_id
        ),
        storefront_latest AS (
            SELECT COUNT(DISTINCT f.nm_id)::bigint AS cnt
            FROM frontend_catalog_price_snapshots f
            JOIN brand b ON b.brand_id IS NOT NULL
            JOIN storefront_run r ON f.snapshot_at = r.run_at
            WHERE f.query_type = 'brand'
              AND f.query_value = b.brand_id
        ),
        expected_storefront AS (
            SELECT COUNT(DISTINCT nm_id)::bigint AS cnt
            FROM (
              SELECT nm_id FROM fbs_latest WHERE qty > 0
              UNION
              SELECT nm_id FROM fbo_latest WHERE qty > 0
            ) u
        ),
        rrp_run AS (
            SELECT MAX(snapshot_at) AS run_at
            FROM rrp_snapshots
            WHERE project_id = :project_id
        ),
        rrp_kpi AS (
            SELECT
              COUNT(DISTINCT s.vendor_code_norm)::bigint AS total,
              COUNT(DISTINCT CASE WHEN s.rrp_price IS NOT NULL THEN s.vendor_code_norm END)::bigint AS with_price,
              COUNT(DISTINCT CASE WHEN COALESCE(s.rrp_stock, 0) > 0 THEN s.vendor_code_norm END)::bigint AS with_stock,
              COUNT(DISTINCT CASE WHEN s.rrp_price IS NOT NULL AND COALESCE(s.rrp_stock, 0) > 0 THEN s.vendor_code_norm END)::bigint AS with_price_and_stock
            FROM rrp_snapshots s
            JOIN rrp_run r ON s.snapshot_at = r.run_at
            WHERE s.project_id = :project_id
        )
        SELECT
          (SELECT total FROM wb_products) AS wb_products_total,
          (SELECT total FROM wb_warehouses) AS wb_warehouses_total,
          (SELECT run_at FROM fbs_run) AS fbs_stock_at,
          (SELECT cnt FROM fbs_in_stock) AS fbs_in_stock,
          (SELECT run_at FROM fbo_run) AS fbo_stock_at,
          (SELECT cnt FROM fbo_in_stock) AS fbo_in_stock,
          (SELECT run_at FROM wb_price_run) AS wb_prices_at,
          (SELECT cnt FROM wb_prices_latest) AS wb_prices_products,
          (SELECT run_at FROM storefront_run) AS storefront_at,
          (SELECT cnt FROM storefront_latest) AS storefront_products,
          (SELECT cnt FROM expected_storefront) AS expected_storefront_products,
          (SELECT run_at FROM rrp_run) AS rrp_at,
          (SELECT total FROM rrp_kpi) AS rrp_total,
          (SELECT with_price FROM rrp_kpi) AS rrp_with_price,
          (SELECT with_stock FROM rrp_kpi) AS rrp_with_stock,
          (SELECT with_price_and_stock FROM rrp_kpi) AS rrp_with_price_and_stock
        ;
        """
    )

    with engine.connect() as conn:
        row = conn.execute(sql, {"project_id": project_id}).mappings().first() or {}

    def iso(v):
        return v.isoformat() if v is not None and hasattr(v, "isoformat") else None

    wb_products_total = int(row.get("wb_products_total") or 0)
    return {
        "wb": {
            "products_total": wb_products_total,
            "warehouses_fbs_total": int(row.get("wb_warehouses_total") or 0),
        },
        "stock": {
            "fbs_in_stock_products": int(row.get("fbs_in_stock") or 0),
            "fbo_in_stock_products": int(row.get("fbo_in_stock") or 0),
        },
        "prices": {
            "wb_prices_products": min(int(row.get("wb_prices_products") or 0), wb_products_total),
        },
        "storefront": {
            "storefront_products": int(row.get("storefront_products") or 0),
            "expected_storefront_products": int(row.get("expected_storefront_products") or 0),
        },
        "rrp_xml": {
            "total": int(row.get("rrp_total") or 0),
            "with_price": int(row.get("rrp_with_price") or 0),
            "with_stock": int(row.get("rrp_with_stock") or 0),
            "with_price_and_stock": int(row.get("rrp_with_price_and_stock") or 0),
        },
        "last_snapshots": {
            "fbs_stock_at": iso(row.get("fbs_stock_at")),
            "fbo_stock_at": iso(row.get("fbo_stock_at")),
            "wb_prices_at": iso(row.get("wb_prices_at")),
            "storefront_at": iso(row.get("storefront_at")),
            "rrp_at": iso(row.get("rrp_at")),
        },
    }

