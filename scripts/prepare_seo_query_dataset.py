#!/usr/bin/env python3
"""Assemble and print unified SEO query dataset diagnostics for one project/category."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from app.db import SessionLocal
from app.services.seo.query_pipeline import assemble_unified_query_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare unified SEO query dataset diagnostics")
    parser.add_argument("--project-id", required=True, type=int, help="Project ID")
    parser.add_argument("--category-id", required=True, type=int, help="WB category_id / subject_id scope")
    parser.add_argument("--top-limit", type=int, default=20, help="Number of top queries in diagnostics")
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
        result = assemble_unified_query_dataset(
            session,
            project_id=args.project_id,
            category_id=args.category_id,
            top_limit=max(1, int(args.top_limit)),
            samples_limit=max(1, int(args.samples_limit)),
        )
        if result.diagnostics.total_source_linked_queries == 0:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "No source data found for project/category scope",
                        "project_id": args.project_id,
                        "category_id": args.category_id,
                    },
                    ensure_ascii=False,
                    indent=2 if args.pretty else None,
                ),
                file=sys.stderr,
            )
            return 2

        print(
            json.dumps(
                result.diagnostics.to_dict(),
                ensure_ascii=False,
                indent=2 if args.pretty else None,
            )
        )
        return 0
    except Exception as exc:
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
