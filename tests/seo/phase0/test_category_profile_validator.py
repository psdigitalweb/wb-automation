from __future__ import annotations

import copy
import json
from pathlib import Path

from app.services.seo.category_profile_validator import validate_category_profile_payload
from app.services.seo.global_vocabulary import load_global_vocabulary


TEMPLATE_PATH = Path("config/seo/category_profiles/templates/812_skeleton_v1.json")


def _template_payload() -> dict[str, object]:
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


def test_validator_accepts_step3_skeleton_template() -> None:
    report = validate_category_profile_payload(
        _template_payload(),
        vocabulary=load_global_vocabulary(),
        subject_match_share=0.984,
    )

    assert report.status == "passed"
    assert all(item.result != "fail" for item in report.checks)


def test_validator_rejects_missing_subject_primary() -> None:
    payload = copy.deepcopy(_template_payload())
    payload["subject"]["primary"] = ""

    report = validate_category_profile_payload(payload, vocabulary=load_global_vocabulary(), subject_match_share=0.984)

    assert report.status == "failed"
    assert any(item.name == "subject_non_empty" and item.result == "fail" for item in report.checks)


def test_validator_rejects_bad_bucket_cutoffs() -> None:
    payload = copy.deepcopy(_template_payload())
    payload["scoring"]["bucket_cutoffs"] = {"primary": 0.30, "secondary": 0.35, "broad": 0.15}

    report = validate_category_profile_payload(payload, vocabulary=load_global_vocabulary(), subject_match_share=0.984)

    assert report.status == "failed"
    assert any(item.name == "bucket_cutoffs_monotonic" and item.result == "fail" for item in report.checks)


def test_validator_rejects_cross_category_duplication() -> None:
    payload = copy.deepcopy(_template_payload())
    payload["recipient_synonyms"] = {"мам": "мама"}

    report = validate_category_profile_payload(payload, vocabulary=load_global_vocabulary(), subject_match_share=0.984)

    assert report.status == "failed"
    assert any(item.name == "no_cross_category_duplication" and item.result == "fail" for item in report.checks)
