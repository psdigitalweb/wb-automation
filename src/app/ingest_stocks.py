"""Ingestion endpoints for warehouses and stock balances."""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks
from sqlalchemy import text

from app.db import engine
from app.wb.client import WBClient

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


def _serialize_json_field(value: Any) -> Optional[str]:
    """Convert Python objects to JSON strings for JSONB fields."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


async def ingest_warehouses() -> None:
    """Fetch and upsert warehouses/offices from WB API."""
    token = os.getenv("WB_TOKEN", "") or ""
    if not token or token.upper() == "MOCK":
        print("ingest_warehouses: skipped (MOCK mode or no token)")
        return
    
    client = WBClient()
    warehouses = await client.fetch_warehouses()
    
    if not warehouses:
        print("ingest_warehouses: no warehouses returned from API")
        return
    
    print(f"ingest_warehouses: fetched {len(warehouses)} warehouses")
    
    upsert_sql = text("""
        INSERT INTO wb_warehouses (wb_id, name, city, address, type, raw, updated_at)
        VALUES (:wb_id, :name, :city, :address, :type, :raw, now())
        ON CONFLICT (wb_id) DO UPDATE SET
            name = EXCLUDED.name,
            city = EXCLUDED.city,
            address = EXCLUDED.address,
            type = EXCLUDED.type,
            raw = EXCLUDED.raw,
            updated_at = now()
    """)
    
    rows = []
    for wh in warehouses:
        wb_id = wh.get("id") or wh.get("wb_id") or wh.get("warehouseId")
        name = wh.get("name") or wh.get("warehouseName")
        city = wh.get("city")
        address = wh.get("address")
        wh_type = wh.get("type") or wh.get("warehouseType")
        
        if not wb_id:
            print(f"ingest_warehouses: skipping warehouse without id: {wh}")
            continue
        
        rows.append({
            "wb_id": wb_id,
            "name": name,
            "city": city,
            "address": address,
            "type": wh_type,
            "raw": _serialize_json_field(wh)
        })
    
    if rows:
        with engine.begin() as conn:
            conn.execute(upsert_sql, rows)
        print(f"ingest_warehouses: upserted {len(rows)} warehouses")
    else:
        print("ingest_warehouses: no valid warehouses to upsert")


async def ingest_stocks() -> None:
    """Fetch and insert stock snapshots from WB API."""
    token = os.getenv("WB_TOKEN", "") or ""
    if not token or token.upper() == "MOCK":
        print("ingest_stocks: skipped (MOCK mode or no token)")
        return
    
    client = WBClient()
    stocks = await client.fetch_stocks()
    
    if not stocks:
        print("ingest_stocks: no stocks returned from API")
        return
    
    print(f"ingest_stocks: fetched {len(stocks)} stock records")
    
    insert_sql = text("""
        INSERT INTO stock_snapshots (nm_id, warehouse_wb_id, quantity, snapshot_at, raw)
        VALUES (:nm_id, :warehouse_wb_id, :quantity, now(), :raw)
    """)
    
    rows = []
    for stock in stocks:
        nm_id = stock.get("nmId") or stock.get("nm_id") or stock.get("nmID")
        warehouse_wb_id = stock.get("warehouseId") or stock.get("warehouse_id") or stock.get("warehouse_wb_id")
        quantity = stock.get("quantity") or stock.get("qty") or stock.get("stock") or 0
        
        if not nm_id:
            print(f"ingest_stocks: skipping stock without nm_id: {stock}")
            continue
        
        rows.append({
            "nm_id": nm_id,
            "warehouse_wb_id": warehouse_wb_id,
            "quantity": int(quantity),
            "raw": _serialize_json_field(stock)
        })
    
    if rows:
        # Batch insert in chunks of 200
        chunk_size = 200
        total_inserted = 0
        with engine.begin() as conn:
            for i in range(0, len(rows), chunk_size):
                chunk = rows[i:i + chunk_size]
                conn.execute(insert_sql, chunk)
                total_inserted += len(chunk)
        print(f"ingest_stocks: inserted {total_inserted} stock snapshots")
    else:
        print("ingest_stocks: no valid stocks to insert")


@router.get("/warehouses")
async def get_warehouses_info():
    """Get information about warehouses ingestion endpoint."""
    token = os.getenv("WB_TOKEN", "")
    endpoint = "https://content-api.wildberries.ru/api/v1/warehouses"
    
    return {
        "endpoint": endpoint,
        "token_configured": bool(token and token != "MOCK"),
        "mock_mode": token.upper() == "MOCK"
    }


@router.post("/warehouses")
async def start_ingest_warehouses(background_tasks: BackgroundTasks):
    """Start ingestion of warehouses from Wildberries API."""
    token = os.getenv("WB_TOKEN", "") or ""
    if not token or token.upper() == "MOCK":
        return {
            "status": "skipped",
            "message": "Warehouses ingestion skipped (MOCK mode or no token configured)"
        }
    
    background_tasks.add_task(ingest_warehouses)
    return {"status": "started", "message": "Warehouses ingestion started in background"}


@router.get("/stocks")
async def get_stocks_info():
    """Get information about stocks ingestion endpoint."""
    token = os.getenv("WB_TOKEN", "")
    endpoint = "https://content-api.wildberries.ru/api/v1/supplies/stocks"
    
    return {
        "endpoint": endpoint,
        "token_configured": bool(token and token != "MOCK"),
        "mock_mode": token.upper() == "MOCK"
    }


@router.post("/stocks")
async def start_ingest_stocks(background_tasks: BackgroundTasks):
    """Start ingestion of stock balances from Wildberries API."""
    token = os.getenv("WB_TOKEN", "") or ""
    if not token or token.upper() == "MOCK":
        return {
            "status": "skipped",
            "message": "Stocks ingestion skipped (MOCK mode or no token configured)"
        }
    
    background_tasks.add_task(ingest_stocks)
    return {"status": "started", "message": "Stocks ingestion started in background"}

