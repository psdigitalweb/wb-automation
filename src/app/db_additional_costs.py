"""Database helpers for Additional Cost Entries.

This module provides CRUD and summary aggregation for additional_cost_entries.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.db import engine


def _validate_scope_fields(scope: str, data: dict) -> None:
    """Validate that scope and related fields are consistent.
    
    Args:
        scope: Scope value ('project', 'marketplace', or 'product')
        data: Dictionary with entry fields
        
    Raises:
        ValueError: If scope and fields are inconsistent
    """
    if scope == 'project':
        if data.get('marketplace_code') or data.get('internal_sku') or data.get('nm_id'):
            raise ValueError("scope='project' requires all marketplace_code, internal_sku, nm_id to be NULL")
    elif scope == 'marketplace':
        if not data.get('marketplace_code'):
            raise ValueError("scope='marketplace' requires marketplace_code")
        if data.get('internal_sku') or data.get('nm_id'):
            raise ValueError("scope='marketplace' requires internal_sku and nm_id to be NULL")
    elif scope == 'product':
        if not data.get('internal_sku'):
            raise ValueError("scope='product' requires internal_sku")
    else:
        raise ValueError(f"Invalid scope: {scope}. Must be 'project', 'marketplace', or 'product'")


def create_additional_cost_entry(project_id: int, data: dict) -> dict:
    """Create a new additional cost entry.
    
    Args:
        project_id: Project ID
        data: Dictionary with entry fields (scope, period_from, period_to, amount, category, etc.)
        
    Returns:
        Created entry as dict
        
    Raises:
        ValueError: If scope and fields are inconsistent
    """
    # Get scope (default to 'project' if not provided)
    scope = data.get("scope", "project")
    
    # Validate scope vs fields
    _validate_scope_fields(scope, data)
    
    # Prepare payload JSON
    payload = data.get("payload", {})
    payload_json = json.dumps(payload, ensure_ascii=False) if payload else "{}"
    
    # Compute payload_hash if payload_hash not provided
    payload_hash = data.get("payload_hash")
    if payload_hash is None and payload:
        import hashlib
        normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    
    sql = text("""
        INSERT INTO additional_cost_entries (
            project_id,
            scope,
            marketplace_code,
            period_from,
            period_to,
            date_incurred,
            currency,
            amount,
            category,
            subcategory,
            vendor,
            description,
            nm_id,
            internal_sku,
            source,
            external_uid,
            payload,
            payload_hash,
            updated_at
        )
        VALUES (
            :project_id,
            :scope,
            :marketplace_code,
            :period_from,
            :period_to,
            :date_incurred,
            :currency,
            :amount,
            :category,
            :subcategory,
            :vendor,
            :description,
            :nm_id,
            :internal_sku,
            :source,
            :external_uid,
            CAST(:payload AS jsonb),
            :payload_hash,
            NOW()
        )
        RETURNING *
    """)
    
    params = {
        "project_id": project_id,
        "scope": scope,
        "marketplace_code": data.get("marketplace_code"),
        "period_from": data.get("period_from"),
        "period_to": data.get("period_to"),
        "date_incurred": data.get("date_incurred"),
        "currency": data.get("currency", "RUB"),
        "amount": data.get("amount"),
        "category": data.get("category"),
        "subcategory": data.get("subcategory"),
        "vendor": data.get("vendor"),
        "description": data.get("description"),
        "nm_id": data.get("nm_id"),
        "internal_sku": data.get("internal_sku"),
        "source": data.get("source", "manual"),
        "external_uid": data.get("external_uid"),
        "payload": payload_json,
        "payload_hash": payload_hash,
    }
    
    with engine.begin() as conn:
        row = conn.execute(sql, params).mappings().first()
        return dict(row)


def get_additional_cost_entry(project_id: int, entry_id: int) -> Optional[dict]:
    """Get a single additional cost entry by ID.
    
    Args:
        project_id: Project ID (for security check)
        entry_id: Entry ID
        
    Returns:
        Entry as dict, or None if not found
    """
    sql = text("""
        SELECT *
        FROM additional_cost_entries
        WHERE id = :entry_id
          AND project_id = :project_id
    """)
    
    with engine.connect() as conn:
        row = conn.execute(sql, {"entry_id": entry_id, "project_id": project_id}).mappings().first()
        return dict(row) if row else None


def get_additional_cost_entry_by_id(entry_id: int) -> Optional[dict]:
    """Get a single additional cost entry by ID without project_id filter.
    
    Used internally to get project_id from entry for permission checks.
    
    Args:
        entry_id: Entry ID
        
    Returns:
        Entry as dict, or None if not found
    """
    sql = text("""
        SELECT *
        FROM additional_cost_entries
        WHERE id = :entry_id
    """)
    
    with engine.connect() as conn:
        row = conn.execute(sql, {"entry_id": entry_id}).mappings().first()
        return dict(row) if row else None


def list_additional_cost_entries(
    project_id: int,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    scope: Optional[str] = None,
    marketplace_code: Optional[str] = None,
    category: Optional[str] = None,
    nm_id: Optional[int] = None,
    internal_sku: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[dict], Optional[int]]:
    """List additional cost entries with filters and pagination.
    
    Args:
        project_id: Project ID
        date_from: Filter by period intersection (period_from <= date_to AND period_to >= date_from)
        date_to: Filter by period intersection
        scope: Filter by scope ('project', 'marketplace', or 'product')
        marketplace_code: Filter by marketplace code
        category: Filter by category
        nm_id: Filter by nm_id
        internal_sku: Filter by internal_sku
        limit: Maximum number of records
        offset: Offset for pagination
        
    Returns:
        Tuple of (list of entries, total count or None)
    """
    where_clauses = ["project_id = :project_id"]
    params: Dict[str, Any] = {"project_id": project_id, "limit": limit, "offset": offset}
    
    if date_from is not None:
        where_clauses.append("period_to >= :date_from")
        params["date_from"] = date_from
    if date_to is not None:
        where_clauses.append("period_from <= :date_to")
        params["date_to"] = date_to
    if scope is not None:
        where_clauses.append("scope = :scope")
        params["scope"] = scope
    if marketplace_code is not None:
        where_clauses.append("marketplace_code = :marketplace_code")
        params["marketplace_code"] = marketplace_code
    if category is not None:
        where_clauses.append("category = :category")
        params["category"] = category
    if nm_id is not None:
        where_clauses.append("nm_id = :nm_id")
        params["nm_id"] = nm_id
    if internal_sku is not None:
        where_clauses.append("internal_sku = :internal_sku")
        params["internal_sku"] = internal_sku
    
    where_sql = " AND ".join(where_clauses)
    
    select_sql = text(f"""
        SELECT *
        FROM additional_cost_entries
        WHERE {where_sql}
        ORDER BY period_from DESC, id DESC
        LIMIT :limit OFFSET :offset
    """)
    
    with engine.connect() as conn:
        rows = conn.execute(select_sql, params).mappings().all()
        items = [dict(row) for row in rows]
        
        # Return without total (as per plan - no unified total pattern in project)
        return (items, None)


def update_additional_cost_entry(project_id: int, entry_id: int, patch: dict) -> Optional[dict]:
    """Update an additional cost entry (partial update).
    
    Args:
        project_id: Project ID (for security check)
        entry_id: Entry ID
        patch: Dictionary with fields to update (only provided fields are updated)
        
    Returns:
        Updated entry as dict, or None if not found
        
    Raises:
        ValueError: If scope and fields are inconsistent
    """
    if not patch:
        # No updates, just return existing entry
        return get_additional_cost_entry(project_id, entry_id)
    
    # Get current entry to know current scope
    current_entry = get_additional_cost_entry(project_id, entry_id)
    if not current_entry:
        return None
    
    current_scope = current_entry.get("scope", "project")
    new_scope = patch.get("scope", current_scope)
    
    # Build merged data for validation (current values + patch)
    merged_data = {
        "marketplace_code": patch.get("marketplace_code", current_entry.get("marketplace_code")),
        "internal_sku": patch.get("internal_sku", current_entry.get("internal_sku")),
        "nm_id": patch.get("nm_id", current_entry.get("nm_id")),
    }
    
    # Validate scope vs fields
    _validate_scope_fields(new_scope, merged_data)
    
    # Build dynamic SET clause
    set_clauses = ["updated_at = NOW()"]
    params: Dict[str, Any] = {"entry_id": entry_id, "project_id": project_id}
    
    if "scope" in patch:
        set_clauses.append("scope = :scope")
        params["scope"] = patch["scope"]
    if "marketplace_code" in patch:
        set_clauses.append("marketplace_code = :marketplace_code")
        params["marketplace_code"] = patch["marketplace_code"]
    if "period_from" in patch:
        set_clauses.append("period_from = :period_from")
        params["period_from"] = patch["period_from"]
    if "period_to" in patch:
        set_clauses.append("period_to = :period_to")
        params["period_to"] = patch["period_to"]
    if "date_incurred" in patch:
        set_clauses.append("date_incurred = :date_incurred")
        params["date_incurred"] = patch["date_incurred"]
    if "currency" in patch:
        set_clauses.append("currency = :currency")
        params["currency"] = patch["currency"]
    if "amount" in patch:
        set_clauses.append("amount = :amount")
        params["amount"] = patch["amount"]
    if "category" in patch:
        set_clauses.append("category = :category")
        params["category"] = patch["category"]
    if "subcategory" in patch:
        set_clauses.append("subcategory = :subcategory")
        params["subcategory"] = patch["subcategory"]
    if "vendor" in patch:
        set_clauses.append("vendor = :vendor")
        params["vendor"] = patch["vendor"]
    if "description" in patch:
        set_clauses.append("description = :description")
        params["description"] = patch["description"]
    if "nm_id" in patch:
        set_clauses.append("nm_id = :nm_id")
        params["nm_id"] = patch["nm_id"]
    if "internal_sku" in patch:
        set_clauses.append("internal_sku = :internal_sku")
        params["internal_sku"] = patch["internal_sku"]
    if "source" in patch:
        set_clauses.append("source = :source")
        params["source"] = patch["source"]
    if "external_uid" in patch:
        set_clauses.append("external_uid = :external_uid")
        params["external_uid"] = patch["external_uid"]
    if "payload" in patch:
        payload = patch["payload"]
        payload_json = json.dumps(payload, ensure_ascii=False) if payload else "{}"
        set_clauses.append("payload = CAST(:payload AS jsonb)")
        params["payload"] = payload_json
    if "payload_hash" in patch:
        set_clauses.append("payload_hash = :payload_hash")
        params["payload_hash"] = patch["payload_hash"]
    
    set_sql = ", ".join(set_clauses)
    
    sql = text(f"""
        UPDATE additional_cost_entries
        SET {set_sql}
        WHERE id = :entry_id
          AND project_id = :project_id
        RETURNING *
    """)
    
    with engine.begin() as conn:
        row = conn.execute(sql, params).mappings().first()
        return dict(row) if row else None


def delete_additional_cost_entry(project_id: int, entry_id: int) -> bool:
    """Delete an additional cost entry.
    
    Args:
        project_id: Project ID (for security check)
        entry_id: Entry ID
        
    Returns:
        True if deleted, False if not found
    """
    sql = text("""
        DELETE FROM additional_cost_entries
        WHERE id = :entry_id
          AND project_id = :project_id
    """)
    
    with engine.begin() as conn:
        result = conn.execute(sql, {"entry_id": entry_id, "project_id": project_id})
        return result.rowcount > 0


def get_additional_cost_summary(
    project_id: int,
    date_from: date,
    date_to: date,
    level: str = "project",
    marketplace_code: Optional[str] = None,
) -> dict:
    """Get summary of additional costs with prorated amounts based on period overlap.
    
    Args:
        project_id: Project ID
        date_from: Start date for summary period
        date_to: End date for summary period
        level: Aggregation level ('project', 'marketplace', or 'product') - filters by scope
        marketplace_code: Optional marketplace code filter
        
    Returns:
        Dict with total_amount and breakdown (list of groups with prorated amounts)
    """
    # Base WHERE clause
    where_clauses = [
        "project_id = :project_id",
        "period_from <= :date_to",
        "period_to >= :date_from",
    ]
    params: Dict[str, Any] = {
        "project_id": project_id,
        "date_from": date_from,
        "date_to": date_to,
    }
    
    # Filter by scope based on level
    if level == "project":
        where_clauses.append("scope = 'project'")
    elif level == "marketplace":
        where_clauses.append("scope = 'marketplace'")
    elif level == "product":
        where_clauses.append("scope = 'product'")
    else:
        raise ValueError(f"Invalid level: {level}. Must be 'project', 'marketplace', or 'product'")
    
    # Add marketplace filter if provided
    if marketplace_code is not None:
        where_clauses.append("marketplace_code = :marketplace_code")
        params["marketplace_code"] = marketplace_code
    
    where_sql = " AND ".join(where_clauses)
    
    # Build GROUP BY clause based on level
    if level == "project":
        group_by = "category, subcategory"
        select_fields = "category, subcategory, NULL::text AS marketplace_code, NULL::text AS internal_sku, NULL::bigint AS nm_id"
    elif level == "marketplace":
        group_by = "marketplace_code, category, subcategory"
        select_fields = "category, subcategory, marketplace_code, NULL::text AS internal_sku, NULL::bigint AS nm_id"
    elif level == "product":
        group_by = "internal_sku, category, subcategory"
        select_fields = "category, subcategory, marketplace_code, internal_sku, MIN(nm_id) AS nm_id"
    else:
        raise ValueError(f"Invalid level: {level}")
    
    # SQL with prorated amount calculation
    sql = text(f"""
        WITH prorated AS (
            SELECT
                {select_fields},
                amount,
                period_from,
                period_to,
                GREATEST(period_from, :date_from) AS overlap_from,
                LEAST(period_to, :date_to) AS overlap_to,
                (LEAST(period_to, :date_to) - GREATEST(period_from, :date_from) + 1)::integer AS overlap_days,
                (period_to - period_from + 1)::integer AS entry_days
            FROM additional_cost_entries
            WHERE {where_sql}
        )
        SELECT
            {select_fields},
            SUM(amount * overlap_days::numeric / NULLIF(entry_days, 0)) AS prorated_amount
        FROM prorated
        GROUP BY {group_by}
        ORDER BY prorated_amount DESC
    """)
    
    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
        breakdown = [dict(row) for row in rows]
        
        # Calculate total (keep as Decimal for precision)
        from decimal import Decimal
        total_amount = sum(Decimal(str(row.get("prorated_amount", 0) or 0)) for row in breakdown)
        
        return {
            "total_amount": total_amount,
            "breakdown": breakdown,
        }


__all__ = [
    "create_additional_cost_entry",
    "get_additional_cost_entry",
    "get_additional_cost_entry_by_id",
    "list_additional_cost_entries",
    "update_additional_cost_entry",
    "delete_additional_cost_entry",
    "get_additional_cost_summary",
]
