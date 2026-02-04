#!/usr/bin/env python3
"""Introspect wb_finance_report_lines payload to discover real keys for FIELD_TO_EVENT.

Usage:
    python scripts/introspect_wb_finance_payload.py --project-id 1 [--limit 2000]
    cd d:\\Work\\EcomCore && python scripts/introspect_wb_finance_payload.py --project-id 1

No DB writes. Read-only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import create_engine, text
from app.settings import SQLALCHEMY_DATABASE_URL

# Keywords suggesting money-like fields (regex, case-insensitive)
MONEY_KEYWORDS = re.compile(
    r"amount|sum|price|rub|cost|vat|nds|commission|penalty|pay|sale|logistic|"
    r"storage|accept|pvz|withhold|compens|fee|операци|комисс|логистик|"
    r"штраф|удержан|хранен|эквайр",
    re.I,
)


def _is_numeric(v) -> bool:
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


def _is_money_candidate(key: str) -> bool:
    return bool(MONEY_KEYWORDS.search(key))


def introspect(project_id: int, limit: int = 2000) -> None:
    """Fetch raw lines and report payload keys + money candidate samples."""
    engine = create_engine(SQLALCHEMY_DATABASE_URL)

    sql = text(
        """
        SELECT r.id, r.report_id, r.line_id, r.payload, r.payload_hash
        FROM wb_finance_report_lines r
        JOIN wb_finance_reports rf ON rf.project_id = r.project_id AND rf.report_id = r.report_id
        WHERE r.project_id = :project_id
          AND rf.marketplace_code = 'wildberries'
        ORDER BY rf.last_seen_at DESC NULLS LAST, r.report_id, r.id
        LIMIT :limit
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(sql, {"project_id": project_id, "limit": limit}).mappings().all()

    if not rows:
        print(f"No rows found for project_id={project_id}. Run WB finances ingest first.")
        return

    all_keys: set[str] = set()
    key_values: defaultdict[str, list] = defaultdict(list)
    key_counts_nonzero: defaultdict[str, int] = defaultdict(int)

    for row in rows:
        payload = row.get("payload")
        if payload is None:
            continue
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                continue
        if not isinstance(payload, dict):
            continue
        for k, v in payload.items():
            all_keys.add(k)
            if _is_numeric(v):
                num = float(str(v).replace(",", ".").replace(" ", "")) if isinstance(v, str) else float(v)
                if num != 0:
                    key_counts_nonzero[k] += 1
                    if len(key_values[k]) < 5:
                        key_values[k].append(num)

    print("=" * 80)
    print("WB FINANCE PAYLOAD INTROSPECTION REPORT")
    print("=" * 80)
    print(f"project_id: {project_id}")
    print(f"limit: {limit}")
    print(f"rows_analyzed: {len(rows)}")
    print(f"keys_total: {len(all_keys)}")
    print()

    money_candidates = [k for k in sorted(all_keys) if _is_money_candidate(k)]
    print(f"money_candidate_keys ({len(money_candidates)}):")
    for k in money_candidates:
        samples = key_values.get(k, [])[:5]
        cnt = key_counts_nonzero.get(k, 0)
        print(f"  {k}: count_nonzero={cnt}, sample_values={samples}")
    print()

    print("ALL KEYS (alphabetical):")
    for k in sorted(all_keys):
        samples = key_values.get(k, [])[:5]
        cnt = key_counts_nonzero.get(k, 0)
        mc = " [MONEY]" if _is_money_candidate(k) else ""
        print(f"  {k}: count_nonzero={cnt}, sample_values={samples}{mc}")
    print()
    print("Use money_candidate_keys to fill FIELD_TO_EVENT in event_mapping.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="Introspect WB finance payload keys")
    parser.add_argument("--project-id", type=int, required=True, help="Project ID")
    parser.add_argument("--limit", type=int, default=2000, help="Max rows to analyze")
    args = parser.parse_args()
    introspect(project_id=args.project_id, limit=args.limit)


if __name__ == "__main__":
    main()
