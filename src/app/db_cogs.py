"""Database helpers for COGS Direct Rules.

This module provides CRUD, coverage, missing-SKUs, price-sources availability,
and get_price_for_source for cogs_direct_rules.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from sqlalchemy import text

from app.db import engine

SENTINEL_ALL = "__ALL__"
PERCENT_THRESHOLD = 0.01  # 1% for internal RRP availability


def _chunked(iterable: List[Dict[str, Any]], size: int) -> Iterator[List[Dict[str, Any]]]:
    """Yield lists of up to `size` elements from `iterable`."""
    if size <= 0:
        raise ValueError("size must be a positive integer")
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


def _get_latest_internal_snapshot_id(project_id: int) -> Optional[int]:
    """Latest internal snapshot: status IN ('success','partial'), ORDER BY imported_at DESC."""
    sql = text(
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
        row = conn.execute(sql, {"project_id": project_id}).mappings().fetchone()
    return int(row["id"]) if row else None


def get_min_period_start_with_reports(project_id: int) -> Optional[date]:
    """Get minimum period date_from for periods with successful tax statements.
    
    Uses tax_statement_snapshots with status='success' as indicator of "periods with report data".
    
    Returns:
        date_from of earliest period with data, or None if no periods found.
    """
    sql = text(
        """
        SELECT MIN(p.date_from) AS min_period_start
        FROM periods p
        INNER JOIN tax_statement_snapshots tss 
            ON tss.period_id = p.id
        WHERE tss.project_id = :project_id
          AND tss.status = 'success'
          AND tss.version = (
              SELECT MAX(version)
              FROM tax_statement_snapshots
              WHERE project_id = tss.project_id
                AND period_id = tss.period_id
          )
        """
    )
    with engine.connect() as conn:
        row = conn.execute(sql, {"project_id": project_id}).mappings().fetchone()
    if row and row["min_period_start"]:
        return row["min_period_start"]
    return None


def _is_first_rule_for_scope(
    conn,
    project_id: int,
    applies_to: str,
    internal_sku: str,
) -> bool:
    """Check if this is the first rule for the given scope.
    
    Scope is (project_id, applies_to, internal_sku).
    Returns True if no existing rules exist for this scope.
    """
    sql = text(
        """
        SELECT 1
        FROM cogs_direct_rules
        WHERE project_id = :project_id
          AND applies_to = :applies_to
          AND internal_sku = :internal_sku
        LIMIT 1
        """
    )
    row = conn.execute(
        sql,
        {
            "project_id": project_id,
            "applies_to": applies_to,
            "internal_sku": internal_sku,
        },
    ).fetchone()
    return row is None


def get_price_sources_availability(project_id: int) -> Dict[str, Any]:
    """Return availability and stats for internal_catalog_rrp and wb_admin_price."""
    snapshot_id = _get_latest_internal_snapshot_id(project_id)
    internal: Dict[str, Any] = {
        "code": "internal_catalog_rrp",
        "title": "Цена из каталога (Internal Data)",
        "description": "RRP из internal_product_prices.rrp последнего валидного снапшота",
        "available": False,
        "stats": {
            "total_skus": 0,
            "with_price": 0,
            "coverage_pct": 0.0,
            "last_snapshot_imported_at": None,
        },
    }
    wb: Dict[str, Any] = {
        "code": "wb_admin_price",
        "title": "Цена из админки WB",
        "description": "price_snapshots.wb_price (discounts-prices API)",
        "available": False,
        "stats": {"rows": 0, "last_at": None},
    }

    if snapshot_id is not None:
        snap_sql = text(
            "SELECT imported_at FROM internal_data_snapshots WHERE id = :sid"
        )
        with engine.connect() as conn:
            snap_row = conn.execute(snap_sql, {"sid": snapshot_id}).mappings().fetchone()
        last_imported = snap_row["imported_at"] if snap_row else None
        internal["stats"]["last_snapshot_imported_at"] = (
            last_imported.isoformat() if last_imported and hasattr(last_imported, "isoformat") else None
        )

        agg_sql = text(
            """
            SELECT
                COUNT(DISTINCT ip.internal_sku) AS total,
                COUNT(DISTINCT CASE WHEN ipp.rrp IS NOT NULL THEN ip.internal_sku END) AS with_price
            FROM internal_products ip
            LEFT JOIN internal_product_prices ipp
                ON ipp.internal_product_id = ip.id AND ipp.snapshot_id = ip.snapshot_id
            WHERE ip.project_id = :project_id AND ip.snapshot_id = :snapshot_id
            """
        )
        with engine.connect() as conn:
            agg = conn.execute(
                agg_sql, {"project_id": project_id, "snapshot_id": snapshot_id}
            ).mappings().fetchone()
        total = int(agg["total"] or 0)
        with_price = int(agg["with_price"] or 0)
        internal["stats"]["total_skus"] = total
        internal["stats"]["with_price"] = with_price
        internal["stats"]["coverage_pct"] = (
            round((with_price / total) * 100.0, 2) if total else 0.0
        )
        internal["available"] = total > 0 and (with_price / total) >= PERCENT_THRESHOLD

    wb_sql = text(
        """
        SELECT COUNT(*) AS rows, MAX(created_at) AS last_at
        FROM price_snapshots
        WHERE project_id = :project_id
        """
    )
    with engine.connect() as conn:
        wb_row = conn.execute(wb_sql, {"project_id": project_id}).mappings().fetchone()
    cnt = int(wb_row["rows"] or 0)
    last_at = wb_row["last_at"]
    wb["stats"]["rows"] = cnt
    wb["stats"]["last_at"] = (
        last_at.isoformat() if last_at and hasattr(last_at, "isoformat") else None
    )
    wb["available"] = cnt > 0

    return {
        "available_sources": [internal, wb],
    }


def _validate_bulk_row(
    row: Dict[str, Any],
    index: int,
    *,
    allowed_price_source_codes: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Validate and normalize a single bulk upsert row. Raises ValueError on invalid."""
    applies_to = (row.get("applies_to") or "sku").strip().lower()
    if applies_to not in ("sku", "all"):
        raise ValueError(f"Row {index}: applies_to must be 'sku' or 'all'; got {applies_to!r}")
    if applies_to == "all":
        internal_sku = SENTINEL_ALL
        if row.get("internal_sku") and (row.get("internal_sku") or "").strip() and (row.get("internal_sku") or "").strip() != SENTINEL_ALL:
            raise ValueError(f"Row {index}: applies_to='all' requires internal_sku='{SENTINEL_ALL}' or empty")
    else:
        internal_sku = (row.get("internal_sku") or "").strip()
        if not internal_sku:
            raise ValueError(f"Row {index}: internal_sku is required when applies_to='sku'")
        if internal_sku == SENTINEL_ALL:
            raise ValueError(f"Row {index}: internal_sku must not be '{SENTINEL_ALL}' when applies_to='sku'")

    mode = row.get("mode") or "fixed"
    allowed_modes = ("fixed", "percent_of_price", "percent_of_rrp", "percent_of_selling_price")
    if mode not in allowed_modes:
        raise ValueError(f"Row {index}: mode must be one of {allowed_modes}; got {mode!r}")

    raw_value = row.get("value")
    if raw_value is None:
        raise ValueError(f"Row {index}: value is required")
    try:
        value = Decimal(str(raw_value))
    except Exception as e:
        raise ValueError(f"Row {index}: value must be numeric; {e}") from e
    if value < 0:
        raise ValueError(f"Row {index}: value must be >= 0; got {value}")
    is_percent = mode in ("percent_of_price", "percent_of_rrp", "percent_of_selling_price")
    if is_percent and value > 100:
        raise ValueError(f"Row {index}: for percent modes value must be 0..100; got {value}")

    valid_from = row.get("valid_from")
    if valid_from is None:
        raise ValueError(f"Row {index}: valid_from is required")
    if isinstance(valid_from, str):
        valid_from = date.fromisoformat(valid_from)
    elif not isinstance(valid_from, date):
        raise ValueError(f"Row {index}: valid_from must be date or ISO string")

    valid_to = row.get("valid_to")
    if valid_to is not None:
        if isinstance(valid_to, str):
            valid_to = date.fromisoformat(valid_to)
        if valid_to < valid_from:
            raise ValueError(f"Row {index}: valid_to must be >= valid_from")

    meta_json = row.get("meta_json")
    if meta_json is None:
        meta_json = {}

    price_source_code = row.get("price_source_code")
    if mode == "percent_of_price":
        if not price_source_code or not str(price_source_code).strip():
            raise ValueError(f"Row {index}: price_source_code is required for mode percent_of_price")
        price_source_code = str(price_source_code).strip()
        if allowed_price_source_codes is not None and price_source_code not in allowed_price_source_codes:
            raise ValueError(
                f"Row {index}: price_source_code must be one of available sources; got {price_source_code!r}"
            )
    else:
        price_source_code = None

    currency = row.get("currency")
    if mode == "fixed":
        if not currency or not str(currency).strip():
            currency = "RUB"
        else:
            currency = str(currency).strip()
    else:
        currency = None

    return {
        "internal_sku": internal_sku,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "applies_to": "all" if applies_to == "all" else "sku",
        "mode": mode,
        "value": value,
        "currency": currency,
        "price_source_code": price_source_code,
        "meta_json": meta_json,
    }


