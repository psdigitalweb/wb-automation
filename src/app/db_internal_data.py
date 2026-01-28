"""Database helpers for project-scoped Internal Data.

This module encapsulates CRUD for:
- internal_data_settings
- internal_data_snapshots
- internal_products and related tables
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
try:
    from psycopg2.errors import UniqueViolation
except ImportError:
    # Fallback: use string comparison for error codes
    UniqueViolation = None

from app.db import engine


def _serialize_jsonb(value: Any) -> Optional[str]:
    """Serialize a value to JSON string for JSONB column.
    
    Args:
        value: Can be None, dict, list, str, or other types
        
    Returns:
        JSON string or None
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, str):
        # Assume it's already JSON string
        return value
    # Fallback: wrap in dict
    try:
        return json.dumps({"value": str(value)}, ensure_ascii=False)
    except Exception:
        return None


def get_internal_data_settings(project_id: int) -> Optional[Dict[str, Any]]:
    """Return internal_data_settings row for project or None."""
    sql = text(
        """
        SELECT
            id,
            project_id,
            source_mode,
            source_url,
            file_storage_key,
            file_original_name,
            file_format,
            is_enabled,
            last_sync_at,
            last_sync_status,
            last_sync_error,
            last_test_at,
            last_test_status,
            mapping_json,
            created_at,
            updated_at
        FROM internal_data_settings
        WHERE project_id = :project_id
        """
    )
    with engine.connect() as conn:
        result = conn.execute(sql, {"project_id": project_id})
        row = result.fetchone()
        if not row:
            return None
        return dict(row._mapping)


