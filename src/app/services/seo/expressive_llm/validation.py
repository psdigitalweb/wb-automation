"""Validation helpers for expressive LLM outputs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceSpanCheck:
    span: str
    found_in_evidence: bool


@dataclass(frozen=True)
class VibeValidation:
    label: str
    confidence: float
    evidence_spans: list[EvidenceSpanCheck]
    evidence_valid: bool
    hallucinated: bool
    issues: list[str]


@dataclass(frozen=True)
class ValidationReport:
    vibes_total: int
    vibes_kept: int
    vibes_dropped: int
    evidence_total: int
    evidence_found: int
    evidence_missing: int
    evidence_quality: float
    vibes: list[VibeValidation]


def validate_evidence_spans(*, evidence_spans: list[str], evidence_text: str) -> tuple[list[EvidenceSpanCheck], bool]:
    checks: list[EvidenceSpanCheck] = []
    for span in evidence_spans:
        s = str(span or "")
        checks.append(EvidenceSpanCheck(span=s, found_in_evidence=(s in evidence_text)))
    ok = all(item.found_in_evidence for item in checks) if checks else False
    return checks, ok
