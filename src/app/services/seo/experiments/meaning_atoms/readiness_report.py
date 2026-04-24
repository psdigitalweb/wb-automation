"""Matcher readiness report for meaning atoms shadow runs."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_THRESHOLDS = {
    "min_labelled_rows": 150,
    "min_primary_precision": 0.85,
    "max_bad_primary": 5,
    "min_bad_primary_reduction": 0.8,
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _pct(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return str(value)


def build_matcher_readiness_payload(
    *,
    run_dir: Path,
    thresholds: dict[str, float | int] | None = None,
) -> dict[str, Any]:
    thresholds = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    metrics = _read_json(run_dir / "metrics.json")
    errors = _read_csv(run_dir / "error_analysis_v1_2_labelled_only.csv")
    if not errors:
        errors = _read_csv(run_dir / "error_analysis_v1_1_labelled_only.csv")
    if not errors:
        errors = _read_csv(run_dir / "error_analysis_labelled_only.csv")

    current_bad_primary = int(metrics.get("current_bad_primary_count") or 0)
    atoms_bad_primary = int(metrics.get("atoms_bad_primary_count") or 0)
    reduction = 1.0 if current_bad_primary == 0 else round((current_bad_primary - atoms_bad_primary) / current_bad_primary, 4)
    checks = {
        "labelled_rows": int(metrics.get("labelled_rows") or 0) >= int(thresholds["min_labelled_rows"]),
        "primary_precision": float(metrics.get("atoms_primary_precision") or 0.0) >= float(thresholds["min_primary_precision"]),
        "bad_primary": atoms_bad_primary <= int(thresholds["max_bad_primary"]),
        "bad_primary_reduction": reduction >= float(thresholds["min_bad_primary_reduction"]),
    }
    residual_by_issue = Counter(row.get("auto_issue_type") or "unknown" for row in errors)
    residual_by_root = Counter(row.get("auto_root_cause") or "unknown" for row in errors)
    status = "ready_as_primary_eligibility_layer" if all(checks.values()) else "needs_more_shadow_work"
    if status == "ready_as_primary_eligibility_layer" and float(metrics.get("atoms_bucket_accuracy") or 0.0) < 0.75:
        status = "ready_as_primary_eligibility_layer_not_full_bucket_replacement"
    return {
        "run_dir": str(run_dir),
        "status": status,
        "thresholds": thresholds,
        "checks": checks,
        "metrics": metrics,
        "bad_primary_reduction": reduction,
        "residual_error_count": len(errors),
        "residual_by_issue": dict(residual_by_issue.most_common()),
        "residual_by_root_cause": dict(residual_by_root.most_common()),
        "integration_recommendation": (
            "Use Atoms v1.2 as a pre-matcher eligibility and Primary gate. "
            "Do not use it as a full bucket replacement until query/SKU atom extraction improves."
        ),
    }


def render_matcher_readiness_report(payload: dict[str, Any]) -> str:
    metrics = payload["metrics"]
    lines = [
        "# Meaning Atoms Matcher Readiness",
        "",
        f"Status: `{payload['status']}`",
        "",
        "## Decision",
        "",
        payload["integration_recommendation"],
        "",
        "## Metrics",
        "",
        f"- Labelled rows: `{metrics.get('labelled_rows')}`",
        f"- Current Primary precision: `{_pct(metrics.get('current_primary_precision'))}`",
        f"- Atoms Primary precision: `{_pct(metrics.get('atoms_primary_precision'))}`",
        f"- Current bad Primary: `{metrics.get('current_bad_primary_count')}`",
        f"- Atoms bad Primary: `{metrics.get('atoms_bad_primary_count')}`",
        f"- Bad Primary reduction: `{_pct(payload.get('bad_primary_reduction'))}`",
        f"- Bucket accuracy: `{_pct(metrics.get('atoms_bucket_accuracy'))}`",
        f"- Target lift: `{metrics.get('target_lift_count')}`",
        "",
        "## Readiness Checks",
        "",
    ]
    for key, ok in payload["checks"].items():
        lines.append(f"- `{key}`: `{'pass' if ok else 'fail'}`")
    lines.extend(["", "## Residual Errors", ""])
    for key, value in payload["residual_by_issue"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Root Causes", ""])
    for key, value in payload["residual_by_root_cause"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Matcher Contract",
            "",
            "- LLM extracts SKU/query atoms; matcher does not use pairwise LLM.",
            "- Hard conflicts and missing hard requirements cap or reject before score.",
            "- Frequency is only a tie-breaker after eligibility.",
            "- Primary is allowed only after a meaningful atom match, not raw lexical frequency.",
            "- Remaining Broad/Secondary/Rejection disagreements should be solved by better atom extraction, not by frequency boosts.",
            "",
        ]
    )
    return "\n".join(lines)


def write_matcher_readiness_report(run_dir: Path) -> dict[str, Any]:
    payload = build_matcher_readiness_payload(run_dir=run_dir)
    (run_dir / "matcher_readiness.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (run_dir / "matcher_readiness.md").write_text(
        render_matcher_readiness_report(payload),
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Write matcher readiness report for a meaning atoms shadow run.")
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    payload = write_matcher_readiness_report(args.run_dir)
    print(json.dumps({"status": payload["status"], "run_dir": str(args.run_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
