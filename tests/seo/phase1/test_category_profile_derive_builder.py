from __future__ import annotations

import copy

import pytest

from app.services.seo.category_profile import CategoryProfile
from app.services.seo.category_profile_derive_builder import (
    BUILDER_METHOD,
    WeakProfileEvidenceError,
    build_category_profile_draft,
)
from app.services.seo.category_profile_validator import validate_category_profile_payload
from app.services.seo.global_vocabulary import load_global_vocabulary


def _evidence(*, category_id: int = 73010, product_type_axes: list[str] | None = None) -> dict[str, object]:
    axes = ["carrier", "case", "sleeve"] if product_type_axes is None else product_type_axes
    return {
        "project_id": 1,
        "category_id": category_id,
        "evidence_hash": f"sha256:synthetic-{category_id}",
        "corpus": {
            "query_count": 5,
            "distinct_query_count": 5,
            "top_queries_count": 4,
            "total_frequency": "116",
            "nonzero_frequency_count": 5,
            "source_payload_keys_sample": ["raw_query"],
            "economic_field_names_present": ["orders", "conversion"],
            "notes": [],
        },
        "query_candidates": [
            {
                "normalized_query": "carrier travel compact",
                "display_query": "Carrier travel compact",
                "frequency_total": "50",
                "raw_row_count": 1,
            }
        ],
        "query_token_counts": {
            "carrier": 100,
            "travel": 40,
            "compact": 30,
            "case": 20,
            "sleeve": 10,
        },
        "axes": {
            "axes_id": 1,
            "schema_version": "category_meaning_axes_v0",
            "source": "deterministic",
            "evidence_hash": "axes-hash",
            "input_hash": "axes-input",
            "axes_payload": {
                "product_type_axes": axes,
                "use_case_axes": ["travel"],
                "audience_axes": ["student"],
                "attribute_axes": ["compact"],
                "synonym_groups": [
                    {"label": "carrier", "variants": ["carrier bag"]},
                    {"label": "case", "variants": ["protective case"]},
                ],
            },
        },
        "diagnostics": {"status": "ready"},
    }


def test_builder_returns_valid_draft_profile_payload() -> None:
    result = build_category_profile_draft(_evidence())
    payload = result.profile_payload

    assert payload["schema_version"] == "category_profile_v1"
    assert payload["subject"]["primary"] == "carrier"
    assert payload["subject"]["primary_aliases"] == ["carrier", "carrier bag"]
    assert payload["generated_by"]["method"] == BUILDER_METHOD

    runtime_profile = CategoryProfile.from_payload(
        profile_id=0,
        project_id=1,
        category_id=73010,
        version="draft",
        payload=payload,
    )
    assert runtime_profile.subject_primary == "carrier"
    assert runtime_profile.bucket_cutoffs["primary"] == 0.60

    self_check = validate_category_profile_payload(payload, vocabulary=load_global_vocabulary())
    assert self_check.status == "passed"


def test_builder_is_deterministic_for_identical_evidence() -> None:
    evidence = _evidence()

    first = build_category_profile_draft(copy.deepcopy(evidence))
    second = build_category_profile_draft(copy.deepcopy(evidence))

    assert first.profile_payload == second.profile_payload
    assert first.diagnostics == second.diagnostics


def test_builder_is_not_tied_to_specific_category_id() -> None:
    first = build_category_profile_draft(_evidence(category_id=73011, product_type_axes=["alpha item", "beta item"]))
    second = build_category_profile_draft(_evidence(category_id=73012, product_type_axes=["gamma item", "delta item"]))

    assert first.profile_payload["subject"]["primary"] == "alpha item"
    assert second.profile_payload["subject"]["primary"] == "gamma item"
    assert "812" not in str(first.profile_payload)
    assert "2841" not in str(first.profile_payload)


