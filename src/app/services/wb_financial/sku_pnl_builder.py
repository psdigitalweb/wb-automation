"""Build WB SKU PnL snapshot from wb_financial_events.

Source: scope='sku', internal_sku IS NOT NULL.
Signed passthrough for all amounts.
Selection: events from reports whose period overlaps filter (period_from <= filter_to AND period_to >= filter_from).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List

from sqlalchemy import text

from app.db import engine
from app.db_wb_sku_pnl import bulk_insert_snapshot_rows, bulk_insert_sources, delete_snapshot


EVENT_TYPE_COLUMNS = {
    "sale_gmv": "gmv",
    "wb_commission_no_vat": "wb_commission_no_vat",
    "wb_commission_vat": "wb_commission_vat",
    "acquiring_fee": "acquiring_fee",
    "delivery_fee": "delivery_fee",
    "rebill_logistics_cost": "rebill_logistics_cost",
    "pvz_issue_return_compensation": "pvz_fee",
    "net_payable_to_seller_per_item": "net_payable_metric",
    "wb_sales_commission_excl_services_no_vat": "wb_sales_commission_metric",
}


def build_wb_sku_pnl_snapshot(
    project_id: int,
    period_from: date,
    period_to: date,
    version: int = 1,
    rebuild: bool = True,
) -> Dict[str, Any]:
    """Build SKU PnL snapshot for period. Returns stats."""
    stats: Dict[str, Any] = {
        "project_id": project_id,
        "period_from": str(period_from),
        "period_to": str(period_to),
        "version": version,
        "inserted_rows": 0,
        "distinct_skus": 0,
        "total_events": 0,
    }

    period_to_excl = period_to + timedelta(days=1)
    filter_params = {
        "project_id": project_id,
        "period_from": period_from,
        "period_to_excl": period_to_excl,
        "period_to": period_to,
    }

    # --- Backfill NULL period_from/period_to in events from wb_finance_reports (so overlap filter includes them) ---
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE wb_financial_events e
                SET period_from = r.period_from, period_to = r.period_to
                FROM wb_finance_reports r
                WHERE e.project_id = r.project_id AND e.report_id = r.report_id
                  AND (e.period_from IS NULL OR e.period_to IS NULL)
                  AND r.period_from IS NOT NULL AND r.period_to IS NOT NULL
            """)
        )
        _ = result  # keep execute side effect

    # Build selection and (optionally) wipe existing snapshot
    with engine.begin() as conn:
        if rebuild:
            delete_snapshot(conn, project_id, period_from, period_to, version)

        rows = conn.execute(
            text("""
                SELECT internal_sku, report_id, currency, event_type, amount
                FROM wb_financial_events
                WHERE project_id = :project_id
                  AND scope = 'sku'
                  AND internal_sku IS NOT NULL
                  AND (
                    (period_from IS NOT NULL AND period_to IS NOT NULL
                     AND period_from <= :period_to AND period_to >= :period_from)
                    OR
                    ((period_from IS NULL OR period_to IS NULL)
                     AND event_date >= :period_from AND event_date < :period_to_excl)
                  )
            """),
            filter_params,
        ).mappings().all()

    # Aggregate per internal_sku (totals)
    sku_data: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "gmv": 0.0,
            "wb_commission_no_vat": 0.0,
            "wb_commission_vat": 0.0,
            "acquiring_fee": 0.0,
            "delivery_fee": 0.0,
            "rebill_logistics_cost": 0.0,
            "pvz_fee": 0.0,
            "net_payable_metric": 0.0,
            "wb_sales_commission_metric": 0.0,
            "events_count": 0,
            "quantity_sold": 0,
            "currency": "RUB",
        }
    )
    # Per (sku, report_id): rows_count, amount_total (sum of all event amounts for PnL contribution)
    sku_report_data: Dict[tuple, Dict[str, Any]] = defaultdict(
        lambda: {"rows_count": 0, "amount_total": 0.0}
    )

    for row in rows:
        sku = row["internal_sku"]
        if not sku:
            continue
        report_id = row.get("report_id")
        event_type = row["event_type"]
        amount = float(row["amount"]) if row["amount"] is not None else 0.0
        col = EVENT_TYPE_COLUMNS.get(event_type)
        if col:
            sku_data[sku][col] += amount
        if event_type == "sale_gmv":
            sku_data[sku]["quantity_sold"] += 1 if amount >= 0 else -1
        sku_data[sku]["events_count"] += 1
        if row.get("currency"):
            sku_data[sku]["currency"] = str(row["currency"])
        # Per-report aggregation (only if report_id present)
        if report_id is not None:
            key = (sku, int(report_id))
            sku_report_data[key]["rows_count"] += 1
            sku_report_data[key]["amount_total"] += amount

    # Compute net_before_cogs (signed passthrough)
    snapshot_rows: List[Dict[str, Any]] = []
    for sku, data in sku_data.items():
        net = (
            data["gmv"]
            + data["wb_commission_no_vat"]
            + data["wb_commission_vat"]
            + data["acquiring_fee"]
            + data["delivery_fee"]
            + data["rebill_logistics_cost"]
            + data["pvz_fee"]
        )
        snapshot_rows.append({
            "project_id": project_id,
            "period_from": period_from,
            "period_to": period_to,
            "internal_sku": sku,
            "currency": data["currency"],
            "gmv": data["gmv"],
            "wb_commission_no_vat": data["wb_commission_no_vat"],
            "wb_commission_vat": data["wb_commission_vat"],
            "acquiring_fee": data["acquiring_fee"],
            "delivery_fee": data["delivery_fee"],
            "rebill_logistics_cost": data["rebill_logistics_cost"],
            "pvz_fee": data["pvz_fee"],
            "net_before_cogs": net,
            "net_payable_metric": data["net_payable_metric"],
            "wb_sales_commission_metric": data["wb_sales_commission_metric"],
            "events_count": data["events_count"],
            "quantity_sold": data["quantity_sold"],
            "version": version,
        })

    if snapshot_rows:
        # Unique report_ids used in per-SKU aggregation
        report_ids = list({rid for (_, rid) in sku_report_data.keys()})
        report_headers: Dict[int, Dict[str, Any]] = {}
        if report_ids:
            # Build IN clause to avoid array binding differences across drivers
            placeholders = ", ".join(f":rid_{i}" for i in range(len(report_ids)))
            params: Dict[str, Any] = {"project_id": project_id}
            for i, rid in enumerate(report_ids):
                params[f"rid_{i}"] = rid
            with engine.begin() as conn:
                header_rows = conn.execute(
                    text(f"""
                        SELECT report_id, period_from, period_to
                        FROM wb_finance_reports
                        WHERE project_id = :project_id
                          AND report_id IN ({placeholders})
                    """),
                    params,
                ).mappings().all()
                for h in header_rows:
                    report_headers[int(h["report_id"])] = {
                        "period_from": h["period_from"],
                        "period_to": h["period_to"],
                    }

        source_rows: List[Dict[str, Any]] = []
        for (sku, report_id), data in sku_report_data.items():
            if data["rows_count"] == 0:
                continue
            header = report_headers.get(report_id, {})
            source_rows.append({
                "project_id": project_id,
                "period_from": period_from,
                "period_to": period_to,
                "internal_sku": sku,
                "version": version,
                "report_id": report_id,
                "report_period_from": header.get("period_from"),
                "report_period_to": header.get("period_to"),
                "report_type": "Реализация",
                "rows_count": data["rows_count"],
                "amount_total": data["amount_total"],
            })

        with engine.begin() as conn:
            inserted = bulk_insert_snapshot_rows(conn, snapshot_rows)
            if source_rows:
                bulk_insert_sources(conn, source_rows)
        stats["inserted_rows"] = inserted

    stats["distinct_skus"] = len(snapshot_rows)
    stats["total_events"] = sum(r["events_count"] for r in snapshot_rows)

    return stats
