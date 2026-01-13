"""API endpoints for product prices and latest price information."""

from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db import engine

router = APIRouter(prefix="/api/v1", tags=["prices"])


def _serialize_decimal(value: Any) -> Optional[float]:
    """Convert Decimal to float for JSON serialization."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value) if value is not None else None


def _serialize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize a database row to JSON-serializable dict."""
    result = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            result[key] = float(value)
        elif hasattr(value, "isoformat"):  # datetime objects
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


@router.get("/prices/latest")
async def get_latest_prices(
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
):
    """Get latest prices for all products with pagination.
    
    Returns the most recent price snapshot for each product (nm_id),
    sorted by created_at DESC (most recent first), then by nm_id.
    Uses CTE to get latest prices if VIEW doesn't exist.
    """
    try:
        # Try to use VIEW first (if it exists)
        query = text("""
            SELECT 
                nm_id,
                wb_price,
                wb_discount,
                spp,
                customer_price,
                rrc,
                price_at AS snapshot_at
            FROM v_products_latest_price
            ORDER BY price_at DESC, nm_id
            LIMIT :limit OFFSET :offset
        """)
        
        with engine.connect() as conn:
            result = conn.execute(query, {"limit": limit, "offset": offset})
            rows = [dict(row._mapping) for row in result]
        
        # Get total count from VIEW
        count_query = text("SELECT COUNT(*) AS cnt FROM v_products_latest_price")
        with engine.connect() as conn:
            count_result = conn.execute(count_query).scalar_one()
        
        return {
            "data": [_serialize_row(row) for row in rows],
            "limit": limit,
            "offset": offset,
            "count": len(rows),
            "total": count_result if count_result else len(rows)
        }
    except Exception:
        # Fallback to CTE if VIEW doesn't exist
        query = text("""
            WITH latest AS (
                SELECT DISTINCT ON (nm_id)
                    nm_id,
                    wb_price,
                    wb_discount,
                    spp,
                    customer_price,
                    rrc,
                    created_at AS snapshot_at
                FROM price_snapshots
                ORDER BY nm_id, created_at DESC
            )
            SELECT * FROM latest
            ORDER BY snapshot_at DESC, nm_id
            LIMIT :limit OFFSET :offset
        """)
        
        count_query = text("""
            WITH latest AS (
                SELECT DISTINCT ON (nm_id)
                    nm_id
                FROM price_snapshots
                ORDER BY nm_id, created_at DESC
            )
            SELECT COUNT(*) AS cnt FROM latest
        """)
        
        try:
            with engine.connect() as conn:
                result = conn.execute(query, {"limit": limit, "offset": offset})
                rows = [dict(row._mapping) for row in result]
                
                count_result = conn.execute(count_query).scalar_one()
            
            return {
                "data": [_serialize_row(row) for row in rows],
                "limit": limit,
                "offset": offset,
                "count": len(rows),
                "total": count_result if count_result else len(rows)
            }
        except Exception as e:
            print(f"get_latest_prices: error: {e}")
            return {
                "data": [],
                "limit": limit,
                "offset": offset,
                "count": 0,
                "total": 0,
                "error": "Table not found or error occurred"
            }


@router.get("/products/with-latest-price")
async def get_products_with_latest_price(
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
):
    """Get products with their latest price information.
    
    Returns products joined with their latest price snapshot,
    sorted by products.nm_id in ascending order.
    """
    query = text("""
        SELECT 
            p.nm_id,
            p.vendor_code,
            p.title,
            p.brand,
            p.subject_name,
            p.updated_at,
            lp.wb_price,
            lp.wb_discount,
            lp.spp,
            lp.customer_price,
            lp.rrc,
            lp.price_at
        FROM products p
        LEFT JOIN v_products_latest_price lp ON p.nm_id = lp.nm_id
        ORDER BY p.nm_id
        LIMIT :limit OFFSET :offset
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query, {"limit": limit, "offset": offset})
        rows = [dict(row._mapping) for row in result]
    
    return {
        "items": [_serialize_row(row) for row in rows],
        "limit": limit,
        "offset": offset,
        "count": len(rows)
    }


@router.get("/products/with-latest-price-and-stock")
async def get_products_with_price_and_stock(
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
):
    """Get products with their latest price and stock information.
    
    Returns products joined with their latest price snapshot and latest stock,
    sorted by products.nm_id in ascending order.
    """
    query = text("""
        SELECT 
            p.nm_id,
            p.vendor_code,
            p.title,
            p.brand,
            p.subject_name,
            p.updated_at,
            lp.wb_price,
            lp.customer_price,
            lp.price_at,
            ls.total_quantity,
            ls.stock_at
        FROM products p
        LEFT JOIN v_products_latest_price lp ON p.nm_id = lp.nm_id
        LEFT JOIN v_products_latest_stock ls ON p.nm_id = ls.nm_id
        ORDER BY p.nm_id
        LIMIT :limit OFFSET :offset
    """)
    
    with engine.connect() as conn:
        result = conn.execute(query, {"limit": limit, "offset": offset})
        rows = [dict(row._mapping) for row in result]
    
    return {
        "items": [_serialize_row(row) for row in rows],
        "limit": limit,
        "offset": offset,
        "count": len(rows)
    }