def test_builder_does_not_use_economic_fields_in_profile_decisions() -> None:
    payload = build_category_profile_draft(_evidence()).profile_payload
    serialized_scoring = str(payload["scoring"]).lower()
    serialized_labels = str(payload["user_bucket_labels"]).lower()
    serialized_decisions = str(payload["generated_by"]["builder_diagnostics"]).lower()

    assert "orders" not in serialized_scoring
    assert "conversion" not in serialized_scoring
    assert "orders" not in serialized_labels
    assert "conversion" not in serialized_labels
    assert "orders" not in serialized_decisions
    assert "conversion" not in serialized_decisions
    assert payload["generated_by"]["builder_diagnostics"]["economic_fields_used_for_build_decisions"] is False


def test_missing_product_type_axes_is_controlled_failure() -> None:
    with pytest.raises(WeakProfileEvidenceError, match="product_type_axes"):
        build_category_profile_draft(_evidence(product_type_axes=[]))


def test_builder_accepts_primary_subject_hint_without_category_branch() -> None:
    payload = build_category_profile_draft(
        _evidence(product_type_axes=["alpha item", "beta item"]),
        primary_subject_hint="beta item",
    ).profile_payload

    assert payload["subject"]["primary"] == "beta item"
    assert payload["generated_by"]["builder_diagnostics"]["primary_subject_source"] == "primary_subject_hint"


def test_builder_prefers_specific_product_type_over_broad_component_axis() -> None:
    evidence = _evidence(product_type_axes=["pack", "packbox", "case"])
    evidence["query_token_counts"] = {
        "pack": 1000,
        "packbox": 80,
        "case": 20,
    }

    payload = build_category_profile_draft(evidence).profile_payload

    assert payload["subject"]["primary"] == "packbox"
    assert payload["subject"]["primary_aliases"] == ["packbox", "pack"]
    assert payload["subject"]["detection_hints"]["token_prefixes"] == ["packbox", "pack"]
    assert payload["generated_by"]["builder_diagnostics"]["primary_subject_source"] == (
        "product_type_axes_specific_product_type"
    )


def test_specific_primary_component_axis_is_not_related_or_hard_conflict() -> None:
    evidence = _evidence(category_id=88101, product_type_axes=["pack", "packbox", "case"])
    evidence["query_token_counts"] = {
        "pack": 1000,
        "packbox": 80,
        "case": 20,
    }

    payload = build_category_profile_draft(evidence).profile_payload
    related_subjects = {item["subject"] for item in payload["subject"]["related_but_different"]}
    conflict_product_types = {
        rule["when_query_has"]["product_type"]
        for rule in payload["hard_conflicts"]
        if "product_type" in rule["when_query_has"]
    }

    assert payload["subject"]["primary"] == "packbox"
    assert "packbox" not in related_subjects
    assert "pack" not in related_subjects
    assert "packbox" not in conflict_product_types
    assert "pack" not in conflict_product_types


def test_specific_primary_selection_is_category_id_agnostic() -> None:
    first_evidence = _evidence(category_id=2841, product_type_axes=["meal", "mealbox", "case"])
    second_evidence = _evidence(category_id=99002, product_type_axes=["meal", "mealbox", "case"])
    first_evidence["query_token_counts"] = {"meal": 1000, "mealbox": 80, "case": 20}
    second_evidence["query_token_counts"] = {"meal": 1000, "mealbox": 80, "case": 20}

    first = build_category_profile_draft(first_evidence).profile_payload
    second = build_category_profile_draft(second_evidence).profile_payload

    assert first["subject"]["primary"] == "mealbox"
    assert second["subject"]["primary"] == "mealbox"
    assert first["subject"] == second["subject"]


