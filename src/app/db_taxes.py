"""Database helpers for tax profiles and tax statement snapshots (project-level)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.db import engine


def get_tax_profile(project_id: int) -> Optional[Dict[str, Any]]:
    """Get tax profile for a project.
    
    Returns:
        Dict with project_id, model_code, params_json, updated_at, or None if not found
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT project_id, model_code, params_json, updated_at
                FROM tax_profiles
                WHERE project_id = :project_id
            """),
            {"project_id": project_id},
        ).mappings().first()
        
        if not row:
            return None
        
        return {
            "project_id": row["project_id"],
            "model_code": row["model_code"],
            "params_json": row["params_json"],
            "updated_at": row["updated_at"],
        }


def upsert_tax_profile(
    project_id: int,
    model_code: str,
    params_json: Dict[str, Any],
) -> Dict[str, Any]:
    """Insert or update tax profile for a project.
    
    Args:
        project_id: Project ID
        model_code: Tax model code (e.g., 'profit_tax', 'turnover_tax')
        params_json: Parameters dict (rate, base_key, etc.)
        
    Returns:
        Dict with project_id, model_code, params_json, updated_at
    """
    import json as json_module
    
    params_json_str = json_module.dumps(params_json, ensure_ascii=False)
    
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO tax_profiles (project_id, model_code, params_json, updated_at)
                VALUES (:project_id, :model_code, CAST(:params_json AS jsonb), now())
                ON CONFLICT (project_id) DO UPDATE SET
                    model_code = EXCLUDED.model_code,
                    params_json = EXCLUDED.params_json,
                    updated_at = now()
            """),
            {
                "project_id": project_id,
                "model_code": model_code,
                "params_json": params_json_str,
            },
        )
        
        # Fetch updated row
        row = conn.execute(
            text("""
                SELECT project_id, model_code, params_json, updated_at
                FROM tax_profiles
                WHERE project_id = :project_id
            """),
            {"project_id": project_id},
        ).mappings().first()
        
        return {
            "project_id": row["project_id"],
            "model_code": row["model_code"],
            "params_json": row["params_json"],
            "updated_at": row["updated_at"],
        }


def _get_next_tax_statement_version(conn, project_id: int, period_id: int) -> int:
    """Compute next snapshot version with an advisory lock to avoid races.
    
    Uses pg_advisory_xact_lock(key1, key2) with (project_id, period_id) as two ints
    to avoid collision with internal_data_snapshots (which uses only project_id).
    """
    # Take transaction-scoped advisory lock on (project_id, period_id)
    conn.execute(
        text("SELECT pg_advisory_xact_lock(:key1, :key2)"),
        {"key1": project_id, "key2": period_id},
    )
    row = conn.execute(
        text("""
            SELECT COALESCE(MAX(version), 0) AS max_version
            FROM tax_statement_snapshots
            WHERE project_id = :project_id AND period_id = :period_id
        """),
        {"project_id": project_id, "period_id": period_id},
    ).fetchone()
    max_version = int(row._mapping["max_version"]) if row and row._mapping["max_version"] is not None else 0
    return max_version + 1


