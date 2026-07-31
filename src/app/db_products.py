"""Lightweight data-access helpers for the `products` table.

This module provides:
- ensure_schema(): idempotently creates the `products` table and indexes
- upsert_products(rows): batch upsert by `nm_id` using INSERT ... ON CONFLICT

Constraints:
- Uses existing SQLAlchemy Engine from app.main
- Raw SQL via sqlalchemy.text
- Safe to run multiple times
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Iterator, List, Optional

from sqlalchemy import text

# Import engine from db module to avoid circular imports
from app.db import engine


def ensure_schema() -> None:
    """Create `products` table and indexes if they do not exist.

    The schema uses JSONB and timestamptz columns as requested. This function is
    idempotent and may be safely executed multiple times.
    """

    create_table_sql = text(
        """
        CREATE TABLE IF NOT EXISTS products (
            id              SERIAL PRIMARY KEY,
            nm_id           BIGINT UNIQUE NOT NULL,
            vendor_code     TEXT,
            title           TEXT,
            brand           TEXT,
            subject_id      INTEGER,
            subject_name    TEXT,
            description     TEXT,
            price_u         BIGINT,
            sale_price_u    BIGINT,
            rating          NUMERIC(3, 2),
            feedbacks       INTEGER,
            sizes           JSONB,
            colors          JSONB,
            pics            JSONB,
            dimensions      JSONB,
            characteristics JSONB,
            created_at_api  TIMESTAMPTZ,
            need_kiz        BOOLEAN,
            raw             JSONB,
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    # Check which columns exist before creating indexes
    # This prevents errors if columns don't exist yet (e.g., during migration)
    check_column_sql = text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'products' AND table_schema = 'public'
    """)
    
    create_indexes_sql: List = []

    with engine.begin() as conn:
        conn.execute(create_table_sql)
        
        # Get existing columns
        result = conn.execute(check_column_sql)
        existing_columns = {row[0] for row in result}
        
        # Only create indexes for columns that exist
        if 'brand' in existing_columns:
            create_indexes_sql.append(text("CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand);"))
        if 'subject_name' in existing_columns:
            create_indexes_sql.append(text("CREATE INDEX IF NOT EXISTS idx_products_subject ON products(subject_name);"))
        if 'subject_id' in existing_columns:
            create_indexes_sql.append(text("CREATE INDEX IF NOT EXISTS idx_products_subject_id ON products(subject_id);"))
        if 'nm_id' in existing_columns:
            create_indexes_sql.append(text("CREATE INDEX IF NOT EXISTS idx_products_nm_id ON products(nm_id);"))
        if 'vendor_code' in existing_columns:
            create_indexes_sql.append(text("CREATE INDEX IF NOT EXISTS idx_products_vendor_code ON products(vendor_code);"))
        
        for stmt in create_indexes_sql:
            conn.execute(stmt)

    print("ensure_schema: products table and indexes are ensured")


def _chunked(iterable: Iterable[Dict[str, Any]], size: int) -> Iterator[List[Dict[str, Any]]]:
    """Yield lists of up to `size` elements from `iterable`.

    This helper does not assume the input size is divisible by `size`.
    """
    if size <= 0:
        raise ValueError("size must be a positive integer")

    batch: List[Dict[str, Any]] = []
    for item in iterable:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def upsert_products(
    rows: List[Dict[str, Any]],
    project_id: int,
    *,
    ingest_run_id: Optional[int] = None,
    photo_attempts: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Dict[str, int]:
    """Insert or update product rows by `nm_id` in batches of 200.

    Args:
        rows: List of dicts with keys: nm_id, vendor_code, title, brand,
              subject_id, subject_name, description, price_u, sale_price_u, 
              rating, feedbacks, sizes, colors, pics, dimensions, 
              characteristics, created_at_api, need_kiz, raw. Values may be None.
        project_id: Project ID to associate products with (required).

    Returns:
        Dict with approximate counts: {"inserted": X, "updated": Y}.
    """
    if not rows:
        return {
            "inserted": 0,
            "updated": 0,
            "changed": 0,
            "unchanged": 0,
            "versions_created": 0,
            "main_photos_stored": 0,
            "main_photos_reused": 0,
            "main_photos_skipped_inactive": 0,
            "main_photo_archive_failed": 0,
        }

    from app.services.wb_product_content.history import (
        history_enabled_for_project,
        persist_product_content,
    )

    if history_enabled_for_project(project_id):
        stats = {
            "inserted": 0,
            "updated": 0,
            "changed": 0,
            "unchanged": 0,
            "versions_created": 0,
            "main_photos_stored": 0,
            "main_photos_reused": 0,
            "main_photos_skipped_inactive": 0,
            "main_photo_archive_failed": 0,
        }
        attempts = photo_attempts or {}
        for row in rows:
            result = persist_product_content(
                row=row,
                project_id=project_id,
                ingest_run_id=ingest_run_id,
                photo_attempt=attempts.get(int(row["nm_id"])),
            )
            if result["initial"]:
                stats["inserted"] += 1
            else:
                stats["updated"] += 1
            if result["changed"]:
                stats["changed"] += 1
                stats["versions_created"] += 1
            else:
                stats["unchanged"] += 1
            photo_status = result.get("photo_status")
            if photo_status == "stored":
                stats["main_photos_stored"] += 1
                if result.get("photo_reused"):
                    stats["main_photos_reused"] += 1
            elif photo_status == "skipped_inactive":
                stats["main_photos_skipped_inactive"] += 1
            elif photo_status == "failed":
                stats["main_photo_archive_failed"] += 1
        return stats

    insert_sql = text(
        """
        INSERT INTO products (
            nm_id,
            vendor_code,
            title,
            brand,
            subject_id,
            subject_name,
            description,
            price_u,
            sale_price_u,
            rating,
            feedbacks,
            sizes,
            colors,
            pics,
            dimensions,
            characteristics,
            created_at_api,
            need_kiz,
            raw,
            project_id
        ) VALUES (
            :nm_id,
            :vendor_code,
            :title,
            :brand,
            :subject_id,
            :subject_name,
            :description,
            :price_u,
            :sale_price_u,
            :rating,
            :feedbacks,
            :sizes,
            :colors,
            :pics,
            :dimensions,
            :characteristics,
            :created_at_api,
            :need_kiz,
            :raw,
            :project_id
        )
        ON CONFLICT (project_id, nm_id) DO UPDATE SET
            vendor_code = EXCLUDED.vendor_code,
            title = EXCLUDED.title,
            brand = EXCLUDED.brand,
            subject_id = EXCLUDED.subject_id,
            subject_name = EXCLUDED.subject_name,
            description = EXCLUDED.description,
            price_u = EXCLUDED.price_u,
            sale_price_u = EXCLUDED.sale_price_u,
            rating = EXCLUDED.rating,
            feedbacks = EXCLUDED.feedbacks,
            sizes = EXCLUDED.sizes,
            colors = EXCLUDED.colors,
            pics = EXCLUDED.pics,
            dimensions = EXCLUDED.dimensions,
            characteristics = EXCLUDED.characteristics,
            created_at_api = EXCLUDED.created_at_api,
            need_kiz = EXCLUDED.need_kiz,
            raw = EXCLUDED.raw,
            project_id = EXCLUDED.project_id,
            updated_at = now();
        """
    )

    total_inserted = 0
    total_updated = 0

    # Add project_id to all rows
    for row in rows:
        row["project_id"] = project_id

    with engine.begin() as conn:
        for batch in _chunked(rows, 200):
            # executemany with list[dict] parameters
            result = conn.execute(insert_sql, batch)
            # Simple approximation: assume half inserted, half updated
            # In real scenario, you'd need more sophisticated tracking
            batch_size = len(batch)
            estimated_inserted = batch_size // 2
            estimated_updated = batch_size - estimated_inserted
            total_inserted += estimated_inserted
            total_updated += estimated_updated

    print(
        f"upsert_products: processed={len(rows)} inserted={total_inserted} updated={total_updated}"
    )

    return {"inserted": total_inserted, "updated": total_updated}


def get_chrt_ids(project_id: int, limit: Optional[int] = None) -> List[int]:
    """Return unique chrtIds (WB size IDs) from products.

    chrtId обычно хранится в массиве sizes либо в raw->'sizes', например:
    raw->'sizes' = [
      {"skus": ["..."], "chrtID": 827988305, ...},
      ...
    ]

    Args:
        limit: Optional maximum number of chrtIds to return.

    Returns:
        List of unique chrtIds as integers. Empty list if данных нет.
    """
    # Извлекаем chrtID из sizes или raw->'sizes'
    sql = """
        SELECT DISTINCT (elem->>'chrtID')::bigint AS chrt_id
        FROM products
        CROSS JOIN LATERAL jsonb_array_elements(
            COALESCE(sizes, raw->'sizes')
        ) AS elem
        WHERE elem ? 'chrtID'
          AND (elem->>'chrtID') ~ '^[0-9]+'
          AND products.project_id = :project_id
    """

    params: Dict[str, Any] = {"project_id": int(project_id)}
    if limit is not None and limit > 0:
        sql += " LIMIT :limit"
        params["limit"] = limit

    stmt = text(sql)

    with engine.connect() as conn:
        result = conn.execute(stmt, params).mappings().all()
        chrt_ids = [int(row["chrt_id"]) for row in result if row.get("chrt_id") is not None]

    print(f"get_chrt_ids: returned {len(chrt_ids)} unique chrtIds")
    return chrt_ids


def search_project_products_lookup(
    project_id: int,
    query: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Lookup project products by nm_id or vendor_code for UI autocomplete."""
    q = (query or "").strip()
    if not q:
        return []

    try:
        q_num = int(q)
    except (ValueError, TypeError):
        q_num = None

    sql = text("""
        SELECT
            p.nm_id,
            p.vendor_code,
            p.title,
            p.subject_name AS wb_category
        FROM products p
        WHERE p.project_id = :project_id
          AND (
            p.vendor_code ILIKE :q_like
            OR p.nm_id::text ILIKE :q_like
          )
        ORDER BY
            CASE
                WHEN p.vendor_code ILIKE :q_exact THEN 0
                WHEN :q_num IS NOT NULL AND p.nm_id = :q_num THEN 0
                WHEN p.vendor_code ILIKE :q_prefix THEN 1
                WHEN p.nm_id::text LIKE :q_prefix THEN 1
                ELSE 2
            END,
            p.vendor_code NULLS LAST,
            p.nm_id
        LIMIT :limit
    """)

    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {
                "project_id": project_id,
                "q_num": q_num,
                "q_like": f"%{q}%",
                "q_exact": q,
                "q_prefix": f"{q}%",
                "limit": max(1, min(int(limit), 20)),
            },
        ).mappings().all()

    return [
        {
            "nm_id": int(row["nm_id"]),
            "vendor_code": row.get("vendor_code"),
            "title": row.get("title"),
            "wb_category": row.get("wb_category"),
        }
        for row in rows
        if row.get("nm_id") is not None
    ]


if __name__ == "__main__":
    ensure_schema()
    print("products schema ready")


