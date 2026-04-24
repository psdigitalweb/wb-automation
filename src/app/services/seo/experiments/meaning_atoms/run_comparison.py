"""CLI entrypoint for the LLM meaning atoms shadow experiment."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from app.db import SessionLocal
from app.services.seo.experiments.meaning_atoms.comparison import run_comparison
from app.services.seo.providers.openrouter import OpenRouterProvider


_SEED_LABELS = [
    (292541341, "кружка милая", "primary", "expressive match"),
    (292541341, "милая кружка", "primary", "expressive match"),
    (292541341, "кружка для папы на день рождения", "rejected", "recipient mismatch"),
    (292541341, "кружка в машину для кофе", "rejected", "car use-case not confirmed"),
    (292541341, "кружка для чая белая без рисунка", "rejected", "SKU has print"),
    (292541341, "кружка для чая с цветами", "rejected", "floral motif mismatch"),
    (292541341, "кружка 800 мл для чая", "rejected", "volume mismatch"),
    (292541341, "кружки для кофемашины", "rejected", "coffee-machine compatibility not confirmed"),
]


def _parse_nm_ids(value: str | None) -> list[int] | None:
    if not value:
        return None
    result: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        result.append(int(item))
    return result


def _ensure_seed_eval_labels(path: Path) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["nm_id", "query", "expected_bucket", "rationale"])
        writer.writerows(_SEED_LABELS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run LLM meaning atoms shadow matcher comparison.")
    parser.add_argument("--project-id", type=int, default=1)
    parser.add_argument("--category-id", type=int, default=812)
    parser.add_argument("--nm-ids", type=str, default=None, help="Comma-separated nm_id list.")
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--limit-per-sku", type=int, default=120)
    parser.add_argument("--query-limit", type=int, default=500)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/meaning_atoms"))
    parser.add_argument("--eval-labels", type=Path, default=Path("artifacts/meaning_atoms/eval_labels.csv"))
    parser.add_argument("--force-refresh-llm", action="store_true")
    parser.add_argument("--include-rejected", action="store_true", default=True)
    args = parser.parse_args()

    _ensure_seed_eval_labels(args.eval_labels)
    provider = OpenRouterProvider()
    session = SessionLocal()
    try:
        result = run_comparison(
            session,
            project_id=args.project_id,
            category_id=args.category_id,
            nm_ids=_parse_nm_ids(args.nm_ids),
            sample_size=args.sample_size,
            limit_per_sku=args.limit_per_sku,
            query_limit=args.query_limit,
            output_dir=args.output_dir,
            eval_labels_path=args.eval_labels,
            provider=provider,
            force_refresh_llm=args.force_refresh_llm,
            include_rejected=args.include_rejected,
        )
        print(f"Output: {result.output_dir}")
        print(f"Rows: {len(result.rows)}")
        print(f"Metrics: {result.metrics}")
    finally:
        session.close()


if __name__ == "__main__":
    main()

