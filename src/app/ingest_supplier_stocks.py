"""Ingestion endpoints for WB Statistics API supplier stock balances."""

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Query
from sqlalchemy import text

from app.db import engine
from app.wb.client import WBClient

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])
# Отдельный роутер для витринных эндпоинтов по supplier stocks
supplier_stocks_router = APIRouter(prefix="/api/v1", tags=["supplier-stocks"])


def _serialize_json_field(value: Any) -> Optional[str]:
    """Convert Python objects to JSON strings for JSONB fields."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _parse_rfc3339_to_datetime(date_str: str) -> datetime:
    """Parse RFC3339 date string to datetime object.
    
    Handles formats like:
    - "2019-06-20T00:00:00Z"
    - "2019-06-20T00:00:00+03:00"
    """
    # Try parsing with timezone
    for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%SZ"]:
        try:
            if fmt.endswith("Z"):
                # Replace Z with +00:00 for parsing
                date_str_z = date_str.replace("Z", "+00:00")
                return datetime.strptime(date_str_z, fmt.replace("Z", "%z"))
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    # Fallback: try without timezone
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"]:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    raise ValueError(f"Unable to parse RFC3339 date: {date_str}")


async def ingest_supplier_stocks() -> None:
    """Fetch and insert supplier stock snapshots from WB Statistics API.
    
    Алгоритм:
    1. Определить начальный dateFrom:
       - Если в БД есть записи: MAX(last_change_date)
       - Иначе: из WB_STOCKS_DATE_FROM_DEFAULT или "2019-06-20T00:00:00Z"
    2. Цикл пагинации:
       - Вызвать fetch_supplier_stocks(dateFrom)
       - Если [] -> завершить
       - Сохранить все строки в supplier_stock_snapshots
       - Взять lastChangeDate последней строки как следующий dateFrom
       - Sleep 60 секунд (rate limit: 1 req/min)
    3. Обработка ошибок:
       - 429: backoff 60-90 секунд и повторить
       - 5xx: retry с exponential backoff
    """
    token = os.getenv("WB_TOKEN", "") or ""
    if not token or token.upper() == "MOCK":
        print("ingest_supplier_stocks: skipped (MOCK mode or no token)")
        return
    
    # 1. Определить начальный dateFrom
    default_date_from = os.getenv("WB_STOCKS_DATE_FROM_DEFAULT", "2019-06-20T00:00:00Z")
    
    # Проверить, есть ли уже данные в БД
    max_date_sql = text("""
        SELECT MAX(last_change_date) AS max_date
        FROM supplier_stock_snapshots
    """)
    
    with engine.connect() as conn:
        result = conn.execute(max_date_sql).mappings().all()
        max_date = result[0]["max_date"] if result and result[0].get("max_date") else None
    
    if max_date:
        # Использовать последнюю дату + 1 секунда для инкрементальной загрузки
        # Преобразуем datetime в RFC3339
        date_from = max_date.strftime("%Y-%m-%dT%H:%M:%S%z")
        if not date_from.endswith("Z") and "+" not in date_from and "-" not in date_from[-6:]:
            # Add timezone if missing
            date_from = date_from + "+00:00"
        print(f"ingest_supplier_stocks: incremental mode, starting from {date_from} (last max_date: {max_date})")
    else:
        date_from = default_date_from
        print(f"ingest_supplier_stocks: full mode, starting from {date_from}")
    
    client = WBClient()
    
    insert_sql = text("""
        INSERT INTO supplier_stock_snapshots (
            snapshot_at, last_change_date, warehouse_name, nm_id,
            supplier_article, barcode, tech_size, quantity, quantity_full,
            in_way_to_client, in_way_from_client, is_supply, is_realization,
            price, discount, raw
        )
        VALUES (
            now(), :last_change_date, :warehouse_name, :nm_id,
            :supplier_article, :barcode, :tech_size, :quantity, :quantity_full,
            :in_way_to_client, :in_way_from_client, :is_supply, :is_realization,
            :price, :discount, :raw
        )
        ON CONFLICT (last_change_date, nm_id, barcode, warehouse_name) DO NOTHING
    """)
    
    total_pages = 0
    total_inserted = 0
    rate_limit_delay = 60  # 1 request per minute
    
    # 2. Цикл пагинации
    while True:
        print(f"ingest_supplier_stocks: fetching page {total_pages + 1}, dateFrom={date_from}")
        
        stocks = await client.fetch_supplier_stocks(date_from)
        
        if not stocks or len(stocks) == 0:
            print("ingest_supplier_stocks: empty response, pagination complete")
            break
        
        print(f"ingest_supplier_stocks: received {len(stocks)} records for page {total_pages + 1}")
        total_pages += 1
        
        # Сохранить записи
        rows: List[Dict[str, Any]] = []
        last_change_date_str = None
        
        for stock in stocks:
            # Извлечь lastChangeDate для следующей итерации
            last_change_date_str = stock.get("lastChangeDate") or stock.get("last_change_date")
            
            # Парсим lastChangeDate в datetime для БД
            try:
                last_change_date_dt = _parse_rfc3339_to_datetime(last_change_date_str) if last_change_date_str else None
            except Exception as e:
                print(f"ingest_supplier_stocks: error parsing lastChangeDate '{last_change_date_str}': {e}")
                continue
            
            # Извлекаем поля из ответа WB
            nm_id = stock.get("nmId") or stock.get("nm_id") or stock.get("nmID")
            warehouse_name = stock.get("warehouseName") or stock.get("warehouse_name")
            supplier_article = stock.get("supplierArticle") or stock.get("supplier_article")
            barcode = stock.get("barcode")
            tech_size = stock.get("techSize") or stock.get("tech_size")
            quantity = stock.get("quantity") or stock.get("Quantity") or 0
            quantity_full = stock.get("quantityFull") or stock.get("quantity_full")
            in_way_to_client = stock.get("inWayToClient") or stock.get("in_way_to_client")
            in_way_from_client = stock.get("inWayFromClient") or stock.get("in_way_from_client")
            is_supply = stock.get("isSupply") or stock.get("is_supply")
            is_realization = stock.get("isRealization") or stock.get("is_realization")
            price = stock.get("Price") or stock.get("price")
            discount = stock.get("Discount") or stock.get("discount")
            
            if not nm_id:
                print(f"ingest_supplier_stocks: skipping stock without nm_id: {stock}")
                continue
            
            rows.append({
                "last_change_date": last_change_date_dt,
                "warehouse_name": warehouse_name,
                "nm_id": int(nm_id),
                "supplier_article": supplier_article,
                "barcode": barcode,
                "tech_size": tech_size,
                "quantity": int(quantity),
                "quantity_full": int(quantity_full) if quantity_full is not None else None,
                "in_way_to_client": int(in_way_to_client) if in_way_to_client is not None else None,
                "in_way_from_client": int(in_way_from_client) if in_way_from_client is not None else None,
                "is_supply": bool(is_supply) if is_supply is not None else None,
                "is_realization": bool(is_realization) if is_realization is not None else None,
                "price": float(price) if price is not None else None,
                "discount": int(discount) if discount is not None else None,
                "raw": _serialize_json_field(stock),
            })
        
        if rows:
            with engine.begin() as conn:
                result = conn.execute(insert_sql, rows)
                inserted = len(rows)  # ON CONFLICT DO NOTHING, so actual inserts may be less
                total_inserted += inserted
            print(f"ingest_supplier_stocks: inserted {inserted} records (page {total_pages})")
        else:
            print(f"ingest_supplier_stocks: no valid rows to insert for page {total_pages}")
        
        # Если нет lastChangeDate, завершаем
        if not last_change_date_str:
            print("ingest_supplier_stocks: no lastChangeDate in response, pagination complete")
            break
        
        # Использовать lastChangeDate последней строки как следующий dateFrom
        date_from = last_change_date_str
        print(f"ingest_supplier_stocks: next dateFrom={date_from} (from last row's lastChangeDate)")
        
        # Rate limit: sleep 60 секунд между запросами
        if total_pages > 0:  # Не спать после последней страницы
            print(f"ingest_supplier_stocks: rate limit throttling, sleeping {rate_limit_delay} seconds...")
            await asyncio.sleep(rate_limit_delay)
    
    print(f"ingest_supplier_stocks: finished. pages={total_pages}, total_inserted={total_inserted}")


@router.get("/supplier-stocks")
async def get_supplier_stocks_info():
    """Get information about supplier stocks ingestion endpoint."""
    token = os.getenv("WB_TOKEN", "")
    endpoint = "https://statistics-api.wildberries.ru/api/v1/supplier/stocks"
    
    return {
        "endpoint": endpoint,
        "token_configured": bool(token and token != "MOCK"),
        "mock_mode": token.upper() == "MOCK",
        "rate_limit": "1 request per minute",
        "pagination": "via lastChangeDate parameter"
    }


@router.post("/supplier-stocks")
async def start_ingest_supplier_stocks(background_tasks: BackgroundTasks):
    """Start ingestion of supplier stock balances from WB Statistics API."""
    token = os.getenv("WB_TOKEN", "") or ""
    if not token or token.upper() == "MOCK":
        return {
            "status": "skipped",
            "message": "Supplier stocks ingestion skipped (MOCK mode or no token configured)"
        }
    
    background_tasks.add_task(ingest_supplier_stocks)
    return {"status": "started", "message": "Supplier stocks ingestion started in background"}


@supplier_stocks_router.get("/supplier-stocks/latest")
async def get_latest_supplier_stocks(limit: int = Query(5, ge=1, le=1000)):
    """Return latest supplier stock snapshots.
    
    Возвращает последние записи из supplier_stock_snapshots,
    отсортированные по last_change_date DESC.
    """
    sql = text("""
        SELECT 
            snapshot_at, last_change_date, warehouse_name, nm_id,
            supplier_article, barcode, tech_size, quantity, quantity_full,
            in_way_to_client, in_way_from_client, is_supply, is_realization,
            price, discount
        FROM supplier_stock_snapshots
        ORDER BY last_change_date DESC, nm_id
        LIMIT :limit
    """)
    
    with engine.connect() as conn:
        result = conn.execute(sql, {"limit": limit}).mappings().all()
        rows = [dict(row) for row in result]
    
    return rows

