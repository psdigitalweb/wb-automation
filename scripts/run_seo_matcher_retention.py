"""CLI helper for matcher-run retention cleanup (Iteration 2, WS-G).

Usage:

    python -m scripts.run_seo_matcher_retention
    python -m scripts.run_seo_matcher_retention --dry-run
    python -m scripts.run_seo_matcher_retention --keep-newest 50 --keep-days 14

Runs the same helper that ``POST /api/v1/seo/matcher/retention/cleanup``
calls. Prints a JSON report of the action taken.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.db import SessionLocal  # noqa: E402
from app.services.seo.matcher_retention import (  # noqa: E402
    KEEP_NEWEST_PER_SKU,
    KEEP_WINDOW_DAYS,
    cleanup_matcher_runs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Matcher-run retention cleanup.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-newest", type=int, default=KEEP_NEWEST_PER_SKU)
    parser.add_argument("--keep-days", type=int, default=KEEP_WINDOW_DAYS)
    args = parser.parse_args()

    session = SessionLocal()
    try:
        report = cleanup_matcher_runs(
            session,
            dry_run=bool(args.dry_run),
            keep_newest=int(args.keep_newest),
            keep_days=int(args.keep_days),
        )
        if not args.dry_run:
            session.commit()
        else:
            session.rollback()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(
        json.dumps(
            {
                "scanned_runs": report.scanned_runs,
                "kept_by_recency_count": report.kept_by_recency_count,
                "kept_by_reference_count": report.kept_by_reference_count,
                "deleted_run_ids": list(report.deleted_run_ids),
                "deleted_result_rows": report.deleted_result_rows,
                "dry_run": report.dry_run,
                "keep_newest": int(args.keep_newest),
                "keep_days": int(args.keep_days),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
