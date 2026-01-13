"""Ingestion endpoints for warehouses and stock balances."""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Query
from sqlalchemy import text

from app.db import engine
from app.wb.client import WBClient
from app import db_products

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])
# Отдельный роутер для витринных эндпоинтов по остаткам
stocks_router = APIRouter(prefix="/api/v1", tags=["stocks"])


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
    """Fetch and insert stock snapshots from WB API.

    Алгоритм:
    1. Получаем список складов из wb_warehouses (если нет — дергаем ingest_warehouses).
    2. Получаем список chrtIds из products (через db_products.get_chrt_ids).
    3. Для каждого склада и батча chrtIds вызываем WB API:
       POST /api/v3/stocks/{warehouseId} с body {"chrtIds": [...]}
    4. Сохраняем результаты в stock_snapshots (append-only).
    """
    token = os.getenv("WB_TOKEN", "") or ""
    if not token or token.upper() == "MOCK":
        print("ingest_stocks: skipped (MOCK mode or no token)")
        return
    # 1. Получаем склады из wb_warehouses
    select_warehouses_sql = text(
        "SELECT wb_id, name FROM wb_warehouses ORDER BY wb_id"
    )

    with engine.connect() as conn:
        warehouses = [dict(row) for row in conn.execute(select_warehouses_sql)]

    if not warehouses:
        print("ingest_stocks: wb_warehouses is empty, running ingest_warehouses first")
        await ingest_warehouses()
        with engine.connect() as conn:
            warehouses = [dict(row) for row in conn.execute(select_warehouses_sql)]

    if not warehouses:
        print("ingest_stocks: no warehouses available after ingest_warehouses, aborting")
        return

    print(f"ingest_stocks: using {len(warehouses)} warehouses from wb_warehouses")

    # 2. Получаем chrtIds из products
    chrt_ids = db_products.get_chrt_ids()
    if not chrt_ids:
        print(
            "ingest_stocks: no chrtIds found in products; "
            "ensure products are ingested and contain sizes/raw.sizes"
        )
        return

    print(f"ingest_stocks: got {len(chrt_ids)} unique chrtIds from products")

    client = WBClient()

    insert_sql = text(
        """
        INSERT INTO stock_snapshots (nm_id, warehouse_wb_id, quantity, snapshot_at, raw)
        VALUES (:nm_id, :warehouse_wb_id, :quantity, now(), :raw)
        """
    )

    # Для сопоставления chrtId -> nm_id используем products.raw->'sizes'
    chrt_to_nm_sql = text(
        """
        SELECT (elem->>'chrtID')::bigint AS chrt_id,
               nm_id
        FROM products
        CROSS JOIN LATERAL jsonb_array_elements(
            COALESCE(sizes, raw->'sizes')
        ) AS elem
        WHERE elem ? 'chrtID'
          AND (elem->>'chrtID') ~ '^[0-9]+'
        """
    )

    with engine.connect() as conn:
        mapping_rows = conn.execute(chrt_to_nm_sql)
        chrt_to_nm: Dict[int, int] = {
            int(row.chrt_id): int(row.nm_id) for row in mapping_rows if row.chrt_id is not None
        }

    print(f"ingest_stocks: built chrtId->nm_id mapping for {len(chrt_to_nm)} sizes")

    # 3. Для каждого склада и батча chrtIds запрашиваем остатки
    # Лимит WB API: максимум 1000 chrtIds на запрос
    batch_size = 1000
    total_api_records = 0
    total_inserted = 0

    for wh in warehouses:
        warehouse_id = wh["wb_id"]
        print(f"ingest_stocks: fetching stocks for warehouse {warehouse_id}")

        for i in range(0, len(chrt_ids), batch_size):
            batch_chrt_ids = chrt_ids[i : i + batch_size]
            print(
                f"ingest_stocks: warehouse={warehouse_id}, chrtIds_chunk={len(batch_chrt_ids)}"
            )
            stocks = await client.fetch_stocks(warehouse_id, batch_chrt_ids)

            if not stocks:
                print(
                    f"ingest_stocks: warehouse={warehouse_id}, chunk_size={len(batch_chrt_ids)}, stocks=0"
                )
                continue

            print(
                f"ingest_stocks: warehouse={warehouse_id}, chunk_size={len(batch_chrt_ids)}, stocks={len(stocks)}"
            )
            total_api_records += len(stocks)

            rows: List[Dict[str, Any]] = []
            for stock in stocks:
                chrt_id = (
                    stock.get("chrtId")
                    or stock.get("chrtID")
                    or stock.get("chrt_id")
                )
                nm_id = (
                    stock.get("nmId")
                    or stock.get("nm_id")
                    or stock.get("nmID")
                    or (chrt_to_nm.get(int(chrt_id)) if chrt_id is not None else None)
                )
                warehouse_wb_id = (
                    stock.get("warehouseId")
                    or stock.get("warehouse_id")
                    or stock.get("warehouse_wb_id")
                    or warehouse_id
                )
                quantity = (
                    stock.get("quantity")
                    or stock.get("qty")
                    or stock.get("stock")
                    or stock.get("amount")
                    or 0
                )

                if nm_id is None:
                    print(
                        f"ingest_stocks: skipping stock without nm_id and mapping, chrt_id={chrt_id}"
                    )
                    continue

                rows.append(
                    {
                        "nm_id": int(nm_id),
                        "warehouse_wb_id": int(warehouse_wb_id)
                        if warehouse_wb_id is not None
                        else None,
                        "quantity": int(quantity),
                        "raw": _serialize_json_field(stock),
                    }
                )

            if rows:
                with engine.begin() as conn:
                    conn.execute(insert_sql, rows)
                    total_inserted += len(rows)

    print(
        f"ingest_stocks: finished. api_records={total_api_records} inserted={total_inserted}"
    )


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
    endpoint = "https://marketplace-api.wildberries.ru/api/v3/stocks/{warehouseId}"
    
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


@stocks_router.get("/stocks/latest")
async def get_latest_stocks(limit: int = Query(5, ge=1, le=1000)):
    """Return latest stock snapshots.

    Возвращает последние записи из stock_snapshots, отсортированные по snapshot_at DESC.
    """
    sql = text(
        """
        SELECT nm_id, warehouse_wb_id, quantity, snapshot_at
        FROM stock_snapshots
        ORDER BY snapshot_at DESC, nm_id
        LIMIT :limit
        """
    )

    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(sql, {"limit": limit})]

    return rows

