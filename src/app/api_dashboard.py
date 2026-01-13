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
    }
    max_dates = {
        "stock_snapshots": None,
        "supplier_stock_snapshots": None,
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
    
    return {
        "counts": counts,
        "max_dates": max_dates,
    }

