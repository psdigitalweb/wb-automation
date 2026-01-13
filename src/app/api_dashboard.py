"""Dashboard API endpoints for frontend."""

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.db import engine

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/metrics")
async def get_dashboard_metrics():
    """Get dashboard metrics: counts and max dates."""
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
        ("products", "products_count"),
        ("wb_warehouses", "warehouses_count"),
        ("stock_snapshots", "stock_snapshots_count"),
        ("supplier_stock_snapshots", "supplier_stock_snapshots_count"),
    ]
    
    with engine.connect() as conn:
        for table_name, count_key in tables:
            try:
                sql = text(f"SELECT COUNT(*) AS cnt FROM {table_name}")
                result = conn.execute(sql).mappings().all()
                if result:
                    counts[count_key.replace("_count", "")] = result[0].get("cnt", 0)
            except Exception as e:
                print(f"api_dashboard: table {table_name} not found or error: {e}")
                # Continue with other tables
        
        # Get max dates
        try:
            sql = text("SELECT MAX(snapshot_at) AS max_date FROM stock_snapshots")
            result = conn.execute(sql).mappings().all()
            if result and result[0].get("max_date"):
                max_dates["stock_snapshots"] = result[0]["max_date"].isoformat()
        except Exception:
            pass
        
        try:
            sql = text("SELECT MAX(last_change_date) AS max_date FROM supplier_stock_snapshots")
            result = conn.execute(sql).mappings().all()
            if result and result[0].get("max_date"):
                max_dates["supplier_stock_snapshots"] = result[0]["max_date"].isoformat()
        except Exception:
            pass
        
        # Get prices count (unique nm_id with latest prices)
        try:
            # Try VIEW first
            sql = text("SELECT COUNT(*) AS cnt FROM v_products_latest_price")
            result = conn.execute(sql).mappings().all()
            if result:
                counts["prices"] = result[0].get("cnt", 0)
        except Exception:
            # Fallback to CTE
            try:
                sql = text("""
                    WITH latest AS (
                        SELECT DISTINCT ON (nm_id) nm_id
                        FROM price_snapshots
                        ORDER BY nm_id, created_at DESC
                    )
                    SELECT COUNT(*) AS cnt FROM latest
                """)
                result = conn.execute(sql).mappings().all()
                if result:
                    counts["prices"] = result[0].get("cnt", 0)
            except Exception:
                pass
        
        # Get max price snapshot date
        try:
            sql = text("SELECT MAX(created_at) AS max_date FROM price_snapshots")
            result = conn.execute(sql).mappings().all()
            if result and result[0].get("max_date"):
                max_dates["price_snapshots"] = result[0]["max_date"].isoformat()
        except Exception:
            pass
    
    return {
        "counts": counts,
        "max_dates": max_dates,
    }

