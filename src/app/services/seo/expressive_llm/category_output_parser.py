"""Parser + validator for category expressive LLM outputs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.services.seo.expressive_llm.validation import ValidationReport, VibeValidation, validate_evidence_spans


_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedCategoryExpressiveResult:
    parsed: dict[str, Any]
    validation: ValidationReport


def _extract_json_object(content: str) -> dict[str, Any]:
    text_value = str(content or "").strip()
    if text_value.startswith("```"):
        text_value = _CODE_FENCE_RE.sub("", text_value).strip()
    start = text_value.find("{")
    end = text_value.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError("Model response does not contain JSON object")
    obj = json.loads(text_value[start : end + 1])
    if not isinstance(obj, dict):
        raise ValueError("Parsed JSON is not an object")
    return obj


def parse_and_validate_category_expressive_output(
    *,
    content: str,
    evidence_text: str,
    max_vibes: int = 5,
    strict: bool = True,
) -> ParsedCategoryExpressiveResult:
    """Parse model content and validate schema + evidence spans.

    Hard rules (iteration 19):
    - vibes <= 5
    - each vibe has label, confidence [0..1], evidence_spans length is 2..3
    - each evidence span <= 80 chars and has no newline
    - each evidence span must be exact substring of evidence_text
    """

    parsed_raw = _extract_json_object(content)

    vibes_raw = parsed_raw.get("vibes")
    if vibes_raw is None:
        vibes_raw = []
    if not isinstance(vibes_raw, list):
        raise ValueError("vibes must be a list")
    if len(vibes_raw) > int(max_vibes):
        if strict:
            raise ValueError(f"too many vibes: {len(vibes_raw)} > {max_vibes}")
        vibes_raw = vibes_raw[: int(max_vibes)]

    validations: list[VibeValidation] = []
    kept_vibes: list[dict[str, Any]] = []
    evidence_total = 0
    evidence_found = 0

    for item in vibes_raw:
        if not isinstance(item, dict):
            if strict:
                raise ValueError("vibe item must be an object")
            continue

        label = str(item.get("label") or "").strip()
        if not label:
            if strict:
                raise ValueError("vibe.label must be non-empty")
            continue

        conf_raw = item.get("confidence")
        try:
            confidence = float(conf_raw)
        except Exception as exc:  # noqa: BLE001
            if strict:
                raise ValueError("vibe.confidence must be a number") from exc
            confidence = 0.0
        if confidence < 0.0 or confidence > 1.0:
            if strict:
                raise ValueError("vibe.confidence must be within [0, 1]")
            confidence = min(1.0, max(0.0, confidence))

        spans_raw = item.get("evidence_spans")
        if not isinstance(spans_raw, list):
            if strict:
                raise ValueError("vibe.evidence_spans must be a list")
            continue

        spans = [str(s or "").strip() for s in spans_raw if str(s or "").strip()]
        issues: list[str] = []

        if len(spans) < 2:
            if strict:
                raise ValueError("vibe.evidence_spans must have length 2..3")
            # Not salvageable deterministically without inventing quotes → drop vibe.
            continue

        if len(spans) > 3:
            if strict:
                raise ValueError("vibe.evidence_spans must have length 2..3")
            spans = spans[:3]
            issues.append("truncated_evidence_spans")

        invalid_span = False
        for span in spans:
            if "\n" in span or "\r" in span:
                invalid_span = True
                break
            if len(span) > 80:
                invalid_span = True
                break
        if invalid_span:
            if strict:
                raise ValueError("evidence span must be <= 80 chars and contain no newlines")
            continue

        checks, ok = validate_evidence_spans(evidence_spans=spans, evidence_text=evidence_text)
        evidence_total += len(checks)
        evidence_found += sum(1 for c in checks if c.found_in_evidence)
        if not ok:
            issues.append("missing_evidence_span")

        validations.append(
            VibeValidation(
                label=label,
                confidence=confidence,
                evidence_spans=checks,
                evidence_valid=bool(ok),
                hallucinated=(not ok),
                issues=issues,
            )
        )
        kept_vibes.append({"label": label, "confidence": confidence, "evidence_spans": spans})

    evidence_missing = evidence_total - evidence_found
    quality = (float(evidence_found) / float(evidence_total)) if evidence_total > 0 else 1.0

    report = ValidationReport(
        vibes_total=int(len(vibes_raw)),
        vibes_kept=int(len(kept_vibes)),
        vibes_dropped=int(len(vibes_raw) - len(kept_vibes)),
        evidence_total=int(evidence_total),
        evidence_found=int(evidence_found),
        evidence_missing=int(evidence_missing),
        evidence_quality=float(quality),
        vibes=validations,
    )

    parsed: dict[str, Any] = {
        "version": str(parsed_raw.get("version") or "v1"),
        "task": str(parsed_raw.get("task") or "category"),
        "category_name": str(parsed_raw.get("category_name") or ""),
        "vibes": kept_vibes,
        "summary": str(parsed_raw.get("summary") or ""),
    }
    return ParsedCategoryExpressiveResult(parsed=parsed, validation=report)
