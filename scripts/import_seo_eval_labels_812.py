"""Import the 191 seeded eval labels for category 812.

Reads ``artifacts/meaning_atoms/<timestamp>_project1_category812/comparison.csv``
and inserts one ``SeoEvalLabel`` per row that carries an ``expected_bucket``
value. Idempotent: existing ``(project_id, category_id, label_set_id,
query_text_normalized, nm_id)`` rows are updated, not duplicated.

Usage:

    python -m scripts.import_seo_eval_labels_812 --project-id 1
    python -m scripts.import_seo_eval_labels_812 --project-id 1 \
        --csv artifacts/meaning_atoms/20260422_121955_project1_category812/comparison.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import SeoEvalLabel  # noqa: E402
from app.services.seo.query_pipeline import normalize_query_text  # noqa: E402


DEFAULT_CSV = (
    ROOT
    / "artifacts"
    / "meaning_atoms"
    / "20260422_121955_project1_category812"
    / "comparison.csv"
)
CATEGORY_ID = 812
LABEL_SET_ID = 1
SOURCE_TAG = "comparison_csv_812"


def _iter_labelled_rows(csv_path: Path) -> Iterable[dict]:
    # Some exports carry a BOM; handle utf-8-sig defensively.
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            expected = (row.get("expected_bucket") or "").strip()
            if not expected:
                continue
            yield row


def _upsert_label(session, *, project_id: int, row: dict) -> str:
    normalized = normalize_query_text(str(row.get("query") or ""))
    if not normalized:
        return "skipped_empty_query"
    nm_id_raw = (row.get("nm_id") or "").strip()
    nm_id: int | None = int(nm_id_raw) if nm_id_raw.isdigit() else None
    expected = str(row.get("expected_bucket") or "").strip()

    existing = session.scalars(
        select(SeoEvalLabel).where(
            SeoEvalLabel.project_id == int(project_id),
            SeoEvalLabel.category_id == CATEGORY_ID,
            SeoEvalLabel.label_set_id == LABEL_SET_ID,
            SeoEvalLabel.query_text_normalized == normalized,
            SeoEvalLabel.nm_id == nm_id,
        )
    ).first()

    reason_parts = [
        part
        for part in (
            row.get("current_reasons") or "",
            row.get("atoms_reasons") or "",
        )
        if part
    ]
    expected_reason = " | ".join(reason_parts) if reason_parts else None

    if existing is not None:
        existing.expected_bucket = expected
        existing.expected_reason = expected_reason
        existing.source = SOURCE_TAG
        return "updated"

    session.add(
        SeoEvalLabel(
            project_id=int(project_id),
            category_id=CATEGORY_ID,
            label_set_id=LABEL_SET_ID,
            query_text_normalized=normalized,
            nm_id=nm_id,
            expected_bucket=expected,
            expected_reason=expected_reason,
            source=SOURCE_TAG,
        )
    )
    return "inserted"


def main() -> int:
    parser = argparse.ArgumentParser(description="Import SEO eval labels for category 812.")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--csv", type=str, default=str(DEFAULT_CSV))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(json.dumps({"error": f"csv not found: {csv_path}"}, ensure_ascii=False))
        return 1

    session = SessionLocal()
    summary = {"inserted": 0, "updated": 0, "skipped_empty_query": 0}
    try:
        for row in _iter_labelled_rows(csv_path):
            action = _upsert_label(session, project_id=args.project_id, row=row)
            summary[action] = summary.get(action, 0) + 1
        if args.dry_run:
            session.rollback()
        else:
            session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(
        json.dumps(
            {
                "project_id": int(args.project_id),
                "category_id": CATEGORY_ID,
                "label_set_id": LABEL_SET_ID,
                "csv": str(csv_path),
                "dry_run": bool(args.dry_run),
                "summary": summary,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
