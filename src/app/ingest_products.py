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
from typing import Any, Dict, List, Optional, Tuple, Set, Union

import httpx
from fastapi import APIRouter, BackgroundTasks, Path, Depends

from app.db_products import ensure_schema, upsert_products
from app.deps import get_current_active_user, get_project_membership
from app.utils.get_project_marketplace_token import get_wb_credentials_for_project
from app.db import engine
from sqlalchemy import text

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
    # From actual API response: nmID, vendorCode, title, brand, subjectName, etc.
    nm_id = item.get("nmID") or item.get("nm_id") or item.get("nmId") or item.get("id")
    vendor_code = item.get("vendorCode") or item.get("vendor_code") or item.get("article")
    title = item.get("title") or item.get("name")
    brand = item.get("brand")
    subject_id = item.get("subjectID") or item.get("subject_id") or item.get("subjectId")
    subject_name = item.get("subjectName") or item.get("subject_name") or item.get("subject")
    description = item.get("description")

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
    
    # Dimensions, characteristics, metadata from API
    dimensions = item.get("dimensions")
    characteristics = item.get("characteristics")
    
    # Parse dates from API
    created_at_api = None
    if item.get("createdAt"):
        try:
            from datetime import datetime
            created_at_api = datetime.fromisoformat(item["createdAt"].replace("Z", "+00:00"))
        except (ValueError, AttributeError, TypeError):
            pass
    
    need_kiz = item.get("needKiz") or item.get("need_kiz")

    print(f"Mapping card: nmID={nm_id}, vendorCode={vendor_code}, title={title[:50] if title else None}...")

    return {
        "nm_id": nm_id,
        "vendor_code": vendor_code,
        "title": title,
        "brand": brand,
        "subject_id": subject_id,
        "subject_name": subject_name,
        "description": description,
        "price_u": price_u,
        "sale_price_u": sale_price_u,
        "rating": rating,
        "feedbacks": feedbacks,
        "sizes": _serialize_json_field(sizes),
        "colors": _serialize_json_field(colors),
        "pics": _serialize_json_field(pics),
        "dimensions": _serialize_json_field(dimensions),
        "characteristics": _serialize_json_field(characteristics),
        "created_at_api": created_at_api,
        "need_kiz": need_kiz,
        "raw": _serialize_json_field(item),
    }


CursorType = Optional[Union[str, Dict[str, Any]]]


async def fetch_page(
    client: httpx.AsyncClient,
    endpoint: str,
    cursor: CursorType,
    page_size: int,
) -> Tuple[List[Dict[str, Any]], CursorType, Optional[int]]:
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
    cursor_obj: Dict[str, Any] = {"limit": page_size}
    if cursor:
        # WB cursor should contain updatedAt + nmID. Keep it strict to avoid sending
        # extra fields (like total) back to WB.
        if isinstance(cursor, str):
            cursor_obj["updatedAt"] = cursor
        elif isinstance(cursor, dict):
            if cursor.get("updatedAt") is not None:
                cursor_obj["updatedAt"] = cursor.get("updatedAt")
            if cursor.get("nmID") is not None:
                cursor_obj["nmID"] = cursor.get("nmID")
    
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
        cards: List[Dict[str, Any]] = []
        next_cursor: CursorType = None
        cursor_total: Optional[int] = None
        
        if isinstance(p2, dict):
            # Direct cards array (as in AppScript)
            cards = p2.get("cards", [])
            print(f"WB response: found {len(cards)} cards")
            
            # Cursor for next page (as in AppScript)
            cursor_data = p2.get("cursor")
            if isinstance(cursor_data, dict):
                # Useful for diagnostics: WB sometimes returns total in cursor.
                try:
                    if cursor_data.get("total") is not None:
                        cursor_total = int(cursor_data.get("total"))
                except (ValueError, TypeError):
                    cursor_total = None
                if cursor_data.get("updatedAt") and cursor_data.get("nmID"):
                    next_cursor = {"updatedAt": cursor_data.get("updatedAt"), "nmID": cursor_data.get("nmID")}
                    print(f"WB response: next cursor = {next_cursor}, cursor_total={cursor_total}")
            elif isinstance(cursor_data, dict) and cursor_data.get("updatedAt"):
                next_cursor = cursor_data.get("updatedAt")  # Fallback to just timestamp
                print(f"WB response: next cursor timestamp = {next_cursor}, cursor_total={cursor_total}")
        
        if not cards:
            print("WB response: no cards found")
            return [], None, cursor_total
        return cards, next_cursor, cursor_total
        
    except Exception as exc:  # minimal handling/logging as requested
        print(f"fetch_page: exception: {exc}")
        return [], None, None


