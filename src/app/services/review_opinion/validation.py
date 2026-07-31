"""Strict parsing and semantic validation for model-produced opinion data."""

from __future__ import annotations

import json
from typing import Any, Mapping

from pydantic import ValidationError

from .contracts import ReviewOpinionFinding, ReviewOpinionModelOutput
from .input_builder import normalize_text


class ReviewOpinionOutputError(ValueError):
    def __init__(self, errors: list[str], *, raw_output: str = "") -> None:
        super().__init__("; ".join(errors))
        self.errors = errors
        self.raw_output = raw_output


def parse_strict_json(content: Any) -> dict[str, Any]:
    if isinstance(content, Mapping):
        return dict(content)
    raw = str(content or "").strip()
    if not raw:
        raise ReviewOpinionOutputError(["empty_model_content"], raw_output=raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReviewOpinionOutputError(
            [f"invalid_json:{exc.msg}:line_{exc.lineno}:column_{exc.colno}"],
            raw_output=raw,
        ) from exc
    if not isinstance(parsed, dict):
        raise ReviewOpinionOutputError(["model_output_must_be_object"], raw_output=raw)
    return parsed


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _validate_finding(
    finding: ReviewOpinionFinding,
    *,
    review_fields: Mapping[str, tuple[str, ...]],
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    supporting_ids = _dedupe(finding.supporting_review_ids)
    unknown = [review_id for review_id in supporting_ids if review_id not in review_fields]
    if unknown:
        errors.append(f"unknown_supporting_review_ids:{','.join(unknown[:10])}")

    evidence: list[dict[str, str]] = []
    for item in finding.evidence:
        fields = review_fields.get(item.review_id)
        if fields is None:
            errors.append(f"unknown_evidence_review_id:{item.review_id}")
            continue
        if item.review_id not in supporting_ids:
            errors.append(f"evidence_id_not_in_supporting_ids:{item.review_id}")
        quote = normalize_text(item.quote)
        if not quote or not any(quote in field for field in fields):
            errors.append(f"quote_not_found:{item.review_id}")
            continue
        evidence.append({"review_id": item.review_id, "quote": quote})

    return (
        {
            "label": finding.label.strip(),
            "category": finding.category,
            "summary": finding.summary.strip(),
            "confidence": finding.confidence,
            "supporting_review_ids": supporting_ids,
            "support_count": len(supporting_ids),
            "evidence": evidence,
        },
        errors,
    )


def validate_and_normalize_output(
    parsed: Mapping[str, Any],
    *,
    review_fields: Mapping[str, tuple[str, ...]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        model_output = ReviewOpinionModelOutput.model_validate(dict(parsed))
    except ValidationError as exc:
        messages = [
            f"schema:{'.'.join(str(part) for part in item['loc'])}:{item['msg']}"
            for item in exc.errors()
        ]
        raise ReviewOpinionOutputError(messages) from exc

    errors: list[str] = []
    strengths: list[dict[str, Any]] = []
    weaknesses: list[dict[str, Any]] = []
    isolated: list[dict[str, Any]] = []
    seen_labels: set[str] = set()

    def append_finding(finding: ReviewOpinionFinding, destination: list[dict[str, Any]], sentiment: str) -> None:
        normalized, finding_errors = _validate_finding(finding, review_fields=review_fields)
        errors.extend(finding_errors)
        label_key = normalize_text(normalized["label"]).casefold()
        if label_key in seen_labels:
            errors.append(f"duplicate_theme_label:{normalized['label']}")
            return
        seen_labels.add(label_key)
        if normalized["support_count"] < 2:
            isolated.append({**normalized, "sentiment": sentiment})
        else:
            destination.append(normalized)

    for finding in model_output.strengths:
        append_finding(finding, strengths, "positive")
    for finding in model_output.weaknesses:
        append_finding(finding, weaknesses, "negative")
    for finding in model_output.isolated_observations:
        normalized, finding_errors = _validate_finding(finding, review_fields=review_fields)
        errors.extend(finding_errors)
        label_key = normalize_text(normalized["label"]).casefold()
        if label_key in seen_labels:
            errors.append(f"duplicate_theme_label:{normalized['label']}")
            continue
        seen_labels.add(label_key)
        isolated.append({**normalized, "sentiment": finding.sentiment})

    conflicts: list[dict[str, Any]] = []
    for conflict in model_output.conflicts:
        positive_ids = _dedupe(conflict.positive_review_ids)
        negative_ids = _dedupe(conflict.negative_review_ids)
        unknown = [
            review_id
            for review_id in positive_ids + negative_ids
            if review_id not in review_fields
        ]
        if unknown:
            errors.append(f"unknown_conflict_review_ids:{','.join(unknown[:10])}")
            continue
        conflicts.append(
            {
                "label": conflict.label.strip(),
                "summary": conflict.summary.strip(),
                "positive_review_ids": positive_ids,
                "negative_review_ids": negative_ids,
            }
        )

    if errors:
        raise ReviewOpinionOutputError(errors)

    result = {
        "schema_version": model_output.schema_version,
        "overall_conclusion": model_output.overall_conclusion.strip(),
        "strengths": strengths[:8],
        "weaknesses": weaknesses[:8],
        "isolated_observations": isolated[:12],
        "conflicts": conflicts[:8],
    }
    validation = {
        "status": "passed",
        "review_ids_available": len(review_fields),
        "strengths_count": len(result["strengths"]),
        "weaknesses_count": len(result["weaknesses"]),
        "isolated_count": len(result["isolated_observations"]),
        "conflicts_count": len(result["conflicts"]),
        "evidence_quotes_valid": True,
    }
    return result, validation
