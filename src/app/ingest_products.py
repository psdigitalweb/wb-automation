"""Simple ingestor for Wildberries products into Postgres `products` table.

Features:
- Async pagination via httpx
- Auth via WB_TOKEN env var
- Upserts into DB using app.db_products.ensure_schema and upsert_products

Notes:
- If WB_TOKEN == "MOCK", generates mock pages for local testing.
- The remote endpoint/shape can be adjusted easily in `fetch_page`.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, BackgroundTasks

from app.db_products import ensure_schema, upsert_products

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


WB_DEFAULT_ENDPOINT = (
    # Official Wildberries Content API v2 list endpoint per products.yaml
    # https://dev.wildberries.ru/yaml/ru/02-products.yaml
    "https://content-api.wildberries.ru/content/v2/get/cards/list"
)


def _serialize_json_field(value: Any) -> Optional[str]:
    """Convert Python objects to JSON strings for JSONB fields."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _to_row(item: Dict[str, Any]) -> Dict[str, Any]:
    """Map a WB item dict to the products table row shape.

    Based on actual API response structure from AppScript.
    """
    # From actual API response: nmID, vendorCode, title, brand, subjectName
    nm_id = item.get("nmID") or item.get("nm_id") or item.get("nmId") or item.get("id")
    vendor_code = item.get("vendorCode") or item.get("vendor_code") or item.get("article")
    title = item.get("title") or item.get("name")
    brand = item.get("brand")
    subject_name = item.get("subjectName") or item.get("subject_name") or item.get("subject")

    # Prices: API response doesn't include prices in cards list
    # These would need to be fetched separately from prices API
    price_u = None
    sale_price_u = None

    # Rating and feedbacks: not in cards response
    rating = None
    feedbacks = None
    
    # Photos array from API response
    pics = item.get("photos") or item.get("pics") or item.get("images")
    
    # Sizes and colors: not in basic cards response
    sizes = None
    colors = None

    print(f"Mapping card: nmID={nm_id}, vendorCode={vendor_code}, title={title[:50] if title else None}...")

    return {
        "nm_id": nm_id,
        "vendor_code": vendor_code,
        "title": title,
        "brand": brand,
        "subject_name": subject_name,
        "price_u": price_u,
        "sale_price_u": sale_price_u,
        "rating": rating,
        "feedbacks": feedbacks,
        "sizes": _serialize_json_field(sizes),
        "colors": _serialize_json_field(colors),
        "pics": _serialize_json_field(pics),
        "raw": _serialize_json_field(item),
    }


