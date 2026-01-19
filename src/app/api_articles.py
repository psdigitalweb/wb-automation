"""API endpoints for unified article base showcase."""

from fastapi import APIRouter, Query
from sqlalchemy import text

from app.db import engine

router = APIRouter(prefix="/api/v1/articles", tags=["articles"])


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


@router.get("/base")
async def get_article_base(
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of records to return"),
    offset: int = Query(0, ge=0, description="Number of records to skip"),
    search: str = Query(None, description="Search by vendor_code_norm (ILIKE) or nm_id"),
    sort_by: str = Query("NMid", description="Column to sort by"),
    sort_order: str = Query("asc", description="Sort order: asc or desc"),
    only_with_wb_stock: bool = Query(False, description="Filter only items with WB stock > 0"),
    only_with_our_stock: bool = Query(False, description="Filter only items with our stock (1C) > 0"),
):
    """Get unified article base showcase with prices and stocks.
    
    Returns data from v_article_base VIEW with pagination and optional search.
    Search filters by vendor_code_norm (ILIKE %search%) or nm_id::text (ILIKE %search%).
    
    Columns:
    - Артикул (vendor_code_norm): Normalized vendor code
    - NMid (nm_id): WB product ID
    - ШК (barcode): Barcode
    - Наша цена (РРЦ) (rrp_price): RRP price from 1C XML
    - Цена на витрине (wb_showcase_price): Price from frontend catalog
    - Скидка наша (wb_our_discount): Our discount from WB API
    - СПП (wb_spp_discount): Co-invest discount from WB frontend
    - Остаток WB (supplier_qty_total): Stock on WB warehouses
    - Остаток 1С (rrp_stock): Stock from 1C XML
    """
    # Build WHERE clause for search and filters
    where_conditions = []
    params = {"limit": limit, "offset": offset}
    
    if search:
        where_conditions.append("""
            ("Артикул" ILIKE :search_pattern 
             OR "NMid"::text ILIKE :search_pattern)
        """)
        params["search_pattern"] = f"%{search}%"
    
    if only_with_wb_stock:
        where_conditions.append('"Остаток WB" > 0')
    
    if only_with_our_stock:
        where_conditions.append('"Остаток 1С" > 0')
    
    where_clause = ""
    if where_conditions:
        where_clause = "WHERE " + " AND ".join(where_conditions)
    
    # Validate and sanitize sort_by
    allowed_columns = [
        "Артикул", "NMid", "ШК", "Наша цена (РРЦ)", "Цена на витрине",
        "Скидка наша", "СПП", "Остаток WB", "Остаток 1С",
        "Обновлено WB", "Обновлено 1С", "Обновлено фронт", "Обновлено WB API"
    ]
    if sort_by not in allowed_columns:
        sort_by = "NMid"
    
    # Validate sort_order
    sort_order = sort_order.lower()
    if sort_order not in ["asc", "desc"]:
        sort_order = "asc"
    
    query_sql = text(f"""
        SELECT 
            "Артикул",
            "NMid",
            "ШК",
            "Наша цена (РРЦ)",
            "Цена на витрине",
            "Скидка наша",
            "СПП",
            "Остаток WB",
            "Остаток 1С",
            "Обновлено WB",
            "Обновлено 1С",
            "Обновлено фронт",
            "Обновлено WB API"
        FROM v_article_base
        {where_clause}
        ORDER BY "{sort_by}" {sort_order.upper()}, "NMid", "Артикул"
        LIMIT :limit OFFSET :offset
    """)
    
    count_sql = text(f"""
        SELECT COUNT(*) 
        FROM v_article_base
        {where_clause}
    """)
    
    try:
        with engine.connect() as conn:
            # Get total count
            total_result = conn.execute(count_sql, params).scalar()
            total_items = total_result if total_result is not None else 0
            
            # Get paginated data
            result = conn.execute(query_sql, params).mappings().all()
            rows = [dict(row) for row in result]
    except Exception as e:
        print(f"get_article_base: error: {e}")
        total_items = 0
        rows = []
    
    return {
        "data": [_serialize_row(row) for row in rows],
        "limit": limit,
        "offset": offset,
        "count": len(rows),
        "total": total_items
    }



