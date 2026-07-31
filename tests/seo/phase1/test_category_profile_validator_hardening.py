from __future__ import annotations

import copy

from app.services.seo.category_profile_derive_builder import build_category_profile_draft
from app.services.seo.category_profile_validator import validate_category_profile_payload
from app.services.seo.global_vocabulary import load_global_vocabulary


def _evidence() -> dict[str, object]:
    return {
        "project_id": 1,
        "category_id": 76010,
        "evidence_hash": "sha256:validator-hardening-synthetic",
        "corpus": {
            "query_count": 4,
            "distinct_query_count": 4,
            "top_queries_count": 4,
            "total_frequency": "125",
            "nonzero_frequency_count": 4,
            "source_payload_keys_sample": ["raw_query"],
            "economic_field_names_present": ["orders", "conversion"],
            "notes": [],
        },
        "query_candidates": [
            {
                "normalized_query": "carrier travel mode",
                "display_query": "Carrier travel mode",
                "frequency_total": "80",
                "raw_row_count": 1,
            },
            {
                "normalized_query": "case compact",
                "display_query": "Case compact",
                "frequency_total": "30",
                "raw_row_count": 1,
            },
        ],
        "query_token_counts": {
            "carrier": 100,
            "travel": 80,
            "mode": 80,
            "case": 30,
            "compact": 30,
            "sleeve": 10,
        },
        "axes": {
            "axes_id": 12,
            "schema_version": "category_meaning_axes_v0",
            "source": "deterministic",
            "evidence_hash": "axes-hash",
            "input_hash": "axes-input",
            "axes_payload": {
                "product_type_axes": ["carrier", "case", "sleeve"],
                "constraint_axes": ["travel mode"],
                "synonym_groups": [
                    {"label": "carrier", "variants": ["carrier bag"]},
                    {"label": "case", "variants": ["protective case"]},
                ],
            },
        },
        "diagnostics": {"status": "ready"},
    }


def _valid_payload() -> dict[str, object]:
    return copy.deepcopy(build_category_profile_draft(_evidence()).profile_payload)


def _report(payload: dict[str, object]):
    return validate_category_profile_payload(payload, vocabulary=load_global_vocabulary())


def _check_result(payload: dict[str, object], check_name: str) -> str:
    report = _report(payload)
    for item in report.checks:
        if item.name == check_name:
            return item.result
    raise AssertionError(f"missing check {check_name}")


def test_step1_to_step4_generated_draft_passes_hardened_validator() -> None:
    payload = _valid_payload()

    report = _report(payload)

    assert report.status == "passed"
    assert {item.name for item in report.checks} >= {
        "operational_sections_present",
        "subject_alias_safety",
        "constraints_structure",
        "scoring_labels_structure",
        "guards_structure",
        "no_economic_decision_fields",
        "generated_by_auditability",
    }


def test_missing_required_operational_sections_fail_clearly() -> None:
    payload = _valid_payload()
    payload.pop("query_guards")
    payload.pop("sku_guards")

    report = _report(payload)

    assert report.status == "failed"
    failing = {item.name: item.detail for item in report.checks if item.result == "fail"}
    assert "operational_sections_present" in failing
    assert "query_guards must be an object" in str(failing["operational_sections_present"])
    assert "sku_guards must be an object" in str(failing["operational_sections_present"])


def test_malformed_constraints_fail_with_actionable_check() -> None:
    payload = _valid_payload()
    payload["constraints"] = {
        "derive_from_query_tokens": [{"constraint": "", "when_query_contains_any": []}],
        "derive_from_sku_meaning": "not-a-list",
    }

    assert _check_result(payload, "constraints_structure") == "fail"
    assert _check_result(payload, "constraint_references") == "pass"


def test_malformed_guards_fail_with_actionable_check() -> None:
    payload = _valid_payload()
    payload["query_guards"] = {
        "product_type_detection": [{"when_contains": "", "set_product_type": ""}],
        "required_atoms": [{"when_contains": "travel mode", "atom": {"type": "use_case"}}],
        "excluded_atoms": "not-a-list",
    }

    report = _report(payload)

    assert report.status == "failed"
    assert any(item.name == "guards_structure" and item.result == "fail" for item in report.checks)


def test_orders_and_conversion_in_decision_sections_fail() -> None:
    payload = _valid_payload()
    payload["scoring"]["weights"]["orders_boost"] = 0.2
    payload["user_bucket_labels"]["primary"] = "Best conversion queries"
    payload["query_guards"]["required_atoms"].append(
        {
            "when_contains": "orders",
            "atom": {"type": "use_case", "field": "use_case", "value": "orders"},
        }
    )

    report = _report(payload)

    assert report.status == "failed"
    check = next(item for item in report.checks if item.name == "no_economic_decision_fields")
    assert check.result == "fail"
    assert "scoring" in str(check.detail)
    assert "query_guards" in str(check.detail)
    assert "user_bucket_labels" in str(check.detail)


def test_generated_by_diagnostics_are_auditable_or_controlled_skip() -> None:
    missing_generated_by = _valid_payload()
    missing_generated_by.pop("generated_by")
    missing_report = _report(missing_generated_by)

    assert missing_report.status == "passed"
    assert any(
        item.name == "generated_by_auditability" and item.result == "skip"
        for item in missing_report.checks
    )

    too_empty = _valid_payload()
    too_empty["generated_by"] = {"method": "generic_heuristic_profile_builder_v1"}

    report = _report(too_empty)

    assert report.status == "failed"
    check = next(item for item in report.checks if item.name == "generated_by_auditability")
    assert check.result == "fail"
    assert "evidence_hash" in str(check.detail)
    assert "builder diagnostics" in str(check.detail)