def test_noisy_descriptor_and_use_case_axes_are_skipped_from_related_subjects() -> None:
    evidence = _evidence(
        category_id=99003,
        product_type_axes=[
            "meal",
            "mealbox",
            "kids",
            "small",
            "school",
            "sections",
            "container",
            "kit",
            "case",
        ],
    )
    evidence["query_token_counts"] = {
        "meal": 1000,
        "mealbox": 80,
        "kids": 70,
        "small": 60,
        "school": 50,
        "sections": 40,
        "container": 30,
        "kit": 20,
        "case": 10,
    }
    evidence["query_candidates"] = [
        {"normalized_query": "mealbox kids small school sections", "display_query": "", "frequency_total": "80"},
        {"normalized_query": "container", "display_query": "", "frequency_total": "30"},
        {"normalized_query": "kit", "display_query": "", "frequency_total": "20"},
        {"normalized_query": "case", "display_query": "", "frequency_total": "10"},
    ]
    evidence["axes"]["axes_payload"].update(
        {
            "use_case_axes": ["for school"],
            "audience_axes": ["kids"],
            "attribute_axes": ["small", "sections"],
        }
    )

    payload = build_category_profile_draft(evidence).profile_payload
    related_subjects = {item["subject"] for item in payload["subject"]["related_but_different"]}
    skipped_axes = {
        item["axis"]
        for item in payload["generated_by"]["builder_diagnostics"]["related_product_type_axes"]["skipped"]
    }

    assert {"kids", "small", "school", "sections"}.isdisjoint(related_subjects)
    assert {"kids", "small", "school", "sections"} <= skipped_axes
    assert {"container", "kit", "case"} <= related_subjects


def test_cooccurring_modifier_axes_are_skipped_from_related_subjects() -> None:
    evidence = _evidence(
        category_id=99006,
        product_type_axes=["base", "basebox", "compact", "bundle", "side case"],
    )
    evidence["query_candidates"] = [
        {"normalized_query": "basebox compact", "display_query": "", "frequency_total": "80"},
        {"normalized_query": "basebox bundle", "display_query": "", "frequency_total": "70"},
        {"normalized_query": "side case", "display_query": "", "frequency_total": "30"},
    ]
    evidence["query_token_counts"] = {
        "base": 1000,
        "basebox": 100,
        "compact": 80,
        "bundle": 70,
        "side": 30,
        "case": 30,
    }

    payload = build_category_profile_draft(evidence).profile_payload
    related_subjects = {item["subject"] for item in payload["subject"]["related_but_different"]}
    skipped = {
        item["axis"]: item
        for item in payload["generated_by"]["builder_diagnostics"]["related_product_type_axes"]["skipped"]
    }

    assert "compact" not in related_subjects
    assert "bundle" not in related_subjects
    assert "side case" in related_subjects
    assert skipped["compact"]["reason"] == "cooccurring_modifier_without_standalone_product_evidence"
    assert skipped["bundle"]["reason"] == "cooccurring_modifier_without_standalone_product_evidence"
    assert skipped["compact"]["evidence"]["standalone_phrase_count"] == 0
    assert skipped["compact"]["evidence"]["cooccurs_with_primary_count"] == 1


def test_standalone_competing_product_type_can_become_related_subject() -> None:
    evidence = _evidence(category_id=99007, product_type_axes=["base", "basebox", "side case"])
    evidence["query_candidates"] = [
        {"normalized_query": "basebox compact", "display_query": "", "frequency_total": "80"},
        {"normalized_query": "side case", "display_query": "", "frequency_total": "30"},
    ]
    evidence["query_token_counts"] = {"base": 1000, "basebox": 100, "side": 30, "case": 30}

    payload = build_category_profile_draft(evidence).profile_payload
    related_subjects = {item["subject"] for item in payload["subject"]["related_but_different"]}
    conflict_product_types = {
        rule["when_query_has"]["product_type"]
        for rule in payload["hard_conflicts"]
        if "product_type" in rule["when_query_has"]
    }

    assert "side case" in related_subjects
    assert "side case" in conflict_product_types


def test_noisy_axis_filter_is_category_id_agnostic() -> None:
    first = _evidence(category_id=99004, product_type_axes=["meal", "mealbox", "kids", "case"])
    second = _evidence(category_id=99005, product_type_axes=["meal", "mealbox", "kids", "case"])
    for evidence in (first, second):
        evidence["query_token_counts"] = {"meal": 1000, "mealbox": 80, "kids": 70, "case": 20}
        evidence["axes"]["axes_payload"].update({"audience_axes": ["kids"]})

    first_payload = build_category_profile_draft(first).profile_payload
    second_payload = build_category_profile_draft(second).profile_payload

    assert first_payload["subject"] == second_payload["subject"]
    assert "kids" not in {item["subject"] for item in first_payload["subject"]["related_but_different"]}
