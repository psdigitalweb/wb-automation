from __future__ import annotations

import json

import pytest

from app.services.seo.expressive_llm.category_output_parser import parse_and_validate_category_expressive_output


def test_parser_accepts_code_fences_and_validates_exact_evidence_spans():
    evidence_text = "AAA\nBBB\nCCC"
    content = """```json
{
  "version": "v1",
  "task": "category",
  "category_name": "X",
  "vibes": [
    {"label":"cute","confidence":0.9,"evidence_spans":["AAA","BBB"]},
    {"label":"aesthetic","confidence":0.5,"evidence_spans":["CCC","AAA","BBB"]}
  ],
  "summary":""
}
```"""
    result = parse_and_validate_category_expressive_output(content=content, evidence_text=evidence_text)
    assert result.parsed["category_name"] == "X"
    assert result.validation.evidence_total == 5
    assert result.validation.evidence_missing == 0
    assert result.validation.evidence_quality == 1.0
    assert all(v.evidence_valid for v in result.validation.vibes)


def test_parser_rejects_invalid_json():
    with pytest.raises(ValueError):
        parse_and_validate_category_expressive_output(content="{", evidence_text="x")


def test_parser_rejects_too_many_vibes():
    payload = {"vibes": [{"label": "x", "confidence": 0.1, "evidence_spans": ["a", "b"]}] * 6}
    with pytest.raises(ValueError):
        parse_and_validate_category_expressive_output(content=json.dumps(payload), evidence_text="a\nb")


def test_parser_strict_rejects_bad_evidence_spans_count_and_length():
    payload = {"vibes": [{"label": "x", "confidence": 0.1, "evidence_spans": ["a"]}]}
    with pytest.raises(ValueError):
        parse_and_validate_category_expressive_output(content=json.dumps(payload), evidence_text="a", strict=True)

    payload = {"vibes": [{"label": "x", "confidence": 0.1, "evidence_spans": ["a", "b", "c", "d"]}]}
    with pytest.raises(ValueError):
        parse_and_validate_category_expressive_output(content=json.dumps(payload), evidence_text="a\nb\nc\nd", strict=True)

    payload = {"vibes": [{"label": "x", "confidence": 0.1, "evidence_spans": ["a" * 81, "b"]}]}
    with pytest.raises(ValueError):
        parse_and_validate_category_expressive_output(content=json.dumps(payload), evidence_text="a\nb", strict=True)

    payload = {"vibes": [{"label": "x", "confidence": 0.1, "evidence_spans": ["a\nb", "b"]}]}
    with pytest.raises(ValueError):
        parse_and_validate_category_expressive_output(content=json.dumps(payload), evidence_text="a\nb", strict=True)


def test_parser_lenient_drops_or_truncates_invalid_vibes():
    # 1 evidence span -> dropped
    payload = {"category_name": "X", "vibes": [{"label": "x", "confidence": 0.1, "evidence_spans": ["a"]}]}
    res = parse_and_validate_category_expressive_output(content=json.dumps(payload), evidence_text="a", strict=False)
    assert res.parsed["vibes"] == []
    assert res.validation.vibes_total == 1
    assert res.validation.vibes_kept == 0
    assert res.validation.vibes_dropped == 1

    # 4 evidence spans -> truncated to 3
    payload = {"category_name": "X", "vibes": [{"label": "x", "confidence": 0.1, "evidence_spans": ["a", "b", "c", "d"]}]}
    res = parse_and_validate_category_expressive_output(content=json.dumps(payload), evidence_text="a\nb\nc\nd", strict=False)
    assert res.parsed["vibes"][0]["evidence_spans"] == ["a", "b", "c"]
    assert res.validation.vibes_kept == 1

    # invalid span (newline/too long) -> dropped
    payload = {"category_name": "X", "vibes": [{"label": "x", "confidence": 0.1, "evidence_spans": ["a\nb", "b"]}]}
    res = parse_and_validate_category_expressive_output(content=json.dumps(payload), evidence_text="a\nb", strict=False)
    assert res.parsed["vibes"] == []


def test_validator_marks_missing_span_as_hallucination_without_raising():
    payload = {"vibes": [{"label": "x", "confidence": 0.1, "evidence_spans": ["a", "missing"]}]}
    result = parse_and_validate_category_expressive_output(content=json.dumps(payload), evidence_text="a\nb")
    assert result.validation.evidence_total == 2
    assert result.validation.evidence_missing == 1
    assert result.validation.vibes[0].hallucinated is True
    assert result.validation.vibes[0].evidence_valid is False