def create_tax_statement_snapshot(
    project_id: int,
    period_id: int,
    status: str,
    tax_expense_total: Optional[Decimal],
    breakdown_json: Dict[str, Any],
    stats_json: Dict[str, Any],
    error_message: Optional[str] = None,
    error_trace: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a new tax statement snapshot with version increment.
    
    Args:
        project_id: Project ID
        period_id: Period ID
        status: 'success' or 'failed'
        tax_expense_total: Total tax expense (None if failed)
        breakdown_json: Breakdown details (JSONB)
        stats_json: Stats/metadata (JSONB) - must include model_code, params snapshot, etc.
        error_message: Error message if failed
        error_trace: Error trace if failed
        
    Returns:
        Dict with snapshot fields including id, version, created_at
    """
    import json as json_module
    
    breakdown_json_str = json_module.dumps(breakdown_json, ensure_ascii=False)
    stats_json_str = json_module.dumps(stats_json, ensure_ascii=False)
    
    with engine.begin() as conn:
        version = _get_next_tax_statement_version(conn, project_id, period_id)
        
        result = conn.execute(
            text("""
                INSERT INTO tax_statement_snapshots (
                    project_id, period_id, version, status,
                    tax_expense_total, breakdown_json, stats_json,
                    error_message, error_trace, created_at
                )
                VALUES (
                    :project_id, :period_id, :version, :status,
                    :tax_expense_total, CAST(:breakdown_json AS jsonb), CAST(:stats_json AS jsonb),
                    :error_message, :error_trace, now()
                )
                RETURNING id, project_id, period_id, version, status,
                          tax_expense_total, breakdown_json, stats_json,
                          error_message, error_trace, created_at
            """),
            {
                "project_id": project_id,
                "period_id": period_id,
                "version": version,
                "status": status,
                "tax_expense_total": tax_expense_total,
                "breakdown_json": breakdown_json_str,
                "stats_json": stats_json_str,
                "error_message": error_message[:500] if error_message else None,
                "error_trace": error_trace[:50000] if error_trace else None,
            },
        )
        
        row = result.mappings().first()
        return dict(row)


def list_tax_statements(
    project_id: int,
    period_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """List tax statements for a project with optional filters.
    
    Args:
        project_id: Project ID
        period_id: Filter by period_id
        date_from: Filter by period date_from (requires join with periods)
        date_to: Filter by period date_to (requires join with periods)
        
    Returns:
        List of snapshot dicts, ordered by created_at DESC
    """
    where_clauses = ["tss.project_id = :project_id"]
    params: Dict[str, Any] = {"project_id": project_id}
    
    if period_id:
        where_clauses.append("tss.period_id = :period_id")
        params["period_id"] = period_id
    
    if date_from or date_to:
        # Need to join with periods
        if date_from:
            where_clauses.append("p.date_from >= :date_from")
            params["date_from"] = date_from
        if date_to:
            where_clauses.append("p.date_to <= :date_to")
            params["date_to"] = date_to
        
        sql = text(f"""
            SELECT tss.id, tss.project_id, tss.period_id, tss.version, tss.status,
                   tss.tax_expense_total, tss.breakdown_json, tss.stats_json,
                   tss.error_message, tss.error_trace, tss.created_at
            FROM tax_statement_snapshots tss
            JOIN periods p ON p.id = tss.period_id
            WHERE {' AND '.join(where_clauses)}
            ORDER BY tss.created_at DESC
        """)
    else:
        sql = text(f"""
            SELECT id, project_id, period_id, version, status,
                   tax_expense_total, breakdown_json, stats_json,
                   error_message, error_trace, created_at
            FROM tax_statement_snapshots
            WHERE {' AND '.join(where_clauses)}
            ORDER BY created_at DESC
        """)
    
    with engine.connect() as conn:
        rows = conn.execute(sql, params).mappings().all()
    
    return [dict(row) for row in rows]


def get_latest_tax_statement(
    project_id: int,
    period_id: int,
) -> Optional[Dict[str, Any]]:
    """Get latest tax statement snapshot for (project_id, period_id).
    
    Returns:
        Dict with snapshot fields, or None if not found
    """
    with engine.connect() as conn:
        row = conn.execute(
            text("""
                SELECT id, project_id, period_id, version, status,
                       tax_expense_total, breakdown_json, stats_json,
                       error_message, error_trace, created_at
                FROM tax_statement_snapshots
                WHERE project_id = :project_id AND period_id = :period_id
                ORDER BY version DESC
                LIMIT 1
            """),
            {"project_id": project_id, "period_id": period_id},
        ).mappings().first()
        
        if not row:
            return None
        
        return dict(row)


def get_tax_adjustments_sum(
    project_id: int,
    period_id: int,
) -> Decimal:
    """Get sum of tax adjustments for a period.
    
    Returns:
        Sum as Decimal (0 if no adjustments or table doesn't exist)
    """
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT COALESCE(SUM(amount), 0) AS total
                    FROM tax_adjustments
                    WHERE project_id = :project_id AND period_id = :period_id
                """),
                {"project_id": project_id, "period_id": period_id},
            ).mappings().first()
            
            if row and row["total"] is not None:
                return Decimal(str(row["total"]))
            return Decimal("0")
    except Exception:
        # Table might not exist if migration not applied
        return Decimal("0")