async def fetch_page(
    client: httpx.AsyncClient,
    endpoint: str,
    cursor: Optional[str],
    page_size: int,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Fetch a single page from WB Content API using cursor-based pagination.

    Returns (items, next_cursor). If next_cursor is None, the caller should stop.
    """
    token = client.headers.get("Authorization", "")

    if token.upper() == "MOCK":
        # Generate deterministic mock data
        if cursor is None:  # First page
            mock_cursor = "mock_page_1"
        elif cursor == "mock_page_1":
            mock_cursor = "mock_page_2"
        elif cursor == "mock_page_2":
            mock_cursor = "mock_page_3"
        else:  # mock_page_3 or beyond
            return [], None

        items: List[Dict[str, Any]] = []
        start_id = 100000 if cursor is None else 100000 + (page_size * 2 if cursor == "mock_page_2" else page_size)
        for i in range(start_id, start_id + page_size):
            items.append(
                {
                    "nm_id": i,
                    "vendor_code": f"SKU-{i}",
                    "title": f"Mock Product {i}",
                    "brand": "MockBrand",
                    "subject_name": "MockSubject",
                    "price_u": 199900,
                    "sale_price_u": 149900,
                    "rating": 4.6,
                    "feedbacks": 42,
                    "sizes": ["S", "M", "L"],
                    "colors": ["black", "white"],
                    "pics": [
                        {"url": f"https://example.com/pic/{i}/1.jpg"},
                        {"url": f"https://example.com/pic/{i}/2.jpg"},
                    ],
                }
            )
        return items, mock_cursor

    # Real request using POST /content/v2/get/cards/list (cursor pagination)
    # Structure exactly as in working AppScript
    cursor_obj = {"limit": page_size}
    if cursor:
        # If cursor is provided, it should contain both updatedAt and nmID
        # For now, assume cursor is a dict or split it if it's a string
        if isinstance(cursor, str):
            # Simple case: just updatedAt timestamp
            cursor_obj["updatedAt"] = cursor
        else:
            cursor_obj.update(cursor)
    
    v2_body = {
        "settings": {
            "cursor": cursor_obj,
            "filter": {"withPhoto": -1}  # exactly as in AppScript
        }
    }

    try:
        print(f"WB request: POST {endpoint} body={v2_body}")
        print(f"WB headers: {dict(client.headers)}")
        r = await client.post(endpoint, json=v2_body)
        if r.status_code != 200:
            print(f"fetch_page: non-200 status={r.status_code}, stop pagination")
            return [], None

        p2 = r.json()
        print(f"WB response: HTTP {r.status_code}, cards count: {len(p2.get('cards', []))}")
        
        # Parse exactly as in AppScript: direct cards array
        cards = []
        next_cursor = None
        
        if isinstance(p2, dict):
            # Direct cards array (as in AppScript)
            cards = p2.get("cards", [])
            print(f"WB response: found {len(cards)} cards")
            
            # Cursor for next page (as in AppScript)
            cursor_data = p2.get("cursor")
            if isinstance(cursor_data, dict) and cursor_data.get("updatedAt") and cursor_data.get("nmID"):
                next_cursor = cursor_data  # Return full cursor object
                print(f"WB response: next cursor = {cursor_data}")
            elif isinstance(cursor_data, dict) and cursor_data.get("updatedAt"):
                next_cursor = cursor_data.get("updatedAt")  # Fallback to just timestamp
                print(f"WB response: next cursor timestamp = {next_cursor}")
        
        if not cards:
            print("WB response: no cards found")
            return [], None
        return cards, next_cursor
        
    except Exception as exc:  # minimal handling/logging as requested
        print(f"fetch_page: exception: {exc}")
        return [], None


async def ingest(loop_delay_s: float = 6.0) -> None:
    """Main ingestion loop: ensure schema, then page through API and upsert.
    
    Args:
        loop_delay_s: Delay between requests in seconds (default 6s for WB API limits)
    """
    ensure_schema()
    print("ingest: products schema ensured")

    token = os.getenv("WB_TOKEN", "") or ""
    endpoint = os.getenv("WB_ENDPOINT", WB_DEFAULT_ENDPOINT)
    page_size = int(os.getenv("WB_PAGE_SIZE", "100"))
    max_pages_env = os.getenv("WB_MAX_PAGES")
    max_pages: Optional[int] = int(max_pages_env) if max_pages_env else None

    # Explicit headers with Authorization first (Bearer prefix as in AppScript)
    request_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=30, headers=request_headers) as client:
        cursor: Optional[str] = None
        page_num = 1
        total_processed = 0
        
        while True:
            items, next_cursor = await fetch_page(client, endpoint, cursor, page_size)
            if not items:
                print(f"ingest: page={page_num} empty, stopping")
                break

            rows = [_to_row(it) for it in items]
            # Filter out rows without nm_id (cannot upsert without key)
            rows = [r for r in rows if r.get("nm_id") is not None]
            if not rows:
                print(f"ingest: page={page_num} had no valid rows, skipping")
            else:
                res = upsert_products(rows)
                total_processed += len(rows)
                print(
                    f"ingest: page={page_num} processed={len(rows)} inserted={res['inserted']} updated={res['updated']}"
                )

            if next_cursor is None:
                print("ingest: no more pages available, stopping")
                break
                
            cursor = next_cursor
            page_num += 1
            
            if max_pages is not None and page_num > max_pages:
                print(f"ingest: reached WB_MAX_PAGES={max_pages}, stopping")
                break
                
            if loop_delay_s > 0:
                await asyncio.sleep(loop_delay_s)

        print(f"ingest: done, total_processed={total_processed}")


def _sync_entry() -> None:
    asyncio.run(ingest())


@router.post("/products")
async def start_ingest_products(background_tasks: BackgroundTasks, loop_delay_s: float = 6.0):
    """Start ingestion of products from Wildberries API.
    
    Args:
        loop_delay_s: Delay between requests in seconds (default 6s for WB API limits)
    """
    background_tasks.add_task(ingest, loop_delay_s)
    return {"status": "started", "message": "Product ingestion started in background"}


@router.get("/products")
async def get_ingest_info():
    """Get information about product ingestion endpoint."""
    token = os.getenv("WB_TOKEN", "")
    endpoint = os.getenv("WB_ENDPOINT", WB_DEFAULT_ENDPOINT)
    page_size = int(os.getenv("WB_PAGE_SIZE", "100"))
    max_pages = os.getenv("WB_MAX_PAGES")
    
    return {
        "endpoint": endpoint,
        "page_size": page_size,
        "max_pages": max_pages,
        "token_configured": bool(token and token != "MOCK"),
        "mock_mode": token.upper() == "MOCK"
    }


if __name__ == "__main__":
    _sync_entry()


