"""DB layer for wb_sku_pnl_snapshots.

All functions accept conn (connection/transaction) - no internal engine.begin().
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.services.wb_financial.sku_pnl_metrics import (
    compute_unit_metrics,
    safe_div,
    wb_total_total_abs,
)

_DEBUG_LOG_PATH = r"d:\Work\EcomCore\.cursor\debug.log"


def _dbg(hypothesis_id: str, location: str, message: str, data: Dict[str, Any], run_id: str = "pre-fix") -> None:
    # NOTE: debug-mode NDJSON logger. Do not log secrets.
    try:
        import json
        import time

        payload = {
            "sessionId": "debug-session",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass

BATCH_SIZE = 2000

def delete_snapshot(
    conn: Connection,
    project_id: int,
    period_from: date,
    period_to: date,
    version: int,
) -> int:
    """Delete existing snapshot rows. Returns deleted count."""
    # Delete sources first (FK would block or we have no FK to snapshot row)
    conn.execute(
        text("""
            DELETE FROM wb_sku_pnl_snapshot_sources
            WHERE project_id = :project_id
              AND period_from = :period_from
              AND period_to = :period_to
              AND version = :version
        """),
        {"project_id": project_id, "period_from": period_from, "period_to": period_to, "version": version},
    )
    result = conn.execute(
        text("""
            DELETE FROM wb_sku_pnl_snapshots
            WHERE project_id = :project_id
              AND period_from = :period_from
              AND period_to = :period_to
              AND version = :version
        """),
        {"project_id": project_id, "period_from": period_from, "period_to": period_to, "version": version},
    )
    return result.rowcount or 0


def delete_snapshot_sources(
    conn: Connection,
    project_id: int,
    period_from: date,
    period_to: date,
    version: int,
) -> int:
    """Delete source rows for a snapshot. Returns deleted count."""
    result = conn.execute(
        text("""
            DELETE FROM wb_sku_pnl_snapshot_sources
            WHERE project_id = :project_id
              AND period_from = :period_from
              AND period_to = :period_to
              AND version = :version
        """),
        {"project_id": project_id, "period_from": period_from, "period_to": period_to, "version": version},
    )
    return result.rowcount or 0


SOURCES_BATCH_SIZE = 500


def bulk_insert_sources(
    conn: Connection,
    rows: List[Dict[str, Any]],
) -> int:
    """Bulk insert snapshot source rows. Returns inserted count."""
    if not rows:
        return 0
    total = 0
    for i in range(0, len(rows), SOURCES_BATCH_SIZE):
        batch = rows[i : i + SOURCES_BATCH_SIZE]
        values = []
        params: Dict[str, Any] = {}
        for j, r in enumerate(batch):
            prefix = f"r{j}_"
            values.append(
                f"(:{prefix}project_id, :{prefix}period_from, :{prefix}period_to, :{prefix}internal_sku, "
                f":{prefix}version, :{prefix}report_id, :{prefix}report_period_from, :{prefix}report_period_to, "
                f":{prefix}report_type, :{prefix}rows_count, :{prefix}amount_total)"
            )
            params[prefix + "project_id"] = r["project_id"]
            params[prefix + "period_from"] = r["period_from"]
            params[prefix + "period_to"] = r["period_to"]
            params[prefix + "internal_sku"] = r["internal_sku"]
            params[prefix + "version"] = r["version"]
            params[prefix + "report_id"] = r["report_id"]
            params[prefix + "report_period_from"] = r.get("report_period_from")
            params[prefix + "report_period_to"] = r.get("report_period_to")
            params[prefix + "report_type"] = r.get("report_type", "Реализация")
            params[prefix + "rows_count"] = r["rows_count"]
            params[prefix + "amount_total"] = r["amount_total"]
        sql = f"""
            INSERT INTO wb_sku_pnl_snapshot_sources (
                project_id, period_from, period_to, internal_sku, version,
                report_id, report_period_from, report_period_to, report_type,
                rows_count, amount_total
            ) VALUES {", ".join(values)}
        """
        conn.execute(text(sql), params)
        total += len(batch)
    return total


def get_sources_for_skus(
    conn: Connection,
    project_id: int,
    period_from: date,
    period_to: date,
    version: int,
    internal_skus: List[str],
) -> Dict[str, List[Dict[str, Any]]]:
    """Get sources grouped by internal_sku. Returns { internal_sku: [ {...}, ... ] }."""
    if not internal_skus:
        return {}
    out: Dict[str, List[Dict[str, Any]]] = {sku: [] for sku in internal_skus}
    # Query in chunks to avoid huge IN list
    for i in range(0, len(internal_skus), 200):
        chunk = internal_skus[i : i + 200]
        placeholders = ", ".join(f":sku_{k}" for k in range(len(chunk)))
        params: Dict[str, Any] = {
            "project_id": project_id,
            "period_from": period_from,
            "period_to": period_to,
            "version": version,
        }
        for k, sku in enumerate(chunk):
            params[f"sku_{k}"] = sku
        rows = conn.execute(
            text(f"""
                SELECT internal_sku, report_id, report_period_from, report_period_to,
                       report_type, rows_count, amount_total
                FROM wb_sku_pnl_snapshot_sources
                WHERE project_id = :project_id
                  AND period_from = :period_from
                  AND period_to = :period_to
                  AND version = :version
                  AND internal_sku IN ({placeholders})
                ORDER BY report_id
            """),
            params,
        ).mappings().all()
        for r in rows:
            sku = r["internal_sku"]
            out[sku].append({
                "report_id": int(r["report_id"]),
                "report_period_from": str(r["report_period_from"]) if r.get("report_period_from") else None,
                "report_period_to": str(r["report_period_to"]) if r.get("report_period_to") else None,
                "report_type": r.get("report_type") or "Реализация",
                "rows_count": int(r["rows_count"] or 0),
                "amount_total": float(r["amount_total"] or 0),
            })
    return out


def bulk_insert_snapshot_rows(
    conn: Connection,
    rows: List[Dict[str, Any]],
) -> int:
    """Bulk insert snapshot rows. Returns inserted count."""
    if not rows:
        return 0
    total = 0
    built_at = datetime.utcnow()
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        values = []
        params: Dict[str, Any] = {"built_at": built_at}
        for j, r in enumerate(batch):
            prefix = f"r{j}_"
            values.append(
                f"(:{prefix}project_id, :{prefix}period_from, :{prefix}period_to, :{prefix}internal_sku, "
                f":{prefix}currency, :{prefix}gmv, :{prefix}wb_commission_no_vat, :{prefix}wb_commission_vat, "
                f":{prefix}acquiring_fee, :{prefix}delivery_fee, :{prefix}rebill_logistics_cost, :{prefix}pvz_fee, "
                f":{prefix}net_before_cogs, :{prefix}net_payable_metric, :{prefix}wb_sales_commission_metric, "
                f":{prefix}events_count, :{prefix}quantity_sold, :built_at, :{prefix}version)"
            )
            params[prefix + "project_id"] = r["project_id"]
            params[prefix + "period_from"] = r["period_from"]
            params[prefix + "period_to"] = r["period_to"]
            params[prefix + "internal_sku"] = r["internal_sku"]
            params[prefix + "currency"] = r.get("currency", "RUB")
            params[prefix + "gmv"] = r["gmv"]
            params[prefix + "wb_commission_no_vat"] = r["wb_commission_no_vat"]
            params[prefix + "wb_commission_vat"] = r["wb_commission_vat"]
            params[prefix + "acquiring_fee"] = r["acquiring_fee"]
            params[prefix + "delivery_fee"] = r["delivery_fee"]
            params[prefix + "rebill_logistics_cost"] = r["rebill_logistics_cost"]
            params[prefix + "pvz_fee"] = r["pvz_fee"]
            params[prefix + "net_before_cogs"] = r["net_before_cogs"]
            params[prefix + "net_payable_metric"] = r["net_payable_metric"]
            params[prefix + "wb_sales_commission_metric"] = r["wb_sales_commission_metric"]
            params[prefix + "events_count"] = r["events_count"]
            params[prefix + "quantity_sold"] = r.get("quantity_sold", 0)
            params[prefix + "version"] = r.get("version", 1)
        sql = f"""
            INSERT INTO wb_sku_pnl_snapshots (
                project_id, period_from, period_to, internal_sku, currency,
                gmv, wb_commission_no_vat, wb_commission_vat,
                acquiring_fee, delivery_fee, rebill_logistics_cost, pvz_fee,
                net_before_cogs, net_payable_metric, wb_sales_commission_metric,
                events_count, quantity_sold, built_at, version
            ) VALUES {", ".join(values)}
        """
        conn.execute(text(sql), params)
        total += len(batch)
    return total


def list_snapshot_rows(
    conn: Connection,
    project_id: int,
    period_from: date,
    period_to: date,
    version: int,
    q: str | None,
    subject_id: int | None,
    sort: str,
    order: str,
    limit: int,
    offset: int,
) -> tuple[List[Dict[str, Any]], int]:
    """List snapshot rows with filters. Returns (rows, total_count)."""
    # region agent log
    _dbg(
        "H1",
        "db_wb_sku_pnl.py:list_snapshot_rows:entry",
        "Entering list_snapshot_rows",
        {
            "project_id": project_id,
            "period_from": str(period_from),
            "period_to": str(period_to),
            "version": version,
            "q_present": bool(q and q.strip()),
            "subject_id": subject_id,
            "sort": sort,
            "order": order,
            "limit": limit,
            "offset": offset,
        },
    )
    # endregion agent log
    where = """
        WHERE project_id = :project_id
          AND period_from = :period_from
          AND period_to = :period_to
          AND version = :version
    """
    params: Dict[str, Any] = {
        "project_id": project_id,
        "period_from": period_from,
        "period_to": period_to,
        "version": version,
    }

    if q and q.strip():
        where += " AND internal_sku ILIKE :q"
        params["q"] = f"%{q.strip()}%"

    if subject_id is not None:
        where += """
          AND internal_sku IN (
            SELECT vendor_code_norm
            FROM products
            WHERE project_id = :project_id
              AND vendor_code_norm IS NOT NULL
              AND subject_id = :subject_id
          )
        """
        params["subject_id"] = int(subject_id)

    # IMPORTANT: WB expenses can come with different signs depending on the source.
    # For all KPIs and sorting we normalize WB expenses as positive ABS values.
    wb_total_abs_sql = (
        "(ABS(COALESCE(wb_commission_no_vat,0)) + ABS(COALESCE(wb_commission_vat,0)) + "
        " ABS(COALESCE(delivery_fee,0)) + ABS(COALESCE(rebill_logistics_cost,0)) + ABS(COALESCE(pvz_fee,0)) + "
        " ABS(COALESCE(acquiring_fee,0)))"
    )
    net_before_cogs_norm_sql = f"(gmv - {wb_total_abs_sql})"

    sort_col = {
        "net_before_cogs": net_before_cogs_norm_sql,
        # Percent-of-revenue KPIs for sorting (returned as percent points from backend too)
        "net_before_cogs_pct": f"CASE WHEN gmv IS NULL OR gmv = 0 THEN NULL ELSE ({net_before_cogs_norm_sql} / gmv) END",
        "wb_total_pct": f"CASE WHEN gmv IS NULL OR gmv = 0 THEN NULL ELSE ({wb_total_abs_sql} / gmv) END",
        # keep legacy options
        "gmv": "gmv",
        "internal_sku": "internal_sku",
    }.get(sort, net_before_cogs_norm_sql)
    dir_sql = "DESC" if order.lower() == "desc" else "ASC"
    order_clause = f"ORDER BY {sort_col} {dir_sql}"

    # region agent log
    _dbg(
        "H1",
        "db_wb_sku_pnl.py:list_snapshot_rows:sql",
        "Computed order clause",
        {"order_clause": order_clause, "sort_col": sort_col},
    )
    # endregion agent log

    # COGS as-of date is period_to (end of selected period)
    # NOTE: We compute rrp_price and wb_price_admin (selling price) in batched CTEs based on the
    # paginated base_rows set, to avoid per-row LATERAL heavy joins.
    select_params = {
        **params,
        "limit": limit,
        "offset": offset,
        "as_of_date": period_to,
    }
    sql = f"""
            WITH base_rows AS (
                SELECT
                    s.internal_sku,
                    NULLIF(regexp_replace(trim(both '/' from s.internal_sku), '^.*/', ''), '') AS sku_norm,
                    s.quantity_sold,
                    s.gmv,
                    s.wb_commission_no_vat,
                    s.wb_commission_vat,
                    s.acquiring_fee,
                    s.delivery_fee,
                    s.rebill_logistics_cost,
                    s.pvz_fee,
                    s.net_before_cogs,
                    s.net_payable_metric,
                    s.wb_sales_commission_metric,
                    s.events_count
                FROM wb_sku_pnl_snapshots s
                {where}
                {order_clause}
                LIMIT :limit OFFSET :offset
            ),
            base_skus AS (
                SELECT DISTINCT sku_norm
                FROM base_rows
                WHERE sku_norm IS NOT NULL
            ),
            latest_internal_snapshot AS (
                SELECT id AS snapshot_id
                FROM internal_data_snapshots
                WHERE project_id = :project_id
                  AND status IN ('success', 'partial')
                ORDER BY imported_at DESC NULLS LAST
                LIMIT 1
            ),
            rrp_by_sku AS (
                -- internal_product_prices has no "as-of" timestamp, so we use a deterministic aggregate.
                -- If multiple internal_products normalize into the same sku_norm, we take MAX(rrp).
                SELECT
                    NULLIF(regexp_replace(trim(both '/' from ip.internal_sku), '^.*/', ''), '') AS sku_norm,
                    MAX(ipp.rrp) AS rrp_price
                FROM latest_internal_snapshot lis
                JOIN internal_products ip
                  ON ip.project_id = :project_id
                 AND ip.snapshot_id = lis.snapshot_id
                JOIN internal_product_prices ipp
                  ON ipp.internal_product_id = ip.id
                 AND ipp.snapshot_id = ip.snapshot_id
                WHERE ipp.rrp IS NOT NULL
                  AND NULLIF(regexp_replace(trim(both '/' from ip.internal_sku), '^.*/', ''), '') IN (
                      SELECT sku_norm FROM base_skus
                  )
                GROUP BY 1
            ),
            sku_to_nm AS (
                -- Deterministic mapping sku_norm -> nm_id: choose MIN(nm_id) if multiple products exist.
                SELECT
                    p.vendor_code_norm AS sku_norm,
                    MIN(p.nm_id) AS nm_id
                FROM products p
                JOIN base_skus b ON b.sku_norm = p.vendor_code_norm
                WHERE p.project_id = :project_id
                  AND p.nm_id IS NOT NULL
                GROUP BY p.vendor_code_norm
            ),
            src_for_page AS (
                -- Limit sources to just SKUs on this page, matched by normalized key.
                SELECT
                    NULLIF(regexp_replace(trim(both '/' from src.internal_sku), '^.*/', ''), '') AS sku_norm,
                    src.report_id
                FROM wb_sku_pnl_snapshot_sources src
                WHERE src.project_id = :project_id
                  AND src.period_from = :period_from
                  AND src.period_to = :period_to
                  AND src.version = :version
                  AND NULLIF(regexp_replace(trim(both '/' from src.internal_sku), '^.*/', ''), '') IN (
                      SELECT sku_norm FROM base_skus
                  )
            ),
            selling_price_by_sku AS (
                -- Batched AVG(retail_price) per sku_norm for the current page only.
                SELECT
                    sfp.sku_norm,
                    AVG(
                        NULLIF(
                            CASE
                                WHEN (r.payload->>'retail_price') ~ '^-?[0-9]+(\\.[0-9]+)?$'
                                    THEN (r.payload->>'retail_price')::numeric
                                ELSE NULL
                            END,
                            0
                        )
                    ) AS wb_price_admin
                FROM src_for_page sfp
                JOIN sku_to_nm sn ON sn.sku_norm = sfp.sku_norm
                JOIN wb_finance_report_lines r
                  ON r.project_id = :project_id
                 AND r.report_id = sfp.report_id
                 AND (
                    CASE
                        WHEN COALESCE(r.payload->>'nm_id', r.payload->>'nmId') ~ '^[0-9]+$'
                            THEN COALESCE(r.payload->>'nm_id', r.payload->>'nmId')::bigint
                        ELSE NULL
                    END
                 ) = sn.nm_id
                GROUP BY sfp.sku_norm
            ),
            with_prices AS (
                SELECT
                    b.*,
                    rrp.rrp_price,
                    sp.wb_price_admin
                FROM base_rows b
                LEFT JOIN rrp_by_sku rrp
                  ON rrp.sku_norm = b.sku_norm
                LEFT JOIN selling_price_by_sku sp
                  ON sp.sku_norm = b.sku_norm
            ),
            with_rule AS (
                SELECT
                    wp.*,
                    CASE
                        WHEN rule.mode = 'fixed' THEN rule.value
                        WHEN rule.mode = 'percent_of_price'
                             AND rule.price_source_code IN ('internal_catalog_rrp')
                             AND wp.rrp_price IS NOT NULL
                            THEN (wp.rrp_price * rule.value / 100)
                        WHEN rule.mode = 'percent_of_rrp'
                             AND wp.rrp_price IS NOT NULL
                            THEN (wp.rrp_price * rule.value / 100)
                        WHEN rule.mode = 'percent_of_selling_price'
                             AND wp.wb_price_admin IS NOT NULL
                            THEN (wp.wb_price_admin * rule.value / 100)
                        ELSE NULL
                    END AS cogs_per_unit
                FROM with_prices wp
                LEFT JOIN LATERAL (
                    SELECT r.mode, r.value, r.price_source_code
                    FROM cogs_direct_rules r
                    WHERE r.project_id = :project_id
                      AND r.valid_from <= :as_of_date
                      AND (r.valid_to IS NULL OR r.valid_to >= :as_of_date)
                      AND (
                        (
                          r.applies_to = 'sku'
                          AND NULLIF(regexp_replace(trim(both '/' from r.internal_sku), '^.*/', ''), '') = wp.sku_norm
                        )
                        OR
                        (
                          r.applies_to = 'all'
                          AND r.internal_sku = '__ALL__'
                        )
                      )
                    ORDER BY
                        CASE WHEN r.applies_to = 'sku' THEN 0 ELSE 1 END,
                        r.valid_from DESC
                    LIMIT 1
                ) rule ON true
            )
            SELECT
                internal_sku,
                quantity_sold,
                gmv,
                wb_commission_no_vat,
                wb_commission_vat,
                acquiring_fee,
                delivery_fee,
                rebill_logistics_cost,
                pvz_fee,
                net_payable_metric,
                wb_sales_commission_metric,
                events_count,
                wb_price_admin,
                rrp_price,
                cogs_per_unit
            FROM with_rule
            """
    try:
        rows = conn.execute(text(sql), select_params).mappings().all()
    except Exception as e:
        # region agent log
        _dbg(
            "H1",
            "db_wb_sku_pnl.py:list_snapshot_rows:sql_error",
            "SQL execution failed",
            {
                "error": str(e),
                "sql_tail": sql[-220:],
            },
        )
        # endregion agent log
        raise

    count_row = conn.execute(
        text(f"SELECT COUNT(*) AS c FROM wb_sku_pnl_snapshots {where}"),
        params,
    ).mappings().first()
    total_count = int(count_row["c"]) if count_row else 0

    def _d(v: object) -> Decimal:
        # Keep decimals stable across float inputs
        return Decimal(str(v or 0))

    def _pct_points(n: Decimal, d: Decimal) -> Optional[Decimal]:
        v = safe_div(n, d)
        if v is None:
            return None
        return v * Decimal("100")

    out: List[Dict[str, Any]] = []
    for r in rows:
        qty = int(r.get("quantity_sold") or 0)
        gmv = float(r.get("gmv") or 0)
        gmv_d = _d(gmv)

        # WB cost components normalized to positive values (ABS).
        wb_comm_no_vat = float(abs(r.get("wb_commission_no_vat") or 0))
        wb_comm_vat = float(abs(r.get("wb_commission_vat") or 0))
        acquiring_fee = float(abs(r.get("acquiring_fee") or 0))
        delivery_fee = float(abs(r.get("delivery_fee") or 0))
        rebill_logistics_cost = float(abs(r.get("rebill_logistics_cost") or 0))
        pvz_fee = float(abs(r.get("pvz_fee") or 0))

        wb_total_total_d = wb_total_total_abs(
            wb_commission_no_vat=wb_comm_no_vat,
            wb_commission_vat=wb_comm_vat,
            acquiring_fee=acquiring_fee,
            delivery_fee=delivery_fee,
            rebill_logistics_cost=rebill_logistics_cost,
            pvz_fee=pvz_fee,
        )
        wb_total_total = float(wb_total_total_d)
        net_before_cogs_total_d = gmv_d - wb_total_total_d

        # Unit values
        avg_price_realization_unit = safe_div(gmv_d, Decimal(qty)) if qty > 0 else None
        wb_total_unit = safe_div(wb_total_total_d, Decimal(qty)) if qty > 0 else None

        rrp_price = float(r["rrp_price"]) if r.get("rrp_price") is not None else None
        cogs_unit = r.get("cogs_per_unit")  # Decimal | None

        unit_metrics = compute_unit_metrics(
            avg_price_realization_unit=avg_price_realization_unit,
            wb_total_unit=wb_total_unit,
            cogs_unit=cogs_unit,
            rrp=rrp_price,
        )

        cogs_total = (cogs_unit * Decimal(qty)) if (cogs_unit is not None and qty > 0) else None
        product_profit = (net_before_cogs_total_d - cogs_total) if (cogs_total is not None) else None
        product_margin_pct = (
            _pct_points(product_profit, gmv_d) if (product_profit is not None and gmv_d > 0) else None
        )
        net_before_cogs_pct = _pct_points(net_before_cogs_total_d, gmv_d) if gmv_d > 0 else None
        wb_total_pct = _pct_points(wb_total_total_d, gmv_d) if gmv_d > 0 else None

        cogs_missing = cogs_unit is None
        wb_comm = wb_comm_no_vat + wb_comm_vat

        out.append({
            "internal_sku": r["internal_sku"],
            "product_name": None,
            "product_image_url": None,
            "product_image": None,
            "wb_category": None,
            "quantity_sold": qty,
            "gmv": gmv,
            "avg_price_realization_unit": unit_metrics.avg_price_realization_unit,
            "wb_commission_total": wb_comm,
            "acquiring_fee": acquiring_fee,
            "delivery_fee": delivery_fee,
            "rebill_logistics_cost": rebill_logistics_cost,
            "pvz_fee": pvz_fee,
            "wb_total_total": wb_total_total,
            "wb_total_unit": unit_metrics.wb_total_unit,
            "income_before_cogs_unit": unit_metrics.income_before_cogs_unit,
            "income_before_cogs_pct_rrp": unit_metrics.income_before_cogs_pct_rrp,
            "wb_total_pct_rrp": unit_metrics.wb_total_pct_rrp,
            "net_before_cogs": float(net_before_cogs_total_d),
            "net_before_cogs_pct": net_before_cogs_pct,
            "wb_total_pct": wb_total_pct,
            "events_count": int(r["events_count"] or 0),
            "wb_commission_no_vat": wb_comm_no_vat,
            "wb_commission_vat": wb_comm_vat,
            "net_payable_metric": float(r["net_payable_metric"] or 0),
            "wb_sales_commission_metric": float(r["wb_sales_commission_metric"] or 0),
            "wb_price_admin": float(r["wb_price_admin"]) if r.get("wb_price_admin") is not None else None,
            "rrp_price": rrp_price,
            "cogs_per_unit": cogs_unit,
            "cogs_total": cogs_total,
            "product_profit": product_profit,
            "product_margin_pct": product_margin_pct,
            # Backward compatibility / aliases
            "gmv_per_unit": unit_metrics.avg_price_realization_unit,
            "profit_per_unit": unit_metrics.profit_unit,
            "profit_unit": unit_metrics.profit_unit,
            "margin_pct_unit": unit_metrics.margin_pct_unit,
            "profit_pct_of_rrp_unit": unit_metrics.profit_pct_rrp,
            "profit_pct_rrp": unit_metrics.profit_pct_rrp,
            "cogs_missing": cogs_missing,
        })

    # Enrich with product identification (title + image + WB category).
    # NOTE: rrp_price and wb_price_admin are computed in SQL above to support SQL-level COGS calculations.
    if out:
        skus = [item["internal_sku"] for item in out if item.get("internal_sku")]

        def _extract_first_url(obj: Any) -> str | None:
            if not obj:
                return None
            if isinstance(obj, str):
                u = obj.strip()
                if not u:
                    return None
                if u.startswith("//"):
                    u = "https:" + u
                if u.startswith("http://"):
                    u = "https://" + u[len("http://") :]
                if not u.startswith("https://"):
                    return None
                return u
            if isinstance(obj, dict):
                for k in (
                    "url",
                    "big",
                    "c516x688",
                    "c246x328",
                    "square",
                    "medium",
                    "small",
                    "original",
                    "src",
                    "link",
                ):
                    v = obj.get(k)
                    if isinstance(v, str) and v.strip():
                        return _extract_first_url(v)
                return None
            if isinstance(obj, list):
                for el in obj:
                    u = _extract_first_url(el)
                    if u:
                        return u
                return None
            return None

        def _extract_image_url(pics: Any, raw: Any) -> str | None:
            u = _extract_first_url(pics)
            if u:
                return u
            if isinstance(raw, dict):
                for key in ("photos", "pics", "images"):
                    u2 = _extract_first_url(raw.get(key))
                    if u2:
                        return u2
            return None

        # Product identification (title + image + WB category)
        product_by_sku: Dict[str, Dict[str, Any]] = {}
        for i in range(0, len(skus), 200):
            chunk = skus[i : i + 200]
            placeholders = ", ".join(f":sku_{k}" for k in range(len(chunk)))
            p: Dict[str, Any] = {"project_id": project_id}
            for k, sku in enumerate(chunk):
                p[f"sku_{k}"] = sku
            rows_prod = conn.execute(
                text(
                    f"""
                    SELECT vendor_code_norm AS internal_sku,
                           title,
                           subject_name,
                           pics,
                           raw
                    FROM products
                    WHERE project_id = :project_id
                      AND vendor_code_norm IN ({placeholders})
                    """
                ),
                p,
            ).mappings().all()
            for r in rows_prod:
                sku = r.get("internal_sku")
                if not sku:
                    continue
                pics = r.get("pics")
                raw = r.get("raw")
                product_by_sku[str(sku)] = {
                    "product_name": r.get("title"),
                    "wb_category": r.get("subject_name"),
                    "product_image_url": _extract_image_url(pics, raw),
                }
        # Attach enrichment to output rows
        for item in out:
            sku = item.get("internal_sku")
            if not sku:
                continue
            pinfo = product_by_sku.get(str(sku))
            if pinfo:
                item["product_name"] = pinfo.get("product_name")
                item["product_image_url"] = pinfo.get("product_image_url")
                # Backward-compatible alias
                item["product_image"] = pinfo.get("product_image_url")
                item["wb_category"] = pinfo.get("wb_category")

    # Attach sources per SKU (from wb_sku_pnl_snapshot_sources)
    skus = [item["internal_sku"] for item in out]
    sources_map = get_sources_for_skus(conn, project_id, period_from, period_to, version, skus)
    for item in out:
        item["sources"] = sources_map.get(item["internal_sku"], [])

    return (out, total_count)