def get_cogs_direct_rules(
    project_id: int,
    search: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    """Return paginated list of cogs_direct_rules and total count.

    Sorted by internal_sku ASC, valid_from DESC. Includes applies_to, price_source_code.
    """
    search_clause = ""
    params: Dict[str, Any] = {"project_id": project_id, "limit": limit, "offset": offset}
    if search and search.strip():
        search_clause = " AND internal_sku ILIKE :search"
        params["search"] = f"%{search.strip()}%"

    select_sql = text(
        f"""
        SELECT
            id,
            project_id,
            internal_sku,
            valid_from,
            valid_to,
            applies_to,
            mode,
            value,
            currency,
            price_source_code,
            meta_json,
            created_at,
            updated_at
        FROM cogs_direct_rules
        WHERE project_id = :project_id
        {search_clause}
        ORDER BY internal_sku ASC, valid_from DESC
        LIMIT :limit OFFSET :offset
        """
    )
    count_sql = text(
        f"""
        SELECT COUNT(*) AS cnt
        FROM cogs_direct_rules
        WHERE project_id = :project_id
        {search_clause}
        """
    )

    with engine.connect() as conn:
        rows_result = conn.execute(select_sql, params).mappings().all()
        rows = [dict(r) for r in rows_result]
        count_result = conn.execute(count_sql, params)
        total = int(count_result.scalar_one() or 0)
    return (rows, total)


def upsert_cogs_direct_rules_bulk(
    project_id: int,
    rows: List[Dict[str, Any]],
    *,
    allowed_price_source_codes: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """Bulk upsert cogs_direct_rules. Validates each row; collects errors. Returns inserted, updated, failed, errors, adjustments.
    
    Business rule: For the FIRST rule per scope (project_id, applies_to, internal_sku),
    automatically adjust valid_from backward to min_period_start_with_reports if needed.
    """
    if not rows:
        return {"inserted": 0, "updated": 0, "failed": 0, "errors": [], "adjustments": []}

    validated: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for i, r in enumerate(rows):
        try:
            validated.append(
                _validate_bulk_row(
                    r, i, allowed_price_source_codes=allowed_price_source_codes
                )
            )
        except ValueError as e:
            errors.append({
                "row_index": i,
                "message": str(e),
                "internal_sku": (r.get("internal_sku") or "").strip() or "(all)",
            })

    if errors:
        return {
            "inserted": 0,
            "updated": 0,
            "failed": len(rows),
            "errors": errors,
            "adjustments": [],
        }

    # Get min_period_start_with_reports once for the project (cached in transaction)
    min_period_start: Optional[date] = None
    
    exists_sql = text(
        """
        SELECT 1 FROM cogs_direct_rules
        WHERE project_id = :project_id AND internal_sku = :internal_sku AND valid_from = :valid_from
        LIMIT 1
        """
    )
    insert_sql = text(
        """
        INSERT INTO cogs_direct_rules (
            project_id,
            internal_sku,
            valid_from,
            valid_to,
            applies_to,
            mode,
            value,
            currency,
            price_source_code,
            meta_json
        )
        VALUES (
            :project_id,
            :internal_sku,
            :valid_from,
            :valid_to,
            :applies_to,
            :mode,
            :value,
            :currency,
            :price_source_code,
            CAST(:meta_json AS jsonb)
        )
        ON CONFLICT (project_id, internal_sku, valid_from) DO UPDATE SET
            valid_to = EXCLUDED.valid_to,
            applies_to = EXCLUDED.applies_to,
            mode = EXCLUDED.mode,
            value = EXCLUDED.value,
            currency = EXCLUDED.currency,
            price_source_code = EXCLUDED.price_source_code,
            meta_json = EXCLUDED.meta_json,
            updated_at = now()
        """
    )

    inserted = 0
    updated = 0
    adjustments: List[Dict[str, Any]] = []
    # Track scopes that already got their first rule in this transaction
    first_rule_scopes: Set[Tuple[str, str]] = set()
    
    with engine.begin() as conn:
        # Cache min_period_start for the transaction
        min_period_start = get_min_period_start_with_reports(project_id)
        
        for idx, r in enumerate(validated):
            try:
                user_valid_from = r["valid_from"]
                adjusted_valid_from = user_valid_from
                
                scope_key = (r["applies_to"], r["internal_sku"])
                
                # Check if this is the first rule for this scope (in DB or already processed in this transaction)
                is_first_in_db = _is_first_rule_for_scope(
                    conn, project_id, r["applies_to"], r["internal_sku"]
                )
                is_first_in_tx = scope_key not in first_rule_scopes
                is_first = is_first_in_db and is_first_in_tx
                
                # Auto-adjust valid_from for first rule
                if is_first and min_period_start is not None:
                    if min_period_start < user_valid_from:
                        adjusted_valid_from = min_period_start
                        adjustments.append({
                            "row_index": idx,
                            "internal_sku": r["internal_sku"],
                            "applies_to": r["applies_to"],
                            "original_valid_from": user_valid_from.isoformat(),
                            "adjusted_valid_from": adjusted_valid_from.isoformat(),
                        })
                
                # Mark this scope as having a first rule (if it was first)
                if is_first:
                    first_rule_scopes.add(scope_key)
                
                # Check if rule with this exact valid_from already exists (before adjustment)
                ex = conn.execute(
                    exists_sql,
                    {
                        "project_id": project_id,
                        "internal_sku": r["internal_sku"],
                        "valid_from": adjusted_valid_from,
                    },
                ).fetchone()
                
                # Use adjusted_valid_from for insert
                conn.execute(
                    insert_sql,
                    {
                        "project_id": project_id,
                        "internal_sku": r["internal_sku"],
                        "valid_from": adjusted_valid_from,
                        "valid_to": r["valid_to"],
                        "applies_to": r["applies_to"],
                        "mode": r["mode"],
                        "value": r["value"],
                        "currency": r["currency"],
                        "price_source_code": r["price_source_code"],
                        "meta_json": json.dumps(r["meta_json"], ensure_ascii=False),
                    },
                )
                if ex:
                    updated += 1
                else:
                    inserted += 1
            except Exception as e:
                errors.append({
                    "row_index": idx,
                    "message": str(e),
                    "internal_sku": r["internal_sku"],
                })

    return {
        "inserted": inserted,
        "updated": updated,
        "failed": len(errors),
        "errors": errors,
        "adjustments": adjustments,
    }


def delete_cogs_direct_rule(project_id: int, rule_id: int) -> bool:
    """Delete a single rule by id. Must belong to project_id. Returns True if deleted."""
    sql = text(
        """
        DELETE FROM cogs_direct_rules
        WHERE project_id = :project_id AND id = :rule_id
        """
    )
    with engine.begin() as conn:
        result = conn.execute(sql, {"project_id": project_id, "rule_id": rule_id})
        return result.rowcount > 0


def _has_active_default_rule(project_id: int, as_of: date) -> bool:
    """True if there exists an active default rule (applies_to=all, __ALL__) on as_of."""
    sql = text(
        """
        SELECT 1
        FROM cogs_direct_rules
        WHERE project_id = :project_id
          AND applies_to = 'all'
          AND internal_sku = :sentinel
          AND valid_from <= :d
          AND (valid_to IS NULL OR valid_to >= :d)
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(
            sql,
            {"project_id": project_id, "sentinel": SENTINEL_ALL, "d": as_of},
        ).fetchone()
    return row is not None


def get_cogs_coverage(project_id: int, as_of_date: Optional[date] = None) -> Dict[str, Any]:
    """Coverage stats: internal_data_available, internal_skus_total, covered_total, missing_total, coverage_pct.

    Uses latest snapshot (success/partial, imported_at DESC). as_of_date defaults to today.
    """
    if as_of_date is None:
        as_of_date = datetime.now(timezone.utc).date()
    snapshot_id = _get_latest_internal_snapshot_id(project_id)
    if snapshot_id is None:
        return {
            "internal_data_available": False,
            "internal_skus_total": 0,
            "covered_total": 0,
            "missing_total": 0,
            "coverage_pct": 0.0,
        }

    total_sql = text(
        """
        SELECT COUNT(DISTINCT internal_sku) AS cnt
        FROM internal_products
        WHERE project_id = :project_id AND snapshot_id = :snapshot_id
        """
    )
    with engine.connect() as conn:
        tot_row = conn.execute(
            total_sql, {"project_id": project_id, "snapshot_id": snapshot_id}
        ).mappings().fetchone()
    total = int(tot_row["cnt"] or 0)
    if total == 0:
        return {
            "internal_data_available": True,
            "internal_skus_total": 0,
            "covered_total": 0,
            "missing_total": 0,
            "coverage_pct": 0.0,
        }

    if _has_active_default_rule(project_id, as_of_date):
        return {
            "internal_data_available": True,
            "internal_skus_total": total,
            "covered_total": total,
            "missing_total": 0,
            "coverage_pct": 100.0,
        }

    covered_sql = text(
        """
        SELECT COUNT(DISTINCT ip.internal_sku) AS cnt
        FROM internal_products ip
        WHERE ip.project_id = :project_id
          AND ip.snapshot_id = :snapshot_id
          AND EXISTS (
            SELECT 1 FROM cogs_direct_rules r
            WHERE r.project_id = :project_id
              AND r.applies_to = 'sku'
              AND r.internal_sku = ip.internal_sku
              AND r.valid_from <= :d
              AND (r.valid_to IS NULL OR r.valid_to >= :d)
          )
        """
    )
    with engine.connect() as conn:
        cov_row = conn.execute(
            covered_sql,
            {"project_id": project_id, "snapshot_id": snapshot_id, "d": as_of_date},
        ).mappings().fetchone()
    covered = int(cov_row["cnt"] or 0)
    missing = total - covered
    pct = round((covered / total) * 100.0, 2) if total else 0.0
    return {
        "internal_data_available": True,
        "internal_skus_total": total,
        "covered_total": covered,
        "missing_total": missing,
        "coverage_pct": pct,
    }


def get_cogs_missing_skus(
    project_id: int,
    as_of_date: Optional[date] = None,
    limit: int = 200,
    offset: int = 0,
    q: Optional[str] = None,
) -> Dict[str, Any]:
    """Return internal_skus from latest snapshot that have no active sku-rule on as_of_date.

    If no snapshot or active default rule, returns empty. Uses NOT EXISTS for scale.
    """
    if as_of_date is None:
        as_of_date = datetime.now(timezone.utc).date()
    snapshot_id = _get_latest_internal_snapshot_id(project_id)
    if snapshot_id is None:
        return {"internal_data_available": False, "total": 0, "items": []}
    if _has_active_default_rule(project_id, as_of_date):
        return {"internal_data_available": True, "total": 0, "items": []}

    search_clause = ""
    params: Dict[str, Any] = {
        "project_id": project_id,
        "snapshot_id": snapshot_id,
        "d": as_of_date,
        "limit": limit,
        "offset": offset,
    }
    if q and str(q).strip():
        search_clause = " AND ip.internal_sku ILIKE :q || '%'"
        params["q"] = str(q).strip()

    count_sql = text(
        f"""
        SELECT COUNT(*) AS cnt
        FROM internal_products ip
        WHERE ip.project_id = :project_id AND ip.snapshot_id = :snapshot_id
          AND NOT EXISTS (
            SELECT 1 FROM cogs_direct_rules r
            WHERE r.project_id = :project_id
              AND r.applies_to = 'sku'
              AND r.internal_sku = ip.internal_sku
              AND r.valid_from <= :d
              AND (r.valid_to IS NULL OR r.valid_to >= :d)
          )
        {search_clause}
        """
    )
    list_sql = text(
        f"""
        SELECT ip.internal_sku
        FROM internal_products ip
        WHERE ip.project_id = :project_id AND ip.snapshot_id = :snapshot_id
          AND NOT EXISTS (
            SELECT 1 FROM cogs_direct_rules r
            WHERE r.project_id = :project_id
              AND r.applies_to = 'sku'
              AND r.internal_sku = ip.internal_sku
              AND r.valid_from <= :d
              AND (r.valid_to IS NULL OR r.valid_to >= :d)
          )
        {search_clause}
        ORDER BY ip.internal_sku ASC
        LIMIT :limit OFFSET :offset
        """
    )

    with engine.connect() as conn:
        total = int(conn.execute(count_sql, params).scalar_one() or 0)
        rows = conn.execute(list_sql, params).mappings().fetchall()
    items = [{"internal_sku": r["internal_sku"]} for r in rows]
    return {
        "internal_data_available": True,
        "total": total,
        "items": items,
    }


def get_price_for_source(
    project_id: int,
    internal_sku: str,
    source_code: str,
    as_of_date: date,
) -> Optional[Decimal]:
    """Return price for (project, internal_sku, source_code) as of date, or None.

    internal_catalog_rrp: latest internal snapshot -> internal_product_prices.rrp.
    wb_admin_price: internal_sku -> nm_id via identifiers (marketplace_item_id or marketplace_sku->products) -> latest price_snapshots.wb_price.
    """
    snapshot_id = _get_latest_internal_snapshot_id(project_id)
    if snapshot_id is None:
        return None

    if source_code == "internal_catalog_rrp":
        sql = text(
            """
            SELECT ipp.rrp
            FROM internal_products ip
            JOIN internal_product_prices ipp
                ON ipp.internal_product_id = ip.id AND ipp.snapshot_id = ip.snapshot_id
            WHERE ip.project_id = :project_id
              AND ip.snapshot_id = :snapshot_id
              AND ip.internal_sku = :internal_sku
              AND ipp.rrp IS NOT NULL
            LIMIT 1
            """
        )
        with engine.connect() as conn:
            row = conn.execute(
                sql,
                {"project_id": project_id, "snapshot_id": snapshot_id, "internal_sku": internal_sku},
            ).mappings().fetchone()
        return Decimal(str(row["rrp"])) if row else None

    if source_code == "wb_admin_price":
        ident_sql = text(
            """
            SELECT idi.marketplace_item_id, idi.marketplace_sku
            FROM internal_products ip
            JOIN internal_product_identifiers idi
                ON idi.internal_product_id = ip.id AND idi.snapshot_id = ip.snapshot_id
            WHERE ip.project_id = :project_id
              AND ip.snapshot_id = :snapshot_id
              AND ip.internal_sku = :internal_sku
              AND idi.marketplace_code = 'wildberries'
            LIMIT 1
            """
        )
        with engine.connect() as conn:
            ident = conn.execute(
                ident_sql,
                {"project_id": project_id, "snapshot_id": snapshot_id, "internal_sku": internal_sku},
            ).mappings().fetchone()
        nm_id: Optional[int] = None
        if ident:
            if ident["marketplace_item_id"]:
                try:
                    nm_id = int(str(ident["marketplace_item_id"]).strip())
                except (TypeError, ValueError):
                    pass
            if nm_id is None and ident["marketplace_sku"]:
                fallback_sql = text(
                    """
                    SELECT nm_id FROM products
                    WHERE project_id = :project_id AND vendor_code = :vc
                    LIMIT 1
                    """
                )
                try:
                    with engine.connect() as c2:
                        p = c2.execute(
                            fallback_sql,
                            {"project_id": project_id, "vc": str(ident["marketplace_sku"]).strip()},
                        ).mappings().fetchone()
                    if p:
                        nm_id = int(p["nm_id"])
                except Exception:
                    pass
        if nm_id is None:
            return None
        price_sql = text(
            """
            SELECT wb_price
            FROM price_snapshots
            WHERE project_id = :project_id AND nm_id = :nm_id
            ORDER BY created_at DESC
            LIMIT 1
            """
        )
        with engine.connect() as conn:
            row = conn.execute(
                price_sql, {"project_id": project_id, "nm_id": nm_id}
            ).mappings().fetchone()
        return Decimal(str(row["wb_price"])) if row and row["wb_price"] is not None else None

    return None
