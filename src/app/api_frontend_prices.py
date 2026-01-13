"""API endpoints for frontend catalog prices."""

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.db import engine

router = APIRouter(prefix="/api/v1", tags=["frontend-prices"])


def _serialize_row(row: dict) -> dict:
    """Serialize row for JSON response (handle Decimal, datetime, etc.)."""
    result = {}
    for key, value in row.items():
        if value is None:
            result[key] = None
        elif hasattr(value, 'isoformat'):  # datetime
            result[key] = value.isoformat()
        elif hasattr(value, '__float__'):  # Decimal
            result[key] = float(value)
        else:
            result[key] = value
    return result


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