def upsert_internal_data_settings(
    project_id: int,
    *,
    source_mode: Optional[str] = None,
    source_url: Optional[str] = None,
    file_storage_key: Optional[str] = None,
    file_original_name: Optional[str] = None,
    file_format: Optional[str] = None,
    is_enabled: Optional[bool] = None,
    mapping_json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Insert or update internal_data_settings for a project.

    Only provided fields are updated; others are preserved.
    """
    import json as json_module

    # Serialize mapping_json to JSON string for JSONB column
    mapping_json_str = None
    if mapping_json is not None:
        mapping_json_str = json_module.dumps(mapping_json)
    elif mapping_json is None:
        # For INSERT, use empty dict. For UPDATE, keep existing (None means don't update)
        mapping_json_str = "{}"

    sql = text(
        """
        INSERT INTO internal_data_settings (
            project_id,
            source_mode,
            source_url,
            file_storage_key,
            file_original_name,
            file_format,
            is_enabled,
            mapping_json
        )
        VALUES (
            :project_id,
            :source_mode,
            :source_url,
            :file_storage_key,
            :file_original_name,
            :file_format,
            COALESCE(:is_enabled, false),
            CAST(:mapping_json AS jsonb)
        )
        ON CONFLICT (project_id) DO UPDATE SET
            source_mode = COALESCE(:source_mode_param, internal_data_settings.source_mode),
            source_url = COALESCE(:source_url_param, internal_data_settings.source_url),
            file_storage_key = COALESCE(:file_storage_key_param, internal_data_settings.file_storage_key),
            file_original_name = COALESCE(:file_original_name_param, internal_data_settings.file_original_name),
            file_format = COALESCE(:file_format_param, internal_data_settings.file_format),
            is_enabled = COALESCE(:is_enabled_param, internal_data_settings.is_enabled),
            mapping_json = COALESCE(CAST(:mapping_json_param AS jsonb), internal_data_settings.mapping_json),
            updated_at = now()
        RETURNING
            id,
            project_id,
            source_mode,
            source_url,
            file_storage_key,
            file_original_name,
            file_format,
            is_enabled,
            last_sync_at,
            last_sync_status,
            last_sync_error,
            last_test_at,
            last_test_status,
            mapping_json,
            created_at,
            updated_at
        """
    )
    with engine.begin() as conn:
        result = conn.execute(
            sql,
            {
                "project_id": project_id,
                "source_mode": source_mode,
                "source_url": source_url,
                "file_storage_key": file_storage_key,
                "file_original_name": file_original_name,
                "file_format": file_format,
                "is_enabled": is_enabled,
                "mapping_json": mapping_json_str,
                # Separate params for UPDATE (NULL means don't update)
                "source_mode_param": source_mode,
                "source_url_param": source_url,
                "file_storage_key_param": file_storage_key,
                "file_original_name_param": file_original_name,
                "file_format_param": file_format,
                "is_enabled_param": is_enabled,
                "mapping_json_param": mapping_json_str if mapping_json is not None else None,
            },
        )
        row = result.fetchone()
        return dict(row._mapping)


def update_sync_result(
    settings_id: int,
    *,
    status: str,
    error: Optional[str],
) -> None:
    sql = text(
        """
        UPDATE internal_data_settings
        SET
            last_sync_at = now(),
            last_sync_status = :status,
            last_sync_error = :error,
            updated_at = now()
        WHERE id = :settings_id
        """
    )
    with engine.begin() as conn:
        conn.execute(sql, {"settings_id": settings_id, "status": status, "error": error})


def update_test_result(
    settings_id: int,
    *,
    status: str,
) -> None:
    sql = text(
        """
        UPDATE internal_data_settings
        SET
            last_test_at = now(),
            last_test_status = :status,
            updated_at = now()
        WHERE id = :settings_id
        """
    )
    with engine.begin() as conn:
        conn.execute(sql, {"settings_id": settings_id, "status": status})


def _get_next_snapshot_version(conn, project_id: int) -> int:
    """Compute next snapshot version with an advisory lock to avoid races."""
    # Take transaction-scoped advisory lock on project_id namespace.
    conn.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": project_id},
    )
    row = conn.execute(
        text(
            """
            SELECT COALESCE(MAX(version), 0) AS max_version
            FROM internal_data_snapshots
            WHERE project_id = :project_id
            """
        ),
        {"project_id": project_id},
    ).fetchone()
    max_version = int(row._mapping["max_version"]) if row and row._mapping["max_version"] is not None else 0
    return max_version + 1


def create_snapshot_with_rows(
    project_id: int,
    settings_row: Dict[str, Any],
    *,
    source_mode: str,
    source_url: Optional[str],
    file_storage_key: Optional[str],
    file_original_name: Optional[str],
    file_format: Optional[str],
    rows: Iterable[Dict[str, Any]],
    rows_total: Optional[int] = None,
    rows_imported: Optional[int] = None,
    rows_failed: Optional[int] = None,
    status: str = "success",
    error_summary: Optional[str] = None,
    row_errors: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[Dict[str, Any], int]:
    """Create snapshot and persist rows in a single transaction.

    rows must already be normalized dictionaries with keys:
      internal_sku, name, lifecycle_status, attributes,
      identifiers (list[dict]), price (dict), cost (dict).
    
    Args:
        rows_total: Total number of rows processed
        rows_imported: Number of successfully imported rows
        rows_failed: Number of failed rows
        status: 'success', 'partial', or 'error'
        error_summary: Brief error summary (for status='error')
    """
    with engine.begin() as conn:
        version = _get_next_snapshot_version(conn, project_id)
        
        # Calculate row_count from rows_imported if not provided
        row_count = rows_imported if rows_imported is not None else 0

        result = conn.execute(
            text(
                """
                INSERT INTO internal_data_snapshots (
                    project_id,
                    settings_id,
                    version,
                    source_mode,
                    source_url,
                    file_storage_key,
                    file_original_name,
                    file_format,
                    row_count,
                    rows_total,
                    rows_imported,
                    rows_failed,
                    status,
                    error
                )
                VALUES (
                    :project_id,
                    :settings_id,
                    :version,
                    :source_mode,
                    :source_url,
                    :file_storage_key,
                    :file_original_name,
                    :file_format,
                    :row_count,
                    :rows_total,
                    :rows_imported,
                    :rows_failed,
                    :status,
                    :error
                )
                RETURNING *
                """
            ),
            {
                "project_id": project_id,
                "settings_id": settings_row["id"],
                "version": version,
                "source_mode": source_mode,
                "source_url": source_url,
                "file_storage_key": file_storage_key,
                "file_original_name": file_original_name,
                "file_format": file_format,
                "row_count": row_count,
                "rows_total": rows_total,
                "rows_imported": rows_imported,
                "rows_failed": rows_failed,
                "status": status,
                "error": error_summary,
            },
        )
        snapshot_row = result.fetchone()
        snapshot = dict(snapshot_row._mapping)
        snapshot_id = snapshot["id"]

        internal_products_rows: List[Dict[str, Any]] = []
        identifiers_rows: List[Dict[str, Any]] = []
        prices_rows: List[Dict[str, Any]] = []
        costs_rows: List[Dict[str, Any]] = []

        for row in rows:
            internal_sku = row.get("internal_sku")
            if not internal_sku:
                continue
            
            internal_products_rows.append(
                {
                    "project_id": project_id,
                    "snapshot_id": snapshot_id,
                    "internal_sku": internal_sku,
                    "name": row.get("name"),
                    "lifecycle_status": row.get("lifecycle_status"),
                    "attributes": _serialize_jsonb(row.get("attributes")),
                }
            )

        if internal_products_rows:
            # Check existing SKUs in this snapshot to count updates
            skus_to_insert = {row["internal_sku"] for row in internal_products_rows}
            existing_skus = set()
            rows_updated_count = 0
            if skus_to_insert:
                # Use ANY() with array parameter (PostgreSQL-specific, SQLAlchemy handles conversion)
                skus_list = list(skus_to_insert)
                existing_result = conn.execute(
                    text(
                        """
                        SELECT internal_sku
                        FROM internal_products
                        WHERE project_id = :project_id 
                          AND snapshot_id = :snapshot_id
                          AND internal_sku = ANY(:skus)
                        """
                    ),
                    {
                        "project_id": project_id,
                        "snapshot_id": snapshot_id,
                        "skus": skus_list,  # Pass as list, psycopg2 will convert to array
                    },
                )
                # Fetch all results immediately before the result object is closed
                existing_skus = {row._mapping["internal_sku"] for row in existing_result.fetchall()}
                rows_updated_count = len(existing_skus)
            
            # Use UPSERT to handle duplicates (update existing records)
            # Execute UPSERT without RETURNING (executemany + RETURNING has issues with result closure)
            insert_sql = text(
                """
                INSERT INTO internal_products (
                    project_id,
                    snapshot_id,
                    internal_sku,
                    name,
                    lifecycle_status,
                    attributes
                )
                VALUES (
                    :project_id,
                    :snapshot_id,
                    :internal_sku,
                    :name,
                    :lifecycle_status,
                    CAST(:attributes AS jsonb)
                )
                ON CONFLICT (project_id, snapshot_id, internal_sku) 
                DO UPDATE SET
                    name = EXCLUDED.name,
                    lifecycle_status = EXCLUDED.lifecycle_status,
                    attributes = EXCLUDED.attributes
                """
            )
            
            # Execute bulk UPSERT in batches
            batch_size = 500
            for i in range(0, len(internal_products_rows), batch_size):
                batch = internal_products_rows[i:i + batch_size]
                conn.execute(insert_sql, batch)
            
            # After UPSERT, fetch all IDs by querying the inserted/updated rows
            skus_list = [row["internal_sku"] for row in internal_products_rows]
            if skus_list:
                id_result = conn.execute(
                    text(
                        """
                        SELECT id, internal_sku
                        FROM internal_products
                        WHERE project_id = :project_id 
                          AND snapshot_id = :snapshot_id
                          AND internal_sku = ANY(:skus)
                        """
                    ),
                    {
                        "project_id": project_id,
                        "snapshot_id": snapshot_id,
                        "skus": skus_list,
                    },
                )
                id_map = {row._mapping["internal_sku"]: row._mapping["id"] for row in id_result.fetchall()}
            else:
                id_map = {}
        else:
            id_map = {}

        for row in rows:
            internal_sku = row.get("internal_sku")
            internal_product_id = id_map.get(internal_sku)
            if not internal_product_id:
                continue

            identifiers = row.get("identifiers") or []
            for ident in identifiers:
                identifiers_rows.append(
                    {
                        "project_id": project_id,
                        "snapshot_id": snapshot_id,
                        "internal_product_id": internal_product_id,
                        "marketplace_code": ident.get("marketplace_code") or "",
                        "marketplace_sku": ident.get("marketplace_sku"),
                        "marketplace_item_id": ident.get("marketplace_item_id"),
                        "extra_identifiers": _serialize_jsonb(ident.get("extra_identifiers")),
                    }
                )

            price = row.get("price") or {}
            if price:
                prices_rows.append(
                    {
                        "project_id": project_id,
                        "snapshot_id": snapshot_id,
                        "internal_product_id": internal_product_id,
                        "currency": price.get("currency"),
                        "rrp": price.get("rrp"),
                        "rrp_promo": price.get("rrp_promo"),
                        "extra": _serialize_jsonb(price.get("extra")),
                    }
                )

            cost = row.get("cost") or {}
            if cost:
                costs_rows.append(
                    {
                        "project_id": project_id,
                        "snapshot_id": snapshot_id,
                        "internal_product_id": internal_product_id,
                        "currency": cost.get("currency"),
                        "cost": cost.get("cost"),
                        "extra": _serialize_jsonb(cost.get("extra")),
                    }
                )

        if identifiers_rows:
            # For identifiers, we need to handle multiple unique constraints
            # Main constraint: (project_id, marketplace_code)
            # Partial indexes: (snapshot_id, marketplace_code, marketplace_item_id) WHERE item_id IS NOT NULL
            #                   (snapshot_id, marketplace_code, marketplace_sku) WHERE sku IS NOT NULL
            # We'll use ON CONFLICT on the main constraint
            conn.execute(
                text(
                    """
                    INSERT INTO internal_product_identifiers (
                        project_id,
                        snapshot_id,
                        internal_product_id,
                        marketplace_code,
                        marketplace_sku,
                        marketplace_item_id,
                        extra_identifiers
                    )
                    VALUES (
                        :project_id,
                        :snapshot_id,
                        :internal_product_id,
                        :marketplace_code,
                        :marketplace_sku,
                        :marketplace_item_id,
                        CAST(:extra_identifiers AS jsonb)
                    )
                    ON CONFLICT (project_id, marketplace_code)
                    DO UPDATE SET
                        snapshot_id = EXCLUDED.snapshot_id,
                        internal_product_id = EXCLUDED.internal_product_id,
                        marketplace_sku = EXCLUDED.marketplace_sku,
                        marketplace_item_id = EXCLUDED.marketplace_item_id,
                        extra_identifiers = EXCLUDED.extra_identifiers
                    """
                ),
                identifiers_rows,
            )

        if prices_rows:
            conn.execute(
                text(
                    """
                    INSERT INTO internal_product_prices (
                        project_id,
                        snapshot_id,
                        internal_product_id,
                        currency,
                        rrp,
                        rrp_promo,
                        extra
                    )
                    VALUES (
                        :project_id,
                        :snapshot_id,
                        :internal_product_id,
                        :currency,
                        :rrp,
                        :rrp_promo,
                        CAST(:extra AS jsonb)
                    )
                    ON CONFLICT (snapshot_id, internal_product_id)
                    DO UPDATE SET
                        project_id = EXCLUDED.project_id,
                        currency = EXCLUDED.currency,
                        rrp = EXCLUDED.rrp,
                        rrp_promo = EXCLUDED.rrp_promo,
                        extra = EXCLUDED.extra
                    """
                ),
                prices_rows,
            )

        if costs_rows:
            conn.execute(
                text(
                    """
                    INSERT INTO internal_product_costs (
                        project_id,
                        snapshot_id,
                        internal_product_id,
                        currency,
                        cost,
                        extra
                    )
                    VALUES (
                        :project_id,
                        :snapshot_id,
                        :internal_product_id,
                        :currency,
                        :cost,
                        CAST(:extra AS jsonb)
                    )
                    ON CONFLICT (snapshot_id, internal_product_id)
                    DO UPDATE SET
                        project_id = EXCLUDED.project_id,
                        currency = EXCLUDED.currency,
                        cost = EXCLUDED.cost,
                        extra = EXCLUDED.extra
                    """
                ),
                costs_rows,
            )

        # Save row errors if provided
        if row_errors:
            prepared_errors = [
                {
                    "project_id": project_id,
                    "snapshot_id": snapshot_id,
                    "row_index": err["row_index"],
                    "source_key": err.get("source_key"),
                    "raw_row": err.get("raw_row"),
                    "error_code": err.get("error_code"),
                    "message": err["message"],
                    "transforms": err.get("transforms"),
                    "trace": err.get("trace"),
                }
                for err in row_errors
            ]
            bulk_insert_internal_data_row_errors(conn, prepared_errors)
        
        # row_count should be rows_imported if provided, otherwise len(internal_products_rows)
        final_row_count = rows_imported if rows_imported is not None else len(internal_products_rows)
        if final_row_count != row_count:
            conn.execute(
                text(
                    """
                    UPDATE internal_data_snapshots
                    SET row_count = :row_count
                    WHERE id = :snapshot_id
                    """
                ),
                {"row_count": final_row_count, "snapshot_id": snapshot_id},
            )
            snapshot["row_count"] = final_row_count
        
        snapshot["version"] = version
        snapshot["rows_updated"] = rows_updated_count if internal_products_rows else 0
        return snapshot, final_row_count


def bulk_insert_internal_data_row_errors(
    conn,
    errors: List[Dict[str, Any]],
) -> int:
    """Bulk insert row errors into internal_data_row_errors table.
    
    Args:
        conn: Database connection (must be in a transaction)
        errors: List of error dicts with keys:
            project_id, snapshot_id, row_index, source_key, raw_row,
            error_code, message, transforms, trace
    
    Returns:
        Number of inserted rows
    """
    if not errors:
        return 0
    
    # Serialize JSONB fields using helper
    prepared_errors = []
    for err in errors:
        prepared_errors.append({
            "project_id": err["project_id"],
            "snapshot_id": err["snapshot_id"],
            "row_index": err["row_index"],
            "source_key": err.get("source_key"),
            "raw_row": _serialize_jsonb(err.get("raw_row")),
            "error_code": err.get("error_code"),
            "message": err["message"],
            "transforms": _serialize_jsonb(err.get("transforms")),
            "trace": _serialize_jsonb(err.get("trace")),
        })
    
    conn.execute(
        text(
            """
            INSERT INTO internal_data_row_errors (
                project_id,
                snapshot_id,
                row_index,
                source_key,
                raw_row,
                error_code,
                message,
                transforms,
                trace
            )
            VALUES (
                :project_id,
                :snapshot_id,
                :row_index,
                :source_key,
                CAST(:raw_row AS jsonb),
                :error_code,
                :message,
                CAST(:transforms AS jsonb),
                CAST(:trace AS jsonb)
            )
            """
        ),
        prepared_errors,
    )
    
    return len(prepared_errors)


def list_internal_data_row_errors(
    project_id: int,
    snapshot_id: int,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """List row errors for a specific snapshot.
    
    Returns:
        Dict with 'total' (int) and 'items' (list of error dicts)
    """
    sql_count = text(
        """
        SELECT COUNT(*) as total
        FROM internal_data_row_errors
        WHERE project_id = :project_id AND snapshot_id = :snapshot_id
        """
    )
    
    sql_list = text(
        """
        SELECT
            id,
            project_id,
            snapshot_id,
            row_index,
            source_key,
            raw_row,
            error_code,
            message,
            transforms,
            trace,
            created_at
        FROM internal_data_row_errors
        WHERE project_id = :project_id AND snapshot_id = :snapshot_id
        ORDER BY row_index ASC
        LIMIT :limit OFFSET :offset
        """
    )
    
    with engine.connect() as conn:
        result_count = conn.execute(
            sql_count,
            {"project_id": project_id, "snapshot_id": snapshot_id},
        )
        total = result_count.scalar_one()
        
        result_list = conn.execute(
            sql_list,
            {
                "project_id": project_id,
                "snapshot_id": snapshot_id,
                "limit": limit,
                "offset": offset,
            },
        )
        items = []
        for row in result_list:
            item = dict(row._mapping)
            # Convert trace from list of tuples/lists to dict if needed
            if item.get("trace") and isinstance(item["trace"], list):
                # If trace is a list of tuples/lists like [("initial", value), ("transform", value)]
                # or [["initial", value], ["transform", value]]
                # convert it to a dict for Pydantic validation
                trace_list = item["trace"]
                if trace_list:
                    # Check if first element is a tuple or list with 2 elements
                    first_elem = trace_list[0]
                    if isinstance(first_elem, (list, tuple)) and len(first_elem) == 2:
                        # Convert list of [key, value] pairs to dict
                        # trace_list is like [['initial', ''], ['transform', 'value']]
                        item["trace"] = {str(pair[0]): pair[1] for pair in trace_list if len(pair) == 2}
                    else:
                        # If it's not in expected format, convert to dict with index keys
                        item["trace"] = {str(i): v for i, v in enumerate(trace_list)}
                else:
                    item["trace"] = None
            items.append(item)
    
    return {"total": total, "items": items}


def list_internal_products(
    project_id: int,
    snapshot_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    with_stock_only: bool = False,
    include_category: bool = False,
) -> Dict[str, Any]:
    """List internal products for a project.
    
    Args:
        project_id: Project ID
        snapshot_id: Optional snapshot ID. If None, uses latest successful snapshot.
        limit: Maximum number of products to return
        offset: Offset for pagination
        with_stock_only: If True, only return products with stock > 0
        include_category: If True, include internal_category_id in response
        
    Returns:
        Dict with 'total' (int) and 'items' (list of product dicts)
    """
    # If snapshot_id not provided, get latest successful snapshot
    if snapshot_id is None:
        snapshot_sql = text(
            """
            SELECT id
            FROM internal_data_snapshots
            WHERE project_id = :project_id
              AND status IN ('success', 'partial')
            ORDER BY imported_at DESC
            LIMIT 1
            """
        )
        with engine.connect() as conn:
            snapshot_result = conn.execute(snapshot_sql, {"project_id": project_id})
            snapshot_row = snapshot_result.fetchone()
            if not snapshot_row:
                return {"total": 0, "items": []}
            snapshot_id = snapshot_row._mapping["id"]
    
    # Build WHERE clause
    where_clause = "WHERE ip.project_id = :project_id AND ip.snapshot_id = :snapshot_id"
    if with_stock_only:
        where_clause += " AND (ip.attributes->>'stock') IS NOT NULL AND (ip.attributes->>'stock')::numeric > 0"
    
    # Count total
    count_sql = text(
        f"""
        SELECT COUNT(*) as total
        FROM internal_products ip
        {where_clause}
        """
    )
    
    # Get products with prices (and optionally category)
    select_fields = [
        "ip.id",
        "ip.internal_sku",
        "ip.name",
        "ip.lifecycle_status",
        "ip.attributes",
        "ipp.rrp as price_rrp",
        "ipp.currency as price_currency",
        "ic.cost",
        "ic.currency as cost_currency",
    ]
    if include_category:
        select_fields.append("ip.internal_category_id")
    
    list_sql = text(
        f"""
        SELECT
            {', '.join(select_fields)}
        FROM internal_products ip
        LEFT JOIN internal_product_prices ipp ON ipp.internal_product_id = ip.id AND ipp.snapshot_id = ip.snapshot_id
        LEFT JOIN internal_product_costs ic ON ic.internal_product_id = ip.id AND ic.snapshot_id = ip.snapshot_id
        {where_clause}
        ORDER BY ip.internal_sku ASC
        LIMIT :limit OFFSET :offset
        """
    )
    
    with engine.connect() as conn:
        result_count = conn.execute(
            count_sql,
            {"project_id": project_id, "snapshot_id": snapshot_id},
        )
        total = result_count.scalar_one()
        
        result_list = conn.execute(
            list_sql,
            {
                "project_id": project_id,
                "snapshot_id": snapshot_id,
                "limit": limit,
                "offset": offset,
            },
        )
        items = []
        for row in result_list:
            item = dict(row._mapping)
            # Parse attributes JSONB if it's a string
            if item.get("attributes") and isinstance(item["attributes"], str):
                try:
                    item["attributes"] = json.loads(item["attributes"])
                except Exception:
                    item["attributes"] = {}
            items.append(item)
    
    return {"total": total, "items": items}


def create_internal_category(
    project_id: int,
    key: str,
    name: str,
    parent_id: Optional[int] = None,
    meta_json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a new internal category for a project.
    
    Args:
        project_id: Project ID
        key: Unique key for the category within the project
        name: Display name
        parent_id: Optional parent category ID (must exist in same project)
        meta_json: Optional metadata dict
        
    Returns:
        Created category dict
        
    Raises:
        ValueError: If parent_id doesn't exist in project, or key conflicts
    """
    # Validate parent_id if provided
    if parent_id is not None:
        parent_check = text(
            """
            SELECT id FROM internal_categories
            WHERE id = :parent_id AND project_id = :project_id
            """
        )
        with engine.connect() as conn:
            result = conn.execute(
                parent_check,
                {"parent_id": parent_id, "project_id": project_id},
            )
            if result.fetchone() is None:
                raise ValueError("parent_category_not_found")
    
    # Serialize meta_json
    meta_json_str = _serialize_jsonb(meta_json) if meta_json is not None else "{}"
    
    insert_sql = text(
        """
        INSERT INTO internal_categories (
            project_id, key, name, parent_id, meta_json
        ) VALUES (
            :project_id, :key, :name, :parent_id, CAST(:meta_json AS jsonb)
        )
        RETURNING id, project_id, key, name, parent_id, meta_json, created_at, updated_at
        """
    )
    
    try:
        with engine.begin() as conn:
            result = conn.execute(
                insert_sql,
                {
                    "project_id": project_id,
                    "key": key,
                    "name": name,
                    "parent_id": parent_id,
                    "meta_json": meta_json_str,
                },
            )
            row = result.fetchone()
            if not row:
                raise ValueError("category_creation_failed")
            
            item = dict(row._mapping)
            # Parse meta_json if it's a string
            if item.get("meta_json") and isinstance(item["meta_json"], str):
                try:
                    item["meta_json"] = json.loads(item["meta_json"])
                except Exception:
                    item["meta_json"] = {}
            return item
    except IntegrityError as e:
        # Check for unique violation: error code 23505 or isinstance check
        if UniqueViolation and isinstance(e.orig, UniqueViolation):
            raise ValueError("category_key_conflict") from e
        elif hasattr(e.orig, 'pgcode') and e.orig.pgcode == '23505':
            raise ValueError("category_key_conflict") from e
        raise


def get_internal_category(project_id: int, category_id: int) -> Optional[Dict[str, Any]]:
    """Get internal category by ID (project-scoped).
    
    Args:
        project_id: Project ID
        category_id: Category ID
        
    Returns:
        Category dict or None if not found
    """
    sql = text(
        """
        SELECT id, project_id, key, name, parent_id, meta_json, created_at, updated_at
        FROM internal_categories
        WHERE id = :category_id AND project_id = :project_id
        """
    )
    with engine.connect() as conn:
        result = conn.execute(sql, {"category_id": category_id, "project_id": project_id})
        row = result.fetchone()
        if not row:
            return None
        
        item = dict(row._mapping)
        # Parse meta_json if it's a string
        if item.get("meta_json") and isinstance(item["meta_json"], str):
            try:
                item["meta_json"] = json.loads(item["meta_json"])
            except Exception:
                item["meta_json"] = {}
        return item


def get_internal_category_by_key(project_id: int, key: str) -> Optional[Dict[str, Any]]:
    """Get internal category by key (project-scoped).
    
    Args:
        project_id: Project ID
        key: Category key
        
    Returns:
        Category dict or None if not found
    """
    sql = text(
        """
        SELECT id, project_id, key, name, parent_id, meta_json, created_at, updated_at
        FROM internal_categories
        WHERE project_id = :project_id AND key = :key
        """
    )
    with engine.connect() as conn:
        result = conn.execute(sql, {"project_id": project_id, "key": key})
        row = result.fetchone()
        if not row:
            return None
        
        item = dict(row._mapping)
        # Parse meta_json if it's a string
        if item.get("meta_json") and isinstance(item["meta_json"], str):
            try:
                item["meta_json"] = json.loads(item["meta_json"])
            except Exception:
                item["meta_json"] = {}
        return item


def list_internal_categories(
    project_id: int,
    *,
    q: Optional[str] = None,
    parent_id: Any = ...,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """List internal categories for a project.
    
    Args:
        project_id: Project ID
        q: Optional search query (ILIKE on name or key)
        parent_id: Filter by parent_id:
            - Ellipsis (not provided) → no filter (all categories)
            - None (explicit) → only root categories (parent_id IS NULL)
            - int → only children of this category
        limit: Maximum number of categories
        offset: Offset for pagination
        
    Returns:
        Dict with 'total' (int) and 'items' (list of category dicts)
    """
    # Build WHERE clause
    where_parts = ["project_id = :project_id"]
    params = {"project_id": project_id}
    
    if q:
        where_parts.append("(name ILIKE :qpat OR key ILIKE :qpat)")
        params["qpat"] = f"%{q}%"
    
    # Handle parent_id filter
    # If parent_id is Ellipsis (not provided), don't filter
    # If parent_id is None (explicit), filter for root categories
    # If parent_id is an int, filter for children of that category
    if parent_id is not ...:
        if parent_id is None:
            where_parts.append("parent_id IS NULL")
        else:
            where_parts.append("parent_id = :parent_id")
            params["parent_id"] = parent_id
    
    where_clause = " AND ".join(where_parts)
    
    # Count total
    count_sql = text(
        f"""
        SELECT COUNT(*) as total
        FROM internal_categories
        WHERE {where_clause}
        """
    )
    
    # Get categories
    list_sql = text(
        f"""
        SELECT id, project_id, key, name, parent_id, meta_json, created_at, updated_at
        FROM internal_categories
        WHERE {where_clause}
        ORDER BY name ASC
        LIMIT :limit OFFSET :offset
        """
    )
    
    with engine.connect() as conn:
        result_count = conn.execute(count_sql, params)
        total = result_count.scalar_one()
        
        params.update({"limit": limit, "offset": offset})
        result_list = conn.execute(list_sql, params)
        
        items = []
        for row in result_list:
            item = dict(row._mapping)
            # Parse meta_json if it's a string
            if item.get("meta_json") and isinstance(item["meta_json"], str):
                try:
                    item["meta_json"] = json.loads(item["meta_json"])
                except Exception:
                    item["meta_json"] = {}
            items.append(item)
    
    return {"total": total, "items": items}


def update_internal_category(
    project_id: int,
    category_id: int,
    patch: Dict[str, Any],
) -> Dict[str, Any]:
    """Update internal category (project-scoped).
    
    Args:
        project_id: Project ID
        category_id: Category ID
        patch: Dict with fields to update (key, name, parent_id, meta_json)
        
    Returns:
        Updated category dict
        
    Raises:
        ValueError: If category not found, parent_id invalid, or key conflicts
    """
    # Check category exists in project
    check_sql = text(
        """
        SELECT id FROM internal_categories
        WHERE id = :category_id AND project_id = :project_id
        """
    )
    
    with engine.begin() as conn:
        result = conn.execute(check_sql, {"category_id": category_id, "project_id": project_id})
        if result.fetchone() is None:
            raise ValueError("category_not_found")
        
        # Validate parent_id if being updated
        if "parent_id" in patch and patch["parent_id"] is not None:
            parent_id = patch["parent_id"]
            parent_check = text(
                """
                SELECT id FROM internal_categories
                WHERE id = :parent_id AND project_id = :project_id
                """
            )
            result = conn.execute(
                parent_check,
                {"parent_id": parent_id, "project_id": project_id},
            )
            if result.fetchone() is None:
                raise ValueError("parent_category_not_found")
        
        # Build UPDATE SET clause
        set_parts = ["updated_at = now()"]
        params = {"category_id": category_id, "project_id": project_id}
        
        if "key" in patch:
            set_parts.append("key = :key")
            params["key"] = patch["key"]
        
        if "name" in patch:
            set_parts.append("name = :name")
            params["name"] = patch["name"]
        
        if "parent_id" in patch:
            set_parts.append("parent_id = :parent_id")
            params["parent_id"] = patch["parent_id"]
        
        if "meta_json" in patch:
            meta_json_str = _serialize_jsonb(patch["meta_json"])
            set_parts.append("meta_json = CAST(:meta_json AS jsonb)")
            params["meta_json"] = meta_json_str
        
        if len(set_parts) == 1:  # Only updated_at
            # No fields to update, just return existing
            select_sql = text(
                """
                SELECT id, project_id, key, name, parent_id, meta_json, created_at, updated_at
                FROM internal_categories
                WHERE id = :category_id AND project_id = :project_id
                """
            )
            result = conn.execute(select_sql, params)
            row = result.fetchone()
            if not row:
                raise ValueError("category_not_found")
            item = dict(row._mapping)
        else:
            update_sql = text(
                f"""
                UPDATE internal_categories
                SET {', '.join(set_parts)}
                WHERE id = :category_id AND project_id = :project_id
                RETURNING id, project_id, key, name, parent_id, meta_json, created_at, updated_at
                """
            )
            try:
                result = conn.execute(update_sql, params)
                row = result.fetchone()
                if not row:
                    raise ValueError("category_not_found")
                item = dict(row._mapping)
            except IntegrityError as e:
                # Check for unique violation: error code 23505 or isinstance check
                if UniqueViolation and isinstance(e.orig, UniqueViolation):
                    raise ValueError("category_key_conflict") from e
                elif hasattr(e.orig, 'pgcode') and e.orig.pgcode == '23505':
                    raise ValueError("category_key_conflict") from e
                raise
        
        # Parse meta_json if it's a string
        if item.get("meta_json") and isinstance(item["meta_json"], str):
            try:
                item["meta_json"] = json.loads(item["meta_json"])
            except Exception:
                item["meta_json"] = {}
        
        return item


def delete_internal_category(project_id: int, category_id: int) -> None:
    """Delete internal category (project-scoped).
    
    Args:
        project_id: Project ID
        category_id: Category ID
        
    Raises:
        ValueError: If category not found in project
    """
    delete_sql = text(
        """
        DELETE FROM internal_categories
        WHERE id = :category_id AND project_id = :project_id
        """
    )
    
    with engine.begin() as conn:
        result = conn.execute(delete_sql, {"category_id": category_id, "project_id": project_id})
        if result.rowcount == 0:
            raise ValueError("category_not_found")
        # FK ON DELETE SET NULL will automatically clear internal_category_id in products


def set_internal_product_category(
    project_id: int,
    internal_sku: str,
    category_id_or_none: Optional[int],
) -> None:
    """Set category for an internal product by SKU (updates latest snapshot).
    
    Args:
        project_id: Project ID
        internal_sku: Internal SKU
        category_id_or_none: Category ID or None to unset
        
    Raises:
        ValueError: If product not found in latest snapshot
    """
    # Find latest snapshot
    snapshot_sql = text(
        """
        SELECT id
        FROM internal_data_snapshots
        WHERE project_id = :project_id
          AND status IN ('success', 'partial')
        ORDER BY imported_at DESC
        LIMIT 1
        """
    )
    
    with engine.begin() as conn:
        snapshot_result = conn.execute(snapshot_sql, {"project_id": project_id})
        snapshot_row = snapshot_result.fetchone()
        if not snapshot_row:
            raise ValueError("product_not_found")
        snapshot_id = snapshot_row._mapping["id"]
        
        # Update product category
        update_sql = text(
            """
            UPDATE internal_products
            SET internal_category_id = :category_id
            WHERE project_id = :project_id
              AND snapshot_id = :snapshot_id
              AND internal_sku = :internal_sku
            """
        )
        result = conn.execute(
            update_sql,
            {
                "project_id": project_id,
                "snapshot_id": snapshot_id,
                "internal_sku": internal_sku,
                "category_id": category_id_or_none,
            },
        )
        if result.rowcount == 0:
            raise ValueError("product_not_found")


def upsert_internal_categories_tree(
    project_id: int,
    categories: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Bulk upsert internal categories tree with parent relationships.
    
    Two-pass approach:
    1. Upsert all categories (get key->id mapping)
    2. Update parent_id based on parent_key
    
    Args:
        project_id: Project ID
        categories: List of {key: str, name: str, parent_key: Optional[str], meta_json: dict}
        
    Returns:
        Dict with:
        - created: int (new categories)
        - updated: int (existing categories updated)
        - key_to_id: Dict[str, int] (mapping category key -> category id)
    """
    if not categories:
        return {"created": 0, "updated": 0, "key_to_id": {}}
    
    key_to_id: Dict[str, int] = {}
    created = 0
    updated = 0
    
    with engine.begin() as conn:
        # Pass 1: Upsert all categories
        for cat in categories:
            key = cat.get("key", "").strip()
            if not key:
                continue
            
            name = cat.get("name", "").strip() or key
            meta_json_str = _serialize_jsonb(cat.get("meta_json") or {})
            
            upsert_sql = text(
                """
                INSERT INTO internal_categories (project_id, key, name, meta_json, created_at, updated_at)
                VALUES (:project_id, :key, :name, CAST(:meta_json AS jsonb), now(), now())
                ON CONFLICT (project_id, key)
                DO UPDATE SET
                  name = EXCLUDED.name,
                  meta_json = EXCLUDED.meta_json,
                  updated_at = now()
                RETURNING id
                """
            )
            
            result = conn.execute(
                upsert_sql,
                {
                    "project_id": project_id,
                    "key": key,
                    "name": name,
                    "meta_json": meta_json_str,
                },
            )
            row = result.fetchone()
            if row:
                cat_id = row._mapping["id"]
                key_to_id[key] = cat_id
                
                # Check if it was created or updated
                check_sql = text(
                    """
                    SELECT created_at, updated_at
                    FROM internal_categories
                    WHERE id = :id
                    """
                )
                check_result = conn.execute(check_sql, {"id": cat_id})
                check_row = check_result.fetchone()
                if check_row:
                    created_at = check_row._mapping["created_at"]
                    updated_at = check_row._mapping["updated_at"]
                    # If created_at == updated_at (within 1 second), it's likely new
                    if abs((updated_at - created_at).total_seconds()) < 1:
                        created += 1
                    else:
                        updated += 1
        
        # Pass 2: Update parent_id
        for cat in categories:
            key = cat.get("key", "").strip()
            if not key or key not in key_to_id:
                continue
            
            parent_key = cat.get("parent_key")
            if not parent_key:
                # Set parent_id to NULL if no parent_key
                update_sql = text(
                    """
                    UPDATE internal_categories
                    SET parent_id = NULL, updated_at = now()
                    WHERE id = :id
                    """
                )
                conn.execute(update_sql, {"id": key_to_id[key]})
            elif parent_key in key_to_id:
                # Set parent_id if parent exists
                update_sql = text(
                    """
                    UPDATE internal_categories
                    SET parent_id = :parent_id, updated_at = now()
                    WHERE id = :id
                    """
                )
                conn.execute(
                    update_sql,
                    {
                        "id": key_to_id[key],
                        "parent_id": key_to_id[parent_key],
                    },
                )
    
    return {
        "created": created,
        "updated": updated,
        "key_to_id": key_to_id,
    }


def bulk_set_internal_product_categories(
    project_id: int,
    links: List[Dict[str, Any]],
    on_unknown_sku: str = "skip",
) -> Dict[str, Any]:
    """Bulk set category for internal products by SKU.
    
    Args:
        project_id: Project ID
        links: List of {internal_sku: str, category_key: str, meta_json: dict}
        on_unknown_sku: "skip" or "error" (default "skip")
        
    Returns:
        Dict with:
        - updated: int (products updated)
        - missing_sku: List[str] (SKUs not found)
        - missing_category: List[str] (category keys not found)
    """
    if not links:
        return {"updated": 0, "missing_sku": [], "missing_category": []}
    
    # Get latest snapshot ID
    snapshot_sql = text(
        """
        SELECT id
        FROM internal_data_snapshots
        WHERE project_id = :project_id
          AND status IN ('success', 'partial')
        ORDER BY imported_at DESC
        LIMIT 1
        """
    )
    
    with engine.begin() as conn:
        snapshot_result = conn.execute(snapshot_sql, {"project_id": project_id})
        snapshot_row = snapshot_result.fetchone()
        if not snapshot_row:
            # No snapshot - all SKUs are missing
            missing_sku = [link.get("internal_sku", "") for link in links if link.get("internal_sku")]
            return {"updated": 0, "missing_sku": missing_sku, "missing_category": []}
        
        snapshot_id = snapshot_row._mapping["id"]
        
        # Build SKU and category_key lists
        skus = [link.get("internal_sku", "").strip() for link in links if link.get("internal_sku")]
        category_keys = [link.get("category_key", "").strip() for link in links if link.get("category_key")]
        
        # Get existing products and categories
        products_sql = text(
            """
            SELECT internal_sku
            FROM internal_products
            WHERE project_id = :project_id
              AND snapshot_id = :snapshot_id
              AND internal_sku = ANY(:skus)
            """
        )
        products_result = conn.execute(
            products_sql,
            {
                "project_id": project_id,
                "snapshot_id": snapshot_id,
                "skus": skus,
            },
        )
        existing_skus = {row._mapping["internal_sku"] for row in products_result}
        
        categories_sql = text(
            """
            SELECT key, id
            FROM internal_categories
            WHERE project_id = :project_id
              AND key = ANY(:category_keys)
            """
        )
        categories_result = conn.execute(
            categories_sql,
            {
                "project_id": project_id,
                "category_keys": category_keys,
            },
        )
        key_to_id = {row._mapping["key"]: row._mapping["id"] for row in categories_result}
        
        # Build update mapping: sku -> category_id
        sku_to_category_id: Dict[str, Optional[int]] = {}
        missing_sku: List[str] = []
        missing_category: List[str] = []
        
        for link in links:
            sku = link.get("internal_sku", "").strip()
            category_key = link.get("category_key", "").strip()
            
            if not sku:
                continue
            
            if sku not in existing_skus:
                missing_sku.append(sku)
                if on_unknown_sku == "error":
                    raise ValueError(f"Product not found: {sku}")
                continue
            
            if not category_key:
                # Unset category
                sku_to_category_id[sku] = None
            elif category_key in key_to_id:
                sku_to_category_id[sku] = key_to_id[category_key]
            else:
                missing_category.append(category_key)
                continue
        
        # Bulk update using temporary table approach
        updated = 0
        if sku_to_category_id:
            # Create temp table with updates
            conn.execute(
                text("""
                    CREATE TEMP TABLE IF NOT EXISTS category_updates_temp (
                        internal_sku TEXT,
                        category_id BIGINT
                    ) ON COMMIT DROP
                """)
            )
            
            # Insert updates into temp table
            if sku_to_category_id:
                insert_sql = text(
                    """
                    INSERT INTO category_updates_temp (internal_sku, category_id)
                    VALUES (:sku, :cat_id)
                    """
                )
                # Use executemany for bulk insert
                updates_data = [
                    {"sku": sku, "cat_id": cat_id}
                    for sku, cat_id in sku_to_category_id.items()
                ]
                conn.execute(insert_sql, updates_data)
                
                # Update from temp table
                update_sql = text(
                    """
                    UPDATE internal_products ip
                    SET internal_category_id = cu.category_id
                    FROM category_updates_temp cu
                    WHERE ip.project_id = :project_id
                      AND ip.snapshot_id = :snapshot_id
                      AND ip.internal_sku = cu.internal_sku
                    """
                )
                result = conn.execute(
                    update_sql,
                    {
                        "project_id": project_id,
                        "snapshot_id": snapshot_id,
                    },
                )
                updated = result.rowcount
        
        return {
            "updated": updated,
            "missing_sku": missing_sku,
            "missing_category": missing_category,
        }
