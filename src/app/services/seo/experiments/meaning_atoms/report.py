"""Artifact writers for the meaning atoms shadow experiment."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from app.services.seo.atoms.v1.schemas import ComparisonResult, ComparisonRow, QueryAtomsRecord, SkuAtoms
from app.services.seo.query_pipeline import normalize_query_text


def load_eval_labels(path: Path | None) -> dict[tuple[int, str], tuple[str, str]]:
    if path is None or not path.exists():
        return {}
    labels: dict[tuple[int, str], tuple[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                nm_id = int(row.get("nm_id") or 0)
            except Exception:
                continue
            query = normalize_query_text(str(row.get("query") or ""))
            expected = str(row.get("expected_bucket") or "").strip().lower()
            if nm_id and query and expected:
                labels[(nm_id, query)] = (expected, str(row.get("rationale") or ""))
    return labels


def apply_eval_labels(rows: list[ComparisonRow], labels: dict[tuple[int, str], tuple[str, str]]) -> None:
    for row in rows:
        expected = labels.get((int(row.nm_id), normalize_query_text(row.query)))
        if expected:
            row.expected_bucket = expected[0]


def compute_metrics(rows: Iterable[ComparisonRow]) -> dict[str, object]:
    items = list(rows)
    labelled = [row for row in items if row.expected_bucket]

    def _precision(system: str) -> float | None:
        bucket_attr = f"{system}_bucket"
        primary = [row for row in labelled if getattr(row, bucket_attr) == "primary"]
        if not primary:
            return None
        good = [row for row in primary if row.expected_bucket == "primary"]
        return round(len(good) / len(primary), 4)

    current_bad_primary = [
        row
        for row in labelled
        if row.current_bucket == "primary" and row.expected_bucket in {"rejected", "broad"}
    ]
    atoms_bad_primary = [
        row
        for row in labelled
        if row.atoms_bucket == "primary" and row.expected_bucket in {"rejected", "broad"}
    ]
    target_lift = [
        row
        for row in labelled
        if row.expected_bucket == "primary" and row.current_bucket != "primary" and row.atoms_bucket == "primary"
    ]
    current_correct = [row for row in labelled if row.current_bucket == row.expected_bucket]
    atoms_correct = [row for row in labelled if row.atoms_bucket == row.expected_bucket]

    return {
        "rows_total": len(items),
        "labelled_rows": len(labelled),
        "changed_bucket_count": len([row for row in items if row.current_bucket != row.atoms_bucket]),
        "current_primary_precision": _precision("current"),
        "atoms_primary_precision": _precision("atoms"),
        "current_bad_primary_count": len(current_bad_primary),
        "atoms_bad_primary_count": len(atoms_bad_primary),
        "target_lift_count": len(target_lift),
        "current_bucket_accuracy": round(len(current_correct) / len(labelled), 4) if labelled else None,
        "atoms_bucket_accuracy": round(len(atoms_correct) / len(labelled), 4) if labelled else None,
        "diff_types": {
            key: len([row for row in items if row.diff_type == key])
            for key in sorted({row.diff_type for row in items})
        },
    }


def write_artifacts(
    result: ComparisonResult,
    *,
    output_dir: Path,
    sku_atoms: list[SkuAtoms],
    query_atoms: list[QueryAtomsRecord],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    result.output_dir = str(output_dir)
    (output_dir / "comparison.json").write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    with (output_dir / "comparison.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "nm_id",
            "query",
            "cluster_key",
            "ranking_value_used",
            "current_bucket",
            "current_score",
            "atoms_bucket",
            "atoms_score",
            "expected_bucket",
            "diff_type",
            "current_reasons",
            "atoms_reasons",
            "matched_atoms",
            "missing_atoms",
            "conflict_atoms",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in result.rows:
            data = row.model_dump(mode="json")
            for key in ("current_reasons", "atoms_reasons", "matched_atoms", "missing_atoms", "conflict_atoms"):
                data[key] = " | ".join(data.get(key) or [])
            writer.writerow({key: data.get(key) for key in fieldnames})
    (output_dir / "metrics.json").write_text(
        json.dumps(result.metrics, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    with (output_dir / "sku_atoms.jsonl").open("w", encoding="utf-8") as handle:
        for item in sku_atoms:
            handle.write(json.dumps(item.model_dump(mode="json"), ensure_ascii=False, default=str) + "\n")
    with (output_dir / "query_atoms.jsonl").open("w", encoding="utf-8") as handle:
        for item in query_atoms:
            handle.write(json.dumps(item.model_dump(mode="json"), ensure_ascii=False, default=str) + "\n")
    (output_dir / "report.md").write_text(_render_report(result), encoding="utf-8")


def _render_report(result: ComparisonResult) -> str:
    lines = [
        "# LLM Meaning Atoms Shadow Experiment",
        "",
        f"Project: `{result.project_id}`",
        f"Category: `{result.category_id}`",
        f"SKU count: `{len(result.nm_ids)}`",
        "",
        "## Metrics",
        "",
        "```json",
        json.dumps(result.metrics, ensure_ascii=False, indent=2, default=str),
        "```",
        "",
        "## Bad Primary Removed",
        "",
    ]
    removed = [
        row
        for row in result.rows
        if row.current_bucket == "primary" and row.atoms_bucket != "primary"
    ][:30]
    if not removed:
        lines.append("No current Primary rows were downgraded by atoms matcher.")
    for row in removed:
        lines.append(f"- `{row.nm_id}` `{row.query}`: current `{row.current_bucket}` -> atoms `{row.atoms_bucket}`")
        if row.conflict_atoms or row.missing_atoms:
            lines.append(f"  - conflicts/missing: {', '.join([*row.conflict_atoms, *row.missing_atoms][:5])}")

    lines.extend(["", "## Target Lift", ""])
    lifted = [
        row
        for row in result.rows
        if row.current_bucket != "primary" and row.atoms_bucket == "primary"
    ][:30]
    if not lifted:
        lines.append("No rows were lifted to Primary by atoms matcher.")
    for row in lifted:
        lines.append(f"- `{row.nm_id}` `{row.query}`: current `{row.current_bucket}` -> atoms `primary`")
        if row.matched_atoms:
            lines.append(f"  - matched: {', '.join(row.matched_atoms[:5])}")

    lines.extend(["", "## Questionable Changes", ""])
    questionable = [
        row
        for row in result.rows
        if row.expected_bucket and row.atoms_bucket != row.expected_bucket
    ][:30]
    if not questionable:
        lines.append("No labelled rows disagree with atoms matcher.")
    for row in questionable:
        lines.append(
            f"- `{row.nm_id}` `{row.query}`: expected `{row.expected_bucket}`, atoms `{row.atoms_bucket}`, current `{row.current_bucket}`"
        )
    lines.append("")
    return "\n".join(lines)