def _get_existing_nm_ids(project_id: int, nm_ids: List[int]) -> Set[int]:
    """Return set of nm_id that already exist for this project (upsert conflict key)."""
    if not nm_ids:
        return set()
    stmt = text(
        """
        SELECT nm_id
        FROM products
        WHERE project_id = :project_id
          AND nm_id = ANY(:nm_ids)
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(stmt, {"project_id": project_id, "nm_ids": nm_ids}).fetchall()
    return {int(r[0]) for r in rows}


async def ingest(project_id: int, loop_delay_s: float = 6.0) -> None:
    """Main ingestion loop: ensure schema, then page through API and upsert.
    
    Args:
        project_id: Project ID to associate products with (required).
        loop_delay_s: Delay between requests in seconds (default 6s for WB API limits)
    """
    ensure_schema()
    print(f"ingest: products schema ensured, project_id={project_id}")

    # Get credentials from project_marketplaces (preferred) or fallback to env
    try:
        credentials = get_wb_credentials_for_project(project_id)
        if credentials:
            token = credentials.get("token", "")
        else:
            # Not enabled or no connection - use env fallback
            token = os.getenv("WB_TOKEN", "") or ""
    except ValueError as e:
        # Enabled but not connected - log error and skip (error already checked at endpoint level)
        print(f"ingest: {str(e)}, skipping")
        return
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
        cursor: CursorType = None
        page_num = 1
        pages_count = 0
        fetched_total = 0
        stored_total = 0  # rows sent to upsert (after nm_id filter), incl duplicates
        updated_total = 0  # conflicts (existing rows by upsert key)
        inserted_total = 0  # new rows by upsert key
        uniq_nm_ids: Set[int] = set()
        dup_nm_ids_total = 0
        wb_cursor_total_first: Optional[int] = None
        wb_cursor_total_last: Optional[int] = None
        
        while True:
            items, next_cursor, cursor_total = await fetch_page(client, endpoint, cursor, page_size)
            if not items:
                print(f"ingest: page={page_num} empty, stopping")
                break

            pages_count += 1
            fetched_total += len(items)
            if cursor_total is not None:
                wb_cursor_total_last = cursor_total
                if wb_cursor_total_first is None:
                    wb_cursor_total_first = cursor_total

            rows = [_to_row(it) for it in items]
            # Filter out rows without nm_id (cannot upsert without key)
            rows = [r for r in rows if r.get("nm_id") is not None]
            if not rows:
                print(f"ingest: page={page_num} had no valid rows, skipping")
            else:
                # Dedup diagnostics within this run
                nm_ids_page = [int(r["nm_id"]) for r in rows if r.get("nm_id") is not None]
                dup_in_page = 0
                for nm in nm_ids_page:
                    if nm in uniq_nm_ids:
                        dup_in_page += 1
                    else:
                        uniq_nm_ids.add(nm)
                dup_nm_ids_total += dup_in_page

                # Conflict diagnostics against DB upsert key (project_id, nm_id)
                existing = _get_existing_nm_ids(project_id, nm_ids_page)
                would_update = sum(1 for nm in nm_ids_page if nm in existing)
                would_insert = len(nm_ids_page) - would_update

                inserted_total += would_insert
                updated_total += would_update
                stored_total += len(nm_ids_page)

                res = upsert_products(rows, project_id)
                print(
                    "ingest: page={page} fetched={fetched} stored={stored} "
                    "would_insert={would_insert} would_update={would_update} dup_in_run={dup_in_run} "
                    "upsert_reported_inserted={ins_est} upsert_reported_updated={upd_est}".format(
                        page=page_num,
                        fetched=len(items),
                        stored=len(nm_ids_page),
                        would_insert=would_insert,
                        would_update=would_update,
                        dup_in_run=dup_in_page,
                        ins_est=res["inserted"],
                        upd_est=res["updated"],
                    )
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

        print(
            "ingest: summary project_id={project_id} pages_count={pages_count} "
            "fetched_total={fetched_total} stored_total={stored_total} uniq_nm_ids={uniq_nm_ids} "
            "would_insert_total={inserted_total} would_update_total={updated_total} dup_in_run_total={dup_total} "
            "wb_cursor_total_first={wb_total_first} wb_cursor_total_last={wb_total_last}".format(
                project_id=project_id,
                pages_count=pages_count,
                fetched_total=fetched_total,
                stored_total=stored_total,
                uniq_nm_ids=len(uniq_nm_ids),
                inserted_total=inserted_total,
                updated_total=updated_total,
                dup_total=dup_nm_ids_total,
                wb_total_first=wb_cursor_total_first,
                wb_total_last=wb_cursor_total_last,
            )
        )


def _sync_entry() -> None:
    asyncio.run(ingest())


@router.post("/projects/{project_id}/products")
async def start_ingest_products(
    project_id: int = Path(..., description="Project ID"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    loop_delay_s: float = 6.0,
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership)
):
    """Start ingestion of products from Wildberries API for a specific project.
    
    Requires project membership.
    
    Args:
        project_id: Project ID to associate products with.
        loop_delay_s: Delay between requests in seconds (default 6s for WB API limits)
    """
    # Check credentials before starting background task
    try:
        credentials = get_wb_credentials_for_project(project_id)
        if credentials is None:
            # Not enabled or no connection - allow env fallback
            pass
    except ValueError as e:
        # Enabled but not connected - return error
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    background_tasks.add_task(ingest, project_id, loop_delay_s)
    return {"status": "started", "message": f"Product ingestion started in background for project {project_id}"}


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


