"""Marketplace-neutral product identity lookups.

Marketplace item IDs remain external identifiers.  Callers that need a stable
internal reference should resolve them to ``marketplace_products.id`` within a
project and marketplace connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db import engine


# Transitional WB projection used while fact tables still carry ``nm_id``.
# Canonical rows win; legacy-only rows remain visible until every ingest and
# consumer has moved to marketplace_product_id.
WB_PRODUCT_SOURCE_CTES = """
wb_connection AS (
    SELECT
        CASE WHEN COUNT(*) = 1 THEN MIN(pm.id) ELSE NULL END AS id
    FROM project_marketplaces pm
    JOIN marketplaces m ON m.id = pm.marketplace_id
    WHERE pm.project_id = :project_id
      AND m.code = 'wildberries'
),
marketplace_product_source AS (
    SELECT
        mp.id AS marketplace_product_id,
        mp.project_id,
        mp.marketplace_item_id::bigint AS nm_id,
        COALESCE(mp.marketplace_sku, p.vendor_code) AS vendor_code,
        COALESCE(
            p.vendor_code_norm,
            NULLIF(regexp_replace(trim(both '/' from mp.marketplace_sku), '^.*/', ''), '')
        ) AS vendor_code_norm,
        COALESCE(mp.title, p.title) AS title,
        COALESCE(
            p.subject_id,
            CASE
                WHEN mp.attributes->>'subject_id' ~ '^[0-9]+$'
                    THEN (mp.attributes->>'subject_id')::integer
                ELSE NULL
            END
        ) AS subject_id,
        COALESCE(p.subject_name, mp.attributes->>'subject_name') AS subject_name,
        p.brand,
        p.sizes,
        p.pics,
        p.raw,
        mp.updated_at AS product_updated_at
    FROM marketplace_products mp
    JOIN wb_connection wb ON wb.id = mp.project_marketplace_id
    LEFT JOIN products p
      ON p.project_id = mp.project_id
     AND p.nm_id::text = mp.marketplace_item_id
    WHERE mp.project_id = :project_id
      AND mp.marketplace_item_id ~ '^[0-9]+$'
),
legacy_product_fallback AS (
    SELECT
        NULL::bigint AS marketplace_product_id,
        p.project_id,
        p.nm_id,
        p.vendor_code,
        p.vendor_code_norm,
        p.title,
        p.subject_id,
        p.subject_name,
        p.brand,
        p.sizes,
        p.pics,
        p.raw,
        p.updated_at AS product_updated_at
    FROM products p
    WHERE p.project_id = :project_id
      AND NOT EXISTS (
          SELECT 1
          FROM marketplace_product_source canonical
          WHERE canonical.project_id = p.project_id
            AND canonical.nm_id = p.nm_id
      )
),
product_source AS (
    SELECT * FROM marketplace_product_source
    UNION ALL
    SELECT * FROM legacy_product_fallback
)
"""


class MarketplaceProductIdentityConflictError(RuntimeError):
    """Raised when an external identifier is ambiguous inside one project."""


@dataclass(frozen=True)
class MarketplaceProductIdentity:
    marketplace_product_id: int
    project_id: int
    project_marketplace_id: int
    marketplace_code: str
    marketplace_item_id: str
    marketplace_sku: Optional[str]


def _normalize_required(value: object, *, field: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{field} must not be blank")
    return normalized


def resolve_marketplace_product(
    *,
    project_id: int,
    marketplace_code: str,
    marketplace_item_id: object,
    connection: Optional[Connection] = None,
) -> Optional[MarketplaceProductIdentity]:
    """Resolve an external marketplace ID to the internal product identity.

    The lookup is project-scoped and does not depend on an uploaded internal
    catalog.  At most one result is valid; ambiguous marketplace connections
    fail explicitly instead of selecting an arbitrary product.
    """
    normalized_code = _normalize_required(marketplace_code, field="marketplace_code").lower()
    normalized_item_id = _normalize_required(marketplace_item_id, field="marketplace_item_id")
    statement = text(
        """
        SELECT
            mp.id AS marketplace_product_id,
            mp.project_id,
            mp.project_marketplace_id,
            m.code AS marketplace_code,
            mp.marketplace_item_id,
            mp.marketplace_sku
        FROM marketplace_products mp
        JOIN project_marketplaces pm
          ON pm.id = mp.project_marketplace_id
         AND pm.project_id = mp.project_id
        JOIN marketplaces m ON m.id = pm.marketplace_id
        WHERE mp.project_id = :project_id
          AND m.code = :marketplace_code
          AND mp.marketplace_item_id = :marketplace_item_id
        ORDER BY mp.id
        LIMIT 2
        """
    )
    params = {
        "project_id": int(project_id),
        "marketplace_code": normalized_code,
        "marketplace_item_id": normalized_item_id,
    }

    def _resolve(conn: Connection) -> Optional[MarketplaceProductIdentity]:
        rows = conn.execute(statement, params).mappings().all()
        if not rows:
            return None
        if len(rows) > 1:
            raise MarketplaceProductIdentityConflictError(
                "Marketplace product identity is ambiguous for "
                f"project_id={int(project_id)}, marketplace={normalized_code!r}, "
                f"marketplace_item_id={normalized_item_id!r}"
            )
        row = rows[0]
        return MarketplaceProductIdentity(
            marketplace_product_id=int(row["marketplace_product_id"]),
            project_id=int(row["project_id"]),
            project_marketplace_id=int(row["project_marketplace_id"]),
            marketplace_code=str(row["marketplace_code"]),
            marketplace_item_id=str(row["marketplace_item_id"]),
            marketplace_sku=str(row["marketplace_sku"]) if row["marketplace_sku"] is not None else None,
        )

    if connection is not None:
        return _resolve(connection)
    with engine.connect() as conn:
        return _resolve(conn)


def resolve_marketplace_product_id(
    *,
    project_id: int,
    marketplace_code: str,
    marketplace_item_id: object,
    connection: Optional[Connection] = None,
) -> Optional[int]:
    identity = resolve_marketplace_product(
        project_id=project_id,
        marketplace_code=marketplace_code,
        marketplace_item_id=marketplace_item_id,
        connection=connection,
    )
    return identity.marketplace_product_id if identity is not None else None


def resolve_marketplace_product_ids(
    *,
    project_id: int,
    marketplace_code: str,
    marketplace_item_ids: Iterable[object],
    connection: Optional[Connection] = None,
) -> dict[str, int]:
    """Resolve multiple external IDs in one query, preserving missing IDs."""
    normalized_code = _normalize_required(marketplace_code, field="marketplace_code").lower()
    normalized_item_ids = list(
        dict.fromkeys(
            _normalize_required(value, field="marketplace_item_id")
            for value in marketplace_item_ids
            if value is not None and str(value).strip()
        )
    )
    if not normalized_item_ids:
        return {}
    statement = text(
        """
        SELECT mp.id AS marketplace_product_id, mp.marketplace_item_id
        FROM marketplace_products mp
        JOIN project_marketplaces pm
          ON pm.id = mp.project_marketplace_id
         AND pm.project_id = mp.project_id
        JOIN marketplaces m ON m.id = pm.marketplace_id
        WHERE mp.project_id = :project_id
          AND m.code = :marketplace_code
          AND mp.marketplace_item_id = ANY(:marketplace_item_ids)
        ORDER BY mp.marketplace_item_id, mp.id
        """
    )
    params = {
        "project_id": int(project_id),
        "marketplace_code": normalized_code,
        "marketplace_item_ids": normalized_item_ids,
    }

    def _resolve(conn: Connection) -> dict[str, int]:
        rows = conn.execute(statement, params).mappings().all()
        resolved: dict[str, int] = {}
        for row in rows:
            item_id = str(row["marketplace_item_id"])
            product_id = int(row["marketplace_product_id"])
            existing = resolved.get(item_id)
            if existing is not None and existing != product_id:
                raise MarketplaceProductIdentityConflictError(
                    "Marketplace product identity is ambiguous for "
                    f"project_id={int(project_id)}, marketplace={normalized_code!r}, "
                    f"marketplace_item_id={item_id!r}"
                )
            resolved[item_id] = product_id
        return resolved

    if connection is not None:
        return _resolve(connection)
    with engine.connect() as conn:
        return _resolve(conn)
