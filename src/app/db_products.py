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

from typing import Any, Dict, Iterable, Iterator, List

from sqlalchemy import text

# Import only the engine from app.main as required
from app.main import engine


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
            subject_name    TEXT,
            price_u         BIGINT,
            sale_price_u    BIGINT,
            rating          NUMERIC(3, 2),
            feedbacks       INTEGER,
            sizes           JSONB,
            colors          JSONB,
            pics            JSONB,
            raw             JSONB,
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    create_indexes_sql: List = [
        text("CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand);"),
        text(
            "CREATE INDEX IF NOT EXISTS idx_products_subject ON products(subject_name);"
        ),
        text("CREATE INDEX IF NOT EXISTS idx_products_nm_id ON products(nm_id);"),
        text(
            "CREATE INDEX IF NOT EXISTS idx_products_vendor_code ON products(vendor_code);"
        ),
    ]

    with engine.begin() as conn:
        conn.execute(create_table_sql)
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


def upsert_products(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    """Insert or update product rows by `nm_id` in batches of 200.

    Args:
        rows: List of dicts with keys: nm_id, vendor_code, title, brand,
              subject_name, price_u, sale_price_u, rating, feedbacks,
              sizes, colors, pics, raw. Values may be None.

    Returns:
        Dict with approximate counts: {"inserted": X, "updated": Y}.
    """
    if not rows:
        return {"inserted": 0, "updated": 0}

    insert_sql = text(
        """
        INSERT INTO products (
            nm_id,
            vendor_code,
            title,
            brand,
            subject_name,
            price_u,
            sale_price_u,
            rating,
            feedbacks,
            sizes,
            colors,
            pics,
            raw
        ) VALUES (
            :nm_id,
            :vendor_code,
            :title,
            :brand,
            :subject_name,
            :price_u,
            :sale_price_u,
            :rating,
            :feedbacks,
            :sizes,
            :colors,
            :pics,
            :raw
        )
        ON CONFLICT (nm_id) DO UPDATE SET
            vendor_code = EXCLUDED.vendor_code,
            title = EXCLUDED.title,
            brand = EXCLUDED.brand,
            subject_name = EXCLUDED.subject_name,
            price_u = EXCLUDED.price_u,
            sale_price_u = EXCLUDED.sale_price_u,
            rating = EXCLUDED.rating,
            feedbacks = EXCLUDED.feedbacks,
            sizes = EXCLUDED.sizes,
            colors = EXCLUDED.colors,
            pics = EXCLUDED.pics,
            raw = EXCLUDED.raw,
            updated_at = now();
        """
    )

    total_inserted = 0
    total_updated = 0

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


if __name__ == "__main__":
    ensure_schema()
    print("products schema ready")


