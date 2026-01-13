"""Dashboard API endpoints for frontend."""

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.db import engine

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/metrics")
async def get_dashboard_metrics():
    """Get dashboard metrics: counts and max dates.
    
    Always returns 200 OK, even if some metrics fail.
    Each metric is wrapped in try/except to prevent one failure from breaking the entire endpoint.
    """
    counts = {
        "products": 0,
        "warehouses": 0,
        "stock_snapshots": 0,
        "supplier_stock_snapshots": 0,
        "prices": 0,
    }
    max_dates = {
        "stock_snapshots": None,
        "supplier_stock_snapshots": None,
        "price_snapshots": None,
    }
    
    # Query each table separately to handle missing tables gracefully
    tables = [
        ("products", "products"),
        ("wb_warehouses", "warehouses"),
        ("stock_snapshots", "stock_snapshots"),
        ("supplier_stock_snapshots", "supplier_stock_snapshots"),
    ]
    
    with engine.connect() as conn:
        # Get counts - each wrapped in try/except
        for table_name, count_key in tables:
            try:
                sql = text(f"SELECT COUNT(*) AS cnt FROM {table_name}")
                result = conn.execute(sql).mappings().all()
                if result:
                    counts[count_key] = result[0].get("cnt", 0)
            except Exception as e:
                print(f"WARNING: api_dashboard: failed to get count for {table_name}: {type(e).__name__}: {e}")
                # Keep default value 0
        
        # Get max dates - each wrapped in try/except
        try:
            sql = text("SELECT MAX(snapshot_at) AS max_date FROM stock_snapshots")
            result = conn.execute(sql).mappings().all()
            if result and result[0].get("max_date"):
                max_dates["stock_snapshots"] = result[0]["max_date"].isoformat()
        except Exception as e:
            print(f"WARNING: api_dashboard: failed to get max date for stock_snapshots: {type(e).__name__}: {e}")
            # Keep default value None
        
        try:
            sql = text("SELECT MAX(last_change_date) AS max_date FROM supplier_stock_snapshots")
            result = conn.execute(sql).mappings().all()
            if result and result[0].get("max_date"):
                max_dates["supplier_stock_snapshots"] = result[0]["max_date"].isoformat()
        except Exception as e:
            print(f"WARNING: api_dashboard: failed to get max date for supplier_stock_snapshots: {type(e).__name__}: {e}")
            # Keep default value None
        
        # Get prices count - check if table exists first, then use simple COUNT(DISTINCT)
        try:
            # First check if table exists
            check_sql = text("SELECT 1 FROM price_snapshots LIMIT 1")
            conn.execute(check_sql).scalar_one_or_none()
            
            # Table exists, get count of distinct nm_id
            sql = text("SELECT COUNT(DISTINCT nm_id) AS cnt FROM price_snapshots")
            result = conn.execute(sql).mappings().all()
            if result:
                counts["prices"] = result[0].get("cnt", 0)
        except Exception as e:
            print(f"WARNING: api_dashboard: failed to get prices count: {type(e).__name__}: {e}")
            # Keep default value 0
        
        # Get max price snapshot date - wrapped in try/except
        try:
            # Check if table exists first
            check_sql = text("SELECT 1 FROM price_snapshots LIMIT 1")
            conn.execute(check_sql).scalar_one_or_none()
            
            # Table exists, get max date
            sql = text("SELECT MAX(created_at) AS max_date FROM price_snapshots")
            result = conn.execute(sql).mappings().all()
            if result and result[0].get("max_date"):
                max_dates["price_snapshots"] = result[0]["max_date"].isoformat()
        except Exception as e:
            print(f"WARNING: api_dashboard: failed to get max date for price_snapshots: {type(e).__name__}: {e}")
            # Keep default value None
    
    return {
        "counts": counts,
        "max_dates": max_dates,
    }

