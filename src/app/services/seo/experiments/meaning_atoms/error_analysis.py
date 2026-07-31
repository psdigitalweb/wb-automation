"""Build human-review CSVs for meaning atoms shadow experiment errors."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any


ERROR_TYPE_OPTIONS = (
    "label_wrong",
    "query_atoms_wrong",
    "sku_atoms_missing",
    "vision_atoms_wrong",
    "matcher_too_strict",
    "matcher_too_soft",
    "current_ok",
    "ignore",
)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "review_status",
        "user_error_type",
        "user_correct_bucket",
        "user_comment",
        "auto_issue_type",
        "auto_root_cause",
        "nm_id",
        "query",
        "cluster_key",
        "ranking_value_used",
        "expected_bucket",
        "current_bucket",
        "current_score",
        "atoms_bucket",
        "atoms_score",
        "diff_type",
        "matched_atoms",
        "missing_atoms",
        "conflict_atoms",
        "current_reasons",
        "atoms_reasons",
        "error_type_options",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _issue_type(row: dict[str, str]) -> str:
    expected = row.get("expected_bucket") or ""
    atoms = row.get("atoms_bucket") or ""
    current = row.get("current_bucket") or ""
    if expected and atoms != expected:
        if atoms == "primary" and expected != "primary":
            return "atoms_false_primary"
        if atoms == "rejected" and expected != "rejected":
            return "atoms_false_reject"
        if expected == "primary" and atoms != "primary":
            return "atoms_under_promoted"
        if expected == "rejected" and atoms != "rejected":
            return "atoms_under_rejected"
        return "atoms_bucket_mismatch"
    if not expected and atoms == "primary" and current != "primary":
        return "unlabeled_atoms_lift"
    if not expected and current == "primary" and atoms != "primary":
        return "unlabeled_bad_primary_removed"
    if not expected and atoms == "rejected":
        return "unlabeled_atoms_reject"
    return "review_optional"


def _root_cause(row: dict[str, str]) -> str:
    text = " ".join(
        [
            row.get("query") or "",
            row.get("missing_atoms") or "",
            row.get("conflict_atoms") or "",
            row.get("atoms_reasons") or "",
        ]
    ).lower()
    if "product_type conflict" in text or "термокруж" in text:
        return "product_type_or_subtype"
    if any(marker in text for marker in ("volume_ml", "numeric mismatch", "мл")):
        return "numeric_volume"
    if "quantity" in text or "набор" in text or "комплект" in text:
        return "quantity_or_set"
    if any(marker in text for marker in ("recipient", "пап", "мам", "подруг", "муж", "жен")):
        return "recipient_or_audience"
    if any(marker in text for marker in ("без рисун", "print", "motif", "цвет")):
        return "visual_or_design"
    if any(marker in text for marker in ("кофемаш", "машину", "compatibility", "car")):
        return "compatibility_or_use_case"
    if any(marker in text for marker in ("крыш", "сеточ", "ситеч", "фильтр", "ложк", "подстав")):
        return "accessory_not_sku"
    if "low-signal" in text or "product-only" in text:
        return "low_signal_query"
    if "expressive" in text or "мила" in text or "красив" in text or "прикол" in text:
        return "expressive_fit"
    return "policy_or_label"


def build_error_analysis_rows(rows: list[dict[str, str]], *, include_unlabeled: bool = True) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        expected = row.get("expected_bucket") or ""
        atoms = row.get("atoms_bucket") or ""
        current = row.get("current_bucket") or ""
        labelled_error = bool(expected and atoms != expected)
        interesting_unlabelled = bool(
            include_unlabeled
            and not expected
            and (
                atoms == "primary"
                or atoms == "rejected"
                or (current == "primary" and atoms != "primary")
            )
        )
        if not labelled_error and not interesting_unlabelled:
            continue
        item = dict(row)
        item.update(
            {
                "review_status": "todo",
                "user_error_type": "",
                "user_correct_bucket": expected,
                "user_comment": "",
                "auto_issue_type": _issue_type(row),
                "auto_root_cause": _root_cause(row),
                "error_type_options": " | ".join(ERROR_TYPE_OPTIONS),
            }
        )
        selected.append(item)
    selected.sort(
        key=lambda item: (
            0 if item["expected_bucket"] else 1,
            item["nm_id"],
            item["auto_issue_type"],
            item["query"],
        )
    )
    return selected


def build_error_analysis_csv(comparison_csv: Path, output_csv: Path, *, include_unlabeled: bool = True) -> int:
    rows = build_error_analysis_rows(_read_rows(comparison_csv), include_unlabeled=include_unlabeled)
    _write_rows(output_csv, rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a human-review error analysis CSV from meaning atoms comparison.csv.")
    parser.add_argument("--comparison-csv", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--labelled-only", action="store_true")
    args = parser.parse_args()
    count = build_error_analysis_csv(
        args.comparison_csv,
        args.output_csv,
        include_unlabeled=not args.labelled_only,
    )
    print(f"Wrote {count} rows to {args.output_csv}")


if __name__ == "__main__":
    main()
