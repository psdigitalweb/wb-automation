"""Build wb_financial_events from wb_finance_report_lines.

Idempotent: rerunning for same period produces same events.
Handles payload_hash changes: deletes old events and rebuilds when raw line changes.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.db import engine
from app.db_wb_financial_events import (
    delete_events_for_line,
    get_events_sum_by_report,
    get_existing_payload_hash,
    insert_reconciliation,
    upsert_event,
)
from app.db_wb_finances import compute_payload_hash
from app.services.wb_financial.date_extractor import extract_event_date
from app.services.wb_financial.event_mapping import (
    FIELD_TO_EVENT,
    NON_MONEY_KEYS,
    resolve_amount_for_event,
)
from app.services.wb_financial.sku_resolver import resolve_internal_sku, resolve_internal_skus_bulk

# Keywords for unmapped money candidate detection
MONEY_KEYWORDS = re.compile(
    r"amount|sum|price|rub|cost|vat|nds|commission|penalty|pay|sale|logistic|"
    r"storage|accept|pvz|withhold|compens|fee",
    re.I,
)


def _is_numeric(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return True
    if isinstance(v, str):
        try:
            float(v.replace(",", ".").replace(" ", ""))
            return True
        except (ValueError, TypeError):
            return False
    return False


def _is_money_candidate_key(key: str) -> bool:
    return bool(MONEY_KEYWORDS.search(key)) and key not in NON_MONEY_KEYS


def _get_numeric_value(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            s = v.replace(",", ".").replace(" ", "").strip()
            return float(s) if s else None
    except (ValueError, TypeError):
        return None
    return None


def build_wb_financial_events(
    project_id: int,
    date_from: date,
    date_to: date,
) -> Dict[str, Any]:
    """Build events from raw lines for given period. Idempotent."""
    stats: Dict[str, Any] = {
        "project_id": project_id,
        "date_from": str(date_from),
        "date_to": str(date_to),
        "inserted": 0,
        "updated": 0,
        "deleted": 0,
        "skipped": 0,
        "unmapped_count": 0,
        "unmapped_sample": [],
        "reconciliation_ok": True,
        "errors": [],
    }

    sql = text(
        """
        SELECT r.id, r.project_id, r.report_id, r.line_id, r.payload, r.payload_hash, r.fetched_at,
               rf.period_from, rf.period_to, rf.last_seen_at
        FROM wb_finance_report_lines r
        JOIN wb_finance_reports rf ON rf.project_id = r.project_id AND rf.report_id = r.report_id
        WHERE r.project_id = :project_id
          AND rf.marketplace_code = 'wildberries'
          AND rf.period_from <= :date_to AND rf.period_to >= :date_from
        ORDER BY rf.last_seen_at DESC NULLS LAST, r.report_id, r.id
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {
                "project_id": project_id,
                "date_from": date_from,
                "date_to": date_to,
            },
        ).mappings().all()

    report_ids = list({int(r["report_id"]) for r in rows if r.get("report_id") is not None})

    # Mapped keys (used in FIELD_TO_EVENT) - for raw_sum reconciliation
    mapped_keys: set = set()
    for aliases, _, _ in FIELD_TO_EVENT:
        mapped_keys.update(aliases)

    # Pre-fetch nm_id -> internal_sku for all nm_ids in payloads (one query)
    nm_ids_set: set = set()
    for row in rows:
        payload = row.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                continue
        if isinstance(payload, dict):
            nid = payload.get("nm_id") or payload.get("nmId")
            if nid is not None:
                try:
                    nm_ids_set.add(int(nid))
                except (ValueError, TypeError):
                    pass
    nm_id_to_sku = resolve_internal_skus_bulk(project_id, list(nm_ids_set))

    raw_mapped_sums: Dict[int, float] = defaultdict(float)
    unmapped_samples: List[Dict[str, Any]] = []

    for row in rows:
        project_id_val = int(row["project_id"])
        report_id_val = row.get("report_id")
        line_id_val = row.get("line_id")
        payload = row.get("payload")
        payload_hash_val = row.get("payload_hash") or ""
        fetched_at = row.get("fetched_at")
        period_from_val = row.get("period_from")
        period_to_val = row.get("period_to")
        line_pk = int(row["id"])

        if payload is None:
            continue
        if isinstance(payload, str):
            import json

            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                stats["errors"].append(f"line id={line_pk}: invalid JSON payload")
                continue
        if not isinstance(payload, dict):
            continue

        # line_uid_surrogate for line_id NULL
        if line_id_val is None:
            line_uid_surrogate = f"{report_id_val}:{line_pk}" if report_id_val is not None else None
        else:
            line_uid_surrogate = None

        # payload_hash change: delete existing events and rebuild
        existing_hash = get_existing_payload_hash(
            project_id_val,
            report_id_val,
            line_id_val,
            line_uid_surrogate,
        )
        if existing_hash is not None and existing_hash != payload_hash_val:
            deleted = delete_events_for_line(
                project_id_val,
                report_id_val,
                line_id_val,
                line_uid_surrogate,
            )
            stats["deleted"] += deleted

        # event_date, quality
        event_date_val, event_date_quality = extract_event_date(
            payload, period_to_val, fetched_at
        )

        # nm_id, vendor_code, internal_sku
        nm_id_val = payload.get("nm_id") or payload.get("nmId")
        if nm_id_val is not None:
            try:
                nm_id_val = int(nm_id_val)
            except (ValueError, TypeError):
                nm_id_val = None
        vendor_code_val = payload.get("vendor_code") or payload.get("vendorCode")
        internal_sku_val = nm_id_to_sku.get(nm_id_val) if nm_id_val else None

        # currency
        currency_val = (
            payload.get("currency")
            or payload.get("currency_code")
            or payload.get("valute")
            or "RUB"
        )
        if not isinstance(currency_val, str):
            currency_val = "RUB"

        # Returns: WB can send positive amounts even for returns; for PnL we need signed events.
        doc_type = (payload.get("doc_type_name") or payload.get("docTypeName") or "").strip()
        oper_name = (
            payload.get("supplier_oper_name")
            or payload.get("supplierOperName")
            or payload.get("operation_type")
            or payload.get("operationType")
            or ""
        ).strip()
        sign = -1.0 if (doc_type == "Возврат" or oper_name == "Возврат") else 1.0

        # Iterate FIELD_TO_EVENT
        for aliases, event_type, scope in FIELD_TO_EVENT:
            amount_val, source_field = resolve_amount_for_event(payload, aliases)
            if amount_val is None or source_field is None or amount_val == 0:
                continue
            amount_val = float(amount_val) * sign

            # SKU PnL builder filters scope='sku'; when line has nm_id, store as sku so it is included.
            effective_scope = "sku" if nm_id_val is not None else scope

            if report_id_val is not None:
                raw_mapped_sums[int(report_id_val)] += amount_val

            upsert_event(
                project_id=project_id_val,
                report_id=report_id_val,
                line_id=line_id_val,
                line_uid_surrogate=line_uid_surrogate,
                event_date=event_date_val,
                event_date_quality=event_date_quality,
                period_from=period_from_val,
                period_to=period_to_val,
                nm_id=nm_id_val,
                vendor_code=vendor_code_val,
                internal_sku=internal_sku_val,
                event_type=event_type,
                scope=effective_scope,
                amount=amount_val,
                currency=str(currency_val),
                source_field=source_field,
                payload_hash=payload_hash_val,
            )
            stats["inserted"] += 1

        # Unmapped diagnostics
        for key, v in payload.items():
            if key in mapped_keys:
                continue
            if not _is_money_candidate_key(key):
                continue
            num = _get_numeric_value(v)
            if num is None or num == 0:
                continue
            stats["unmapped_count"] += 1
            if len(unmapped_samples) < 20:
                unmapped_samples.append(
                    {"line_id": line_id_val, "line_pk": line_pk, "key": key, "value": num}
                )

    stats["unmapped_sample"] = unmapped_samples

    # Reconciliation v1
    events_sums = get_events_sum_by_report(project_id, report_ids)
    for rid in report_ids:
        raw_sum = raw_mapped_sums.get(rid, 0.0)
        ev_sum = events_sums.get(rid, 0.0)
        diff = abs(raw_sum - ev_sum)
        insert_reconciliation(
            project_id=project_id,
            period_from=date_from,
            period_to=date_to,
            report_id=rid,
            source="raw_sum",
            metric="total_mapped",
            value=raw_sum,
            details_json={"report_id": rid},
        )
        insert_reconciliation(
            project_id=project_id,
            period_from=date_from,
            period_to=date_to,
            report_id=rid,
            source="events_sum",
            metric="total_mapped",
            value=ev_sum,
            details_json={"report_id": rid, "diff": diff, "ok": diff < 0.01},
        )
        if diff >= 0.01:
            stats["reconciliation_ok"] = False

    if unmapped_samples:
        insert_reconciliation(
            project_id=project_id,
            period_from=date_from,
            period_to=date_to,
            report_id=None,
            source="unmapped",
            metric="unmapped",
            value=float(stats["unmapped_count"]),
            details_json={"sample": unmapped_samples[:10]},
        )

    return stats
