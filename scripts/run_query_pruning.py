#!/usr/bin/env python3
"""Run deterministic query pruning/basic annotation for one project/category."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from app.db import SessionLocal
from app.services.seo.query_pipeline import (
    get_clean_query_set,
    get_pruning_slice,
    run_query_pruning_and_basic_annotation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run SEO query pruning and basic annotation")
    parser.add_argument("--project-id", required=True, type=int, help="Project ID")
    parser.add_argument("--category-id", required=True, type=int, help="WB category_id / subject_id scope")
    parser.add_argument("--bucket", choices=("head", "mid", "tail"), help="Optional head/mid/tail filter")
    parser.add_argument("--status", choices=("keep", "drop", "review"), help="Optional pruning status filter")
    parser.add_argument("--top-limit", type=int, default=20, help="Number of top kept queries in diagnostics")
    parser.add_argument("--samples-limit", type=int, default=20, help="Number of sample rows per diagnostics section")
    parser.add_argument(
        "--pretty",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pretty-print JSON output (default: enabled)",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        result = run_query_pruning_and_basic_annotation(
            session,
            project_id=args.project_id,
            category_id=args.category_id,
            top_limit=max(1, int(args.top_limit)),
            samples_limit=max(1, int(args.samples_limit)),
            persist=True,
        )
        if result.diagnostics.total_canonical_queries_processed == 0:
            session.rollback()
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "No canonical queries found for project/category scope",
                        "project_id": args.project_id,
                        "category_id": args.category_id,
                    },
                    ensure_ascii=False,
                    indent=2 if args.pretty else None,
                ),
                file=sys.stderr,
            )
            return 2

        session.commit()
        if args.status == "keep":
            filtered_rows = get_clean_query_set(
                session,
                project_id=args.project_id,
                category_id=args.category_id,
                bucket=args.bucket,
            )
        elif args.status:
            filtered_rows = get_pruning_slice(
                session,
                project_id=args.project_id,
                category_id=args.category_id,
                pruning_status=args.status,
                bucket=args.bucket,
            )
        elif args.bucket:
            filtered_rows = get_clean_query_set(
                session,
                project_id=args.project_id,
                category_id=args.category_id,
                bucket=args.bucket,
            )
        else:
            filtered_rows = None

        payload = result.diagnostics.to_dict()
        if filtered_rows is not None:
            payload = {
                "diagnostics": payload,
                "queries": [row.to_dict() for row in filtered_rows],
                "status_filter": args.status or "keep",
                "bucket_filter": args.bucket,
            }

        print(json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None))
        return 0
    except Exception as exc:
        session.rollback()
        print(
            json.dumps(
                {"ok": False, "error": str(exc), "project_id": args.project_id, "category_id": args.category_id},
                ensure_ascii=False,
                indent=2 if args.pretty else None,
            ),
            file=sys.stderr,
        )
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
