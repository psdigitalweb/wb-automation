"""CLI entrypoint for the vision-enhanced meaning atoms shadow experiment."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Mapping

from app.db import SessionLocal
from app.schemas.seo_query_meaning_matcher import MeaningAwareMatcherItem
from app.services.seo.experiments.meaning_atoms.comparison import (
    _annotation_for_sku,
    _current_matcher_items,
    _load_query_meanings,
    _load_query_meanings_by_cluster_keys,
    _merge_rows,
    _query_display,
    _query_payload,
    _safe_evidence_payload,
    _timestamped_output_dir,
    select_sample_nm_ids,
)
from app.services.seo.atoms.v1.llm_extractors import extract_query_atoms, extract_sku_atoms
from app.services.seo.atoms.v1.matcher_v1 import (
    ATOMS_MATCHER_V1_VERSION,
    match_atoms_v1,
    normalize_query_atoms_v1,
    normalize_sku_atoms_v1,
)
from app.services.seo.atoms.v1.schemas import ComparisonResult, QueryAtomsRecord, SkuAtoms
from app.services.seo.atoms.v1.vision import extract_vision_sku_atoms, image_urls_from_evidence, merge_sku_atoms_with_vision
from app.services.seo.experiments.meaning_atoms.matcher import match_atoms
from app.services.seo.experiments.meaning_atoms.report import apply_eval_labels, compute_metrics, load_eval_labels, write_artifacts
from app.services.seo.providers.openrouter import OpenRouterProvider


def _parse_nm_ids(value: str | None) -> list[int] | None:
    if not value:
        return None
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _write_vision_atoms(path: Path, items: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(item, ensure_ascii=False, default=str) + "\n")


def _write_image_urls(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["nm_id", "image_url"])
        writer.writeheader()
        writer.writerows(rows)


def run_vision_comparison(
    *,
    project_id: int,
    category_id: int,
    nm_ids: list[int] | None,
    sample_size: int,
    limit_per_sku: int,
    query_limit: int,
    output_dir: Path,
    eval_labels_path: Path | None,
    force_refresh_llm: bool,
    force_refresh_vision: bool,
    include_rejected: bool,
    vision_model: str,
    image_limit: int,
    use_v1_matcher: bool = False,
) -> ComparisonResult:
    provider = OpenRouterProvider()
    session = SessionLocal()
    try:
        resolved_nm_ids = select_sample_nm_ids(
            session,
            project_id=project_id,
            category_id=category_id,
            requested_nm_ids=nm_ids,
            sample_size=sample_size,
        )
        run_dir = _timestamped_output_dir(output_dir, project_id=project_id, category_id=category_id)
        cache_dir = output_dir / "llm_cache"
        vision_cache_dir = output_dir / "vision_cache"

        current_by_sku: dict[int, dict[str, MeaningAwareMatcherItem]] = {}
        current_cluster_keys: set[str] = set()
        for nm_id in resolved_nm_ids:
            current = _current_matcher_items(
                session,
                project_id=project_id,
                category_id=category_id,
                nm_id=nm_id,
                limit=limit_per_sku,
                include_rejected=include_rejected,
            )
            current_by_sku[int(nm_id)] = current
            current_cluster_keys.update(key for key in current if key)

        query_rows = _load_query_meanings(session, project_id=project_id, category_id=category_id, query_limit=query_limit)
        loaded_keys = {str(row.cluster_key) for row, _ in query_rows}
        query_rows.extend(
            _load_query_meanings_by_cluster_keys(
                session,
                project_id=project_id,
                category_id=category_id,
                cluster_keys=current_cluster_keys - loaded_keys,
            )
        )
        query_records: list[QueryAtomsRecord] = []
        for query_row, ranking_value in query_rows:
            atoms = extract_query_atoms(
                _query_payload(query_row, ranking_value=ranking_value),
                provider=provider,
                cache_dir=cache_dir,
                force_refresh=force_refresh_llm,
            )
            query_records.append(
                QueryAtomsRecord(
                    query=_query_display(query_row),
                    cluster_key=str(query_row.cluster_key),
                    cluster_id=int(query_row.cluster_id) if query_row.cluster_id is not None else None,
                    query_meaning_id=int(query_row.id),
                    ranking_value_used=ranking_value,
                    current_genericness=str(query_row.genericness or ""),
                    atoms=atoms,
                )
            )

        rows = []
        base_sku_atoms: list[SkuAtoms] = []
        merged_sku_atoms: list[SkuAtoms] = []
        vision_records: list[dict[str, Any]] = []
        image_rows: list[dict[str, Any]] = []
        for nm_id in resolved_nm_ids:
            annotation = _annotation_for_sku(session, project_id=project_id, category_id=category_id, nm_id=nm_id)
            meaning_payload: Mapping[str, Any] = annotation.meaning_payload if annotation is not None else {}
            evidence_payload = _safe_evidence_payload(session, project_id=project_id, category_id=category_id, nm_id=nm_id)
            image_urls = image_urls_from_evidence(evidence_payload, limit=image_limit)
            image_rows.extend({"nm_id": int(nm_id), "image_url": url} for url in image_urls)
            sku_atoms = extract_sku_atoms(
                evidence_payload,
                meaning_payload=meaning_payload,
                provider=provider,
                cache_dir=cache_dir,
                force_refresh=force_refresh_llm,
            )
            vision_atoms = extract_vision_sku_atoms(
                evidence_payload,
                image_limit=image_limit,
                cache_dir=vision_cache_dir,
                force_refresh=force_refresh_vision,
                model=vision_model,
            )
            merged = merge_sku_atoms_with_vision(sku_atoms, vision_atoms)
            base_sku_atoms.append(sku_atoms)
            merged_sku_atoms.append(merged)
            vision_records.append(
                {
                    "nm_id": int(nm_id),
                    "image_urls": image_urls,
                    "vision_atoms": vision_atoms.model_dump(mode="json"),
                    "base_counts": {
                        "facts": len(sku_atoms.facts),
                        "positive_atoms": len(sku_atoms.positive_atoms),
                        "negative_fit_atoms": len(sku_atoms.negative_fit_atoms),
                    },
                    "merged_counts": {
                        "facts": len(merged.facts),
                        "positive_atoms": len(merged.positive_atoms),
                        "negative_fit_atoms": len(merged.negative_fit_atoms),
                    },
                }
            )
            current = current_by_sku.get(int(nm_id), {})
            matcher_fn = match_atoms_v1 if use_v1_matcher else match_atoms
            atoms_results = {
                record.cluster_key: matcher_fn(
                    merged,
                    record.atoms,
                    query_text=record.query,
                    cluster_key=record.cluster_key,
                    ranking_value_used=record.ranking_value_used,
                )
                for record in query_records
            }
            rows.extend(_merge_rows(nm_id=nm_id, current=current, atoms=atoms_results))

        labels = load_eval_labels(eval_labels_path)
        apply_eval_labels(rows, labels)
        result = ComparisonResult(
            project_id=int(project_id),
            category_id=int(category_id),
            nm_ids=resolved_nm_ids,
            matcher_version=ATOMS_MATCHER_V1_VERSION if use_v1_matcher else "atoms_matcher_shadow_v0",
            rows=rows,
            metrics=compute_metrics(rows),
        )
        write_artifacts(result, output_dir=run_dir, sku_atoms=merged_sku_atoms, query_atoms=query_records)
        if use_v1_matcher:
            with (run_dir / "sku_atoms_v1.jsonl").open("w", encoding="utf-8") as handle:
                for item in merged_sku_atoms:
                    handle.write(json.dumps(normalize_sku_atoms_v1(item).model_dump(mode="json"), ensure_ascii=False, default=str) + "\n")
            with (run_dir / "query_atoms_v1.jsonl").open("w", encoding="utf-8") as handle:
                for item in query_records:
                    handle.write(
                        json.dumps(
                            {
                                "query": item.query,
                                "cluster_key": item.cluster_key,
                                "ranking_value_used": item.ranking_value_used,
                                "atoms": normalize_query_atoms_v1(item.atoms, query_text=item.query).model_dump(mode="json"),
                            },
                            ensure_ascii=False,
                            default=str,
                        )
                        + "\n"
                    )
        _write_vision_atoms(run_dir / "vision_atoms.jsonl", vision_records)
        _write_image_urls(run_dir / "vision_image_urls.csv", image_rows)
        with (run_dir / "base_sku_atoms.jsonl").open("w", encoding="utf-8") as handle:
            for item in base_sku_atoms:
                handle.write(json.dumps(item.model_dump(mode="json"), ensure_ascii=False, default=str) + "\n")
        return result
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run vision-enhanced LLM meaning atoms shadow matcher comparison.")
    parser.add_argument("--project-id", type=int, default=1)
    parser.add_argument("--category-id", type=int, default=812)
    parser.add_argument("--nm-ids", type=str, default=None)
    parser.add_argument("--sample-size", type=int, default=10)
    parser.add_argument("--limit-per-sku", type=int, default=120)
    parser.add_argument("--query-limit", type=int, default=500)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/meaning_atoms_vision"))
    parser.add_argument("--eval-labels", type=Path, default=None)
    parser.add_argument("--force-refresh-llm", action="store_true")
    parser.add_argument("--force-refresh-vision", action="store_true")
    parser.add_argument("--include-rejected", action="store_true", default=True)
    parser.add_argument("--vision-model", type=str, default="openai/gpt-4o")
    parser.add_argument("--image-limit", type=int, default=1)
    parser.add_argument("--use-v1-matcher", action="store_true")
    args = parser.parse_args()
    result = run_vision_comparison(
        project_id=args.project_id,
        category_id=args.category_id,
        nm_ids=_parse_nm_ids(args.nm_ids),
        sample_size=args.sample_size,
        limit_per_sku=args.limit_per_sku,
        query_limit=args.query_limit,
        output_dir=args.output_dir,
        eval_labels_path=args.eval_labels,
        force_refresh_llm=args.force_refresh_llm,
        force_refresh_vision=args.force_refresh_vision,
        include_rejected=args.include_rejected,
        vision_model=args.vision_model,
        image_limit=args.image_limit,
        use_v1_matcher=args.use_v1_matcher,
    )
    print(f"Output: {result.output_dir}")
    print(f"Rows: {len(result.rows)}")
    print(f"Metrics: {result.metrics}")


if __name__ == "__main__":
    main()
