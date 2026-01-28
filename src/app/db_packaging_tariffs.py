"""Database helpers for Packaging Tariffs.

This module provides CRUD and summary aggregation for packaging_tariffs.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.db import engine


def bulk_upsert_packaging_tariffs(
    project_id: int,
    valid_from: date,
    cost_per_unit: Decimal,
    sku_list: List[str],
    notes: Optional[str] = None,
) -> Dict[str, int]:
    """Bulk upsert packaging tariffs for a list of SKUs.
    
    Args:
        project_id: Project ID
        valid_from: Date from which tariff is valid
        cost_per_unit: Cost per unit (must be > 0)
        sku_list: List of internal_sku strings (will be trimmed, deduplicated)
        notes: Optional notes
        
    Returns:
        Dict with summary: {created: int, updated: int, skipped: int}
    """
    if not sku_list:
        raise ValueError("sku_list cannot be empty")
    
    if cost_per_unit <= 0:
        raise ValueError("cost_per_unit must be > 0")
    
    # Normalize SKU list: trim, remove empty, deduplicate (preserve order not required)
    normalized_skus = []
    seen = set()
    for sku in sku_list:
        cleaned = (sku or "").strip()
        if cleaned and cleaned not in seen:
            normalized_skus.append(cleaned)
            seen.add(cleaned)
    
    if not normalized_skus:
        raise ValueError("sku_list must contain at least one non-empty SKU after normalization")
    
    created = 0
    updated = 0
    skipped = 0
    
    with engine.begin() as conn:
        for sku in normalized_skus:
            # Check if exists
            check_sql = text("""
                SELECT id
                FROM packaging_tariffs
                WHERE project_id = :project_id
                  AND internal_sku = :internal_sku
                  AND valid_from = :valid_from
            """)
            existing = conn.execute(
                check_sql,
                {
                    "project_id": project_id,
                    "internal_sku": sku,
                    "valid_from": valid_from,
                },
            ).scalar_one_or_none()
            
            if existing:
                # Update existing
                update_sql = text("""
                    UPDATE packaging_tariffs
                    SET cost_per_unit = :cost_per_unit,
                        notes = :notes,
                        updated_at = now()
                    WHERE id = :id
                """)
                result = conn.execute(
                    update_sql,
                    {
                        "id": existing,
                        "cost_per_unit": cost_per_unit,
                        "notes": notes,
                    },
                )
                if result.rowcount > 0:
                    updated += 1
                else:
                    skipped += 1
            else:
                # Insert new
                insert_sql = text("""
                    INSERT INTO packaging_tariffs (
                        project_id,
                        internal_sku,
                        valid_from,
                        cost_per_unit,
                        currency,
                        notes
                    )
                    VALUES (
                        :project_id,
                        :internal_sku,
                        :valid_from,
                        :cost_per_unit,
                        'RUB',
                        :notes
                    )
                """)
                conn.execute(
                    insert_sql,
                    {
                        "project_id": project_id,
                        "internal_sku": sku,
                        "valid_from": valid_from,
                        "cost_per_unit": cost_per_unit,
                        "notes": notes,
                    },
                )
                created += 1
    
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
    }


def list_packaging_tariffs(
    project_id: int,
    internal_sku_query: Optional[str] = None,
    only_current: bool = True,
    limit: int = 200,
    offset: int = 0,
) -> Dict[str, Any]:
    """List packaging tariffs for a project.
    
    Args:
        project_id: Project ID
        internal_sku_query: Optional filter by internal_sku (ILIKE)
        only_current: If True, return only current tariff per SKU (latest valid_from)
                      If False, return full history
        limit: Maximum number of records
        offset: Offset for pagination
        
    Returns:
        Dict with items list and total count
    """
    where_clauses = ["project_id = :project_id"]
    params: Dict[str, Any] = {"project_id": project_id, "limit": limit, "offset": offset}
    
    if internal_sku_query:
        where_clauses.append("internal_sku ILIKE :sku_query")
        params["sku_query"] = f"%{internal_sku_query}%"
    
    where_sql = " AND ".join(where_clauses)
    
    if only_current:
        # DISTINCT ON to get latest valid_from per SKU
        sql = text(f"""
            SELECT DISTINCT ON (internal_sku)
                id,
                project_id,
                internal_sku,
                valid_from,
                cost_per_unit,
                currency,
                notes,
                created_at,
                updated_at
            FROM packaging_tariffs
            WHERE {where_sql}
            ORDER BY internal_sku, valid_from DESC
            LIMIT :limit OFFSET :offset
        """)
    else:
        # Full history
        sql = text(f"""
            SELECT
                id,
                project_id,
                internal_sku,
                valid_from,
                cost_per_unit,
                currency,
                notes,
                created_at,
                updated_at
            FROM packaging_tariffs
            WHERE {where_sql}
            ORDER BY internal_sku ASC, valid_from DESC
            LIMIT :limit OFFSET :offset
        """)
    
    # Count total (for pagination)
    count_sql = text(f"""
        SELECT COUNT(*)
        FROM packaging_tariffs
        WHERE {where_sql}
    """)
    
    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
        total_result = conn.execute(count_sql, {k: v for k, v in params.items() if k not in ["limit", "offset"]})
        total = total_result.scalar_one()
    
    return {
        "items": [dict(row) for row in rows],
        "total": total,
    }


def delete_packaging_tariff(project_id: int, tariff_id: int) -> bool:
    """Delete a packaging tariff.
    
    Args:
        project_id: Project ID (for security check)
        tariff_id: Tariff ID to delete
        
    Returns:
        True if deleted, False if not found
    """
    with engine.begin() as conn:
        delete_sql = text("""
            DELETE FROM packaging_tariffs
            WHERE id = :tariff_id
              AND project_id = :project_id
        """)
        result = conn.execute(
            delete_sql,
            {
                "tariff_id": tariff_id,
                "project_id": project_id,
            },
        )
        return result.rowcount > 0


def get_packaging_cost_summary(
    project_id: int,
    date_from: date,
    date_to: date,
    group_by: str = "project",
    internal_sku: Optional[str] = None,
) -> Dict[str, Any]:
    """Get packaging cost summary for a period based on sold units.
    
    Algorithm:
    1) Get sales rows: (sale_date, nm_id, units_sold) from wb_finance_report_lines.payload
    2) Map nm_id -> internal_sku via internal_product_identifiers
    3) For each (sale_date, internal_sku) determine tariff:
       - select max(valid_from) <= sale_date for this sku
       - if no tariff -> cost = 0
    4) cost = units_sold * cost_per_unit
    5) Sum by group_by level
    
    Args:
        project_id: Project ID
        date_from: Start date
        date_to: End date
        group_by: 'project' or 'product'
        internal_sku: Optional filter by specific SKU
        
    Returns:
        Dict with total_amount, breakdown, missing_tariff info
    """
    if group_by not in ["project", "product"]:
        raise ValueError("group_by must be 'project' or 'product'")
    
    # Step 1: Extract sales from wb_finance_report_lines.payload
    # WB finance reports payload typically contains fields like:
    # - nm_id (or nmId)
    # - quantity (or qty, quantity_doc)
    # - sale_dt (or sale_date, doc_date)
    # We'll extract these from JSONB payload
    
    # Step 2: Map nm_id -> internal_sku via internal_product_identifiers
    # Step 3: Apply tariffs
    # Step 4: Aggregate
    
    # For now, implement a basic version that extracts from payload
    # This assumes payload has fields: nm_id (or nmId), quantity (or qty), sale_dt (or sale_date)
    
    sales_cte = """
    WITH sales_raw AS (
        SELECT
            r.report_id,
            r.line_id,
            r.payload->>'nm_id' AS nm_id_str,
            r.payload->>'nmId' AS nm_id_str_alt,
            r.payload->>'quantity' AS qty_str,
            r.payload->>'qty' AS qty_str_alt,
            r.payload->>'quantity_doc' AS qty_str_alt2,
            r.payload->>'sale_dt' AS sale_date_str,
            r.payload->>'sale_date' AS sale_date_str_alt,
            r.payload->>'doc_date' AS sale_date_str_alt2,
            r.report_id AS report_id_val
        FROM wb_finance_report_lines r
        JOIN wb_finance_reports rf ON rf.project_id = :project_id
            AND rf.report_id = r.report_id
            AND rf.marketplace_code = 'wildberries'
        WHERE r.project_id = :project_id
    ),
    sales_parsed AS (
        SELECT
            CASE 
                WHEN nm_id_str ~ '^[0-9]+$' THEN (nm_id_str)::bigint
                WHEN nm_id_str_alt ~ '^[0-9]+$' THEN (nm_id_str_alt)::bigint
                ELSE NULL
            END AS nm_id,
            CASE 
                WHEN sale_date_str IS NOT NULL THEN (sale_date_str::date)
                WHEN sale_date_str_alt IS NOT NULL THEN (sale_date_str_alt::date)
                WHEN sale_date_str_alt2 IS NOT NULL THEN (sale_date_str_alt2::date)
                ELSE NULL
            END AS sale_date,
            CASE 
                WHEN qty_str ~ '^[0-9]+$' THEN (qty_str)::integer
                WHEN qty_str_alt ~ '^[0-9]+$' THEN (qty_str_alt)::integer
                WHEN qty_str_alt2 ~ '^[0-9]+$' THEN (qty_str_alt2)::integer
                ELSE 0
            END AS units_sold
        FROM sales_raw
        WHERE (nm_id_str ~ '^[0-9]+$' OR nm_id_str_alt ~ '^[0-9]+$')
          AND (sale_date_str IS NOT NULL OR sale_date_str_alt IS NOT NULL OR sale_date_str_alt2 IS NOT NULL)
          AND (qty_str ~ '^[0-9]+$' OR qty_str_alt ~ '^[0-9]+$' OR qty_str_alt2 ~ '^[0-9]+$')
    ),
    sales_filtered AS (
        SELECT nm_id, sale_date, units_sold
        FROM sales_parsed
        WHERE nm_id IS NOT NULL
          AND sale_date IS NOT NULL
          AND sale_date BETWEEN :date_from AND :date_to
          AND units_sold > 0
    ),
    latest_snapshot AS (
        SELECT id AS snapshot_id
        FROM internal_data_snapshots
        WHERE project_id = :project_id
          AND status IN ('success', 'partial')
        ORDER BY imported_at DESC
        LIMIT 1
    ),
    sku_mapping AS (
        SELECT DISTINCT ON (ipi.marketplace_item_id)
            ipi.marketplace_item_id::bigint AS nm_id,
            ip.internal_sku
        FROM internal_product_identifiers ipi
        JOIN internal_products ip ON ip.id = ipi.internal_product_id
            AND ip.snapshot_id = ipi.snapshot_id
        CROSS JOIN latest_snapshot ls
        WHERE ipi.project_id = :project_id
          AND ipi.snapshot_id = ls.snapshot_id
          AND ipi.marketplace_code = 'wildberries'
          AND ipi.marketplace_item_id IS NOT NULL
          AND ipi.marketplace_item_id ~ '^[0-9]+$'
        ORDER BY ipi.marketplace_item_id, ipi.id DESC
    ),
    sales_with_sku AS (
        SELECT
            s.sale_date,
            COALESCE(sm.internal_sku, NULL) AS internal_sku,
            s.units_sold
        FROM sales_filtered s
        LEFT JOIN sku_mapping sm ON sm.nm_id = s.nm_id
    )
    """
    
    sales_cte_suffix = ""
    if internal_sku:
        sales_cte_suffix = "WHERE internal_sku = :filter_sku"
    else:
        sales_cte_suffix = "WHERE internal_sku IS NOT NULL"
    
    # Complete sales CTE with filter
    sales_cte_complete = sales_cte + f"""
    SELECT sale_date, internal_sku, units_sold
    FROM sales_with_sku
    {sales_cte_suffix}
    """
    
    # Get tariffs for each SKU-date combination
    tariff_cte = f"""
    , tariff_lookup AS (
        SELECT DISTINCT ON (s.internal_sku, s.sale_date)
            s.sale_date,
            s.internal_sku,
            s.units_sold,
            pt.cost_per_unit,
            pt.valid_from
        FROM ({sales_cte_complete}) s
        LEFT JOIN LATERAL (
            SELECT cost_per_unit, valid_from
            FROM packaging_tariffs
            WHERE project_id = :project_id
              AND internal_sku = s.internal_sku
              AND valid_from <= s.sale_date
            ORDER BY valid_from DESC
            LIMIT 1
        ) pt ON true
    )
    """
    
    if group_by == "project":
        summary_sql = text(sales_cte + tariff_cte + """
        SELECT
            COALESCE(SUM(units_sold * COALESCE(cost_per_unit, 0)), 0) AS total_amount
        FROM tariff_lookup
        """)
        
        breakdown_sql = None
    else:  # group_by == "product"
        summary_sql = text(sales_cte + tariff_cte + """
        SELECT
            COALESCE(SUM(units_sold * COALESCE(cost_per_unit, 0)), 0) AS total_amount
        FROM tariff_lookup
        """)
        
        breakdown_sql = text(sales_cte + tariff_cte + """
        SELECT
            internal_sku,
            SUM(units_sold)::bigint AS units_sold,
            SUM(units_sold * COALESCE(cost_per_unit, 0)) AS amount
        FROM tariff_lookup
        GROUP BY internal_sku
        ORDER BY internal_sku
        """)
    
    # Missing tariff detection
    missing_sql = text(sales_cte + f"""
    , missing_check AS (
        SELECT DISTINCT
            s.internal_sku,
            s.sale_date
        FROM ({sales_cte_complete}) s
        WHERE NOT EXISTS (
            SELECT 1
            FROM packaging_tariffs pt
            WHERE pt.project_id = :project_id
              AND pt.internal_sku = s.internal_sku
              AND pt.valid_from <= s.sale_date
        )
    )
    SELECT
        COUNT(DISTINCT internal_sku) AS count,
        ARRAY_AGG(DISTINCT internal_sku ORDER BY internal_sku) FILTER (WHERE internal_sku IS NOT NULL) AS skus
    FROM missing_check
    LIMIT 200
    """)
    
    params = {
        "project_id": project_id,
        "date_from": date_from,
        "date_to": date_to,
    }
    if internal_sku:
        params["filter_sku"] = internal_sku
    
    with engine.connect() as conn:
        # Get total
        total_row = conn.execute(summary_sql, params).mappings().first()
        total_amount = Decimal(str(total_row["total_amount"])) if total_row else Decimal("0")
        
        # Get breakdown if product level
        breakdown = []
        if group_by == "product" and breakdown_sql:
            breakdown_rows = conn.execute(breakdown_sql, params).mappings().all()
            breakdown = [
                {
                    "internal_sku": row["internal_sku"],
                    "units_sold": int(row["units_sold"]),
                    "amount": Decimal(str(row["amount"])),
                }
                for row in breakdown_rows
            ]
        
        # Get missing tariff info
        missing_row = conn.execute(missing_sql, params).mappings().first()
        missing_count = int(missing_row["count"]) if missing_row and missing_row["count"] else 0
        missing_skus = missing_row["skus"] if missing_row and missing_row["skus"] else []
        # Limit missing SKUs list to 200
        if isinstance(missing_skus, list) and len(missing_skus) > 200:
            missing_skus = missing_skus[:200]
    
    return {
        "total_amount": total_amount,
        "breakdown": breakdown,
        "missing_tariff": {
            "count": missing_count,
            "skus": missing_skus if isinstance(missing_skus, list) else [],
        },
    }
