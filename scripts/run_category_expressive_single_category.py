#!/usr/bin/env python3
"""Run category expressive extraction for a single category (offline, cache-first).

No batch orchestration, no runtime endpoint integration.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from app.db import SessionLocal  # noqa: E402
from app.services.seo.expressive_llm.category_extractive_service import (  # noqa: E402
    run_single_category_expressive_extraction,
)
from app.services.seo.expressive_llm.storage import CategoryExpressiveStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Single-category expressive extraction (offline).")
    parser.add_argument("--project-id", type=int, default=1)
    parser.add_argument("--category-id", type=int, required=True)
    parser.add_argument("--model", default="openai/gpt-4.1-mini")
    parser.add_argument("--prompt-version", default="v1")
    parser.add_argument("--min-rating", type=int, default=4)
    parser.add_argument("--max-reviews", type=int, default=100)
    parser.add_argument("--include-titles", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--max-tokens", type=int, default=900)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--store-root", default=None, help="Override store root dir (optional).")
    parser.add_argument("--overwrite-cache", action="store_true", default=False)
    args = parser.parse_args()

    store = CategoryExpressiveStore(root_dir=args.store_root) if args.store_root else CategoryExpressiveStore()

    session = SessionLocal()
    try:
        result = run_single_category_expressive_extraction(
            session,
            project_id=int(args.project_id),
            category_id=int(args.category_id),
            model=str(args.model),
            prompt_version=str(args.prompt_version),
            min_rating=int(args.min_rating),
            max_reviews=int(args.max_reviews),
            include_titles=bool(args.include_titles),
            temperature=float(args.temperature),
            top_p=float(args.top_p),
            max_tokens=int(args.max_tokens),
            timeout_seconds=float(args.timeout_seconds),
            store=store,
            overwrite_cache=bool(args.overwrite_cache),
        )

        print(
            json.dumps(
                {
                    "status": "ok",
                    "cache_hit": bool(result.cache_hit),
                    "model": str(result.model),
                    "latency_ms": result.latency_ms,
                    "cost_usd": result.cost_usd,
                    "reviews_count": int(result.input.reviews_count),
                    "titles_count": int(result.input.titles_count),
                    "evidence_quality": float(result.validation.get("evidence_quality", 0.0)),
                    "artifact_dir": str(result.artifact.artifact_dir),
                },
                ensure_ascii=False,
            )
        )
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())

