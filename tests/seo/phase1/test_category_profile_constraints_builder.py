from __future__ import annotations

import copy
from pathlib import Path

from app.services.seo.category_profile import CategoryProfile
from app.services.seo.category_profile_constraints_builder import (
    CONSTRAINTS_BUILDER_METHOD,
    enrich_profile_constraints,
)
from app.services.seo.category_profile_derive_builder import build_category_profile_draft
from app.services.seo.category_profile_validator import validate_category_profile_payload
from app.services.seo.global_vocabulary import load_global_vocabulary


def _evidence(*, constraint_axes: list[str] | None = None, weak_axes: bool = False) -> dict[str, object]:
    axes_payload: dict[str, object] = {
        "product_type_axes": ["carrier", "case", "sleeve"],
        "constraint_axes": ["travel mode"] if constraint_axes is None else constraint_axes,
        "synonym_groups": [
            {"label": "carrier", "variants": ["carrier bag"]},
            {"label": "case", "variants": ["protective case"]},
        ],
    }
    if weak_axes:
        axes_payload.update(
            {
                "use_case_axes": ["daily commute"],
                "attribute_axes": ["compact"],
                "negative_constraint_axes": ["bad fit"],
            }
        )
    return {
        "project_id": 1,
        "category_id": 74010,
        "evidence_hash": "sha256:constraints-synthetic",
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
            "axes_id": 10,
            "schema_version": "category_meaning_axes_v0",
            "source": "deterministic",
            "evidence_hash": "axes-hash",
            "input_hash": "axes-input",
            "axes_payload": axes_payload,
        },
        "diagnostics": {"status": "ready"},
    }


def test_constraints_builder_adds_schema_valid_constraints_and_hard_conflicts() -> None:
    draft = build_category_profile_draft(_evidence()).profile_payload

    constraints = draft["constraints"]
    hard_conflicts = draft["hard_conflicts"]

    assert constraints["derive_from_query_tokens"] == [
        {"constraint": "travel_mode", "when_query_contains_any": ["travel mode"]}
    ]
    assert constraints["derive_from_sku_meaning"] == [
        {"constraint": "travel_mode", "when_functional_attribute_contains": ["travel mode"]}
    ]
    assert {"constraint": "travel_mode"} in [rule["when_query_has"] for rule in hard_conflicts]
    related_subjects = {item["subject"] for item in draft["subject"]["related_but_different"]}
    covered_product_types = {
        rule["when_query_has"]["product_type"]
        for rule in hard_conflicts
        if "product_type" in rule["when_query_has"]
    }
    assert related_subjects <= covered_product_types

    runtime_profile = CategoryProfile.from_payload(
        profile_id=0,
        project_id=1,
        category_id=74010,
        version="draft",
        payload=draft,
    )
    assert len(runtime_profile.hard_conflicts) == len(hard_conflicts)
    self_check = validate_category_profile_payload(draft, vocabulary=load_global_vocabulary())
    assert self_check.status == "passed"


def test_constraints_builder_is_deterministic_for_identical_input() -> None:
    draft = build_category_profile_draft(_evidence()).profile_payload

    first = enrich_profile_constraints(copy.deepcopy(draft), copy.deepcopy(_evidence()))
    second = enrich_profile_constraints(copy.deepcopy(draft), copy.deepcopy(_evidence()))

    assert first.profile_payload == second.profile_payload
    assert first.diagnostics == second.diagnostics


def test_constraints_builder_is_generic_and_contains_no_category_literals() -> None:
    source = Path("src/app/services/seo/category_profile_constraints_builder.py").read_text(encoding="utf-8")

    for forbidden in ("термокруж", "круж", "рюкзак", "сумка", "тарел", "пивн", "кофемаш", "812", "2841"):
        assert forbidden not in source
    assert CONSTRAINTS_BUILDER_METHOD in source


def test_economic_fields_do_not_enter_constraints_scoring_labels_or_decisions() -> None:
    draft = build_category_profile_draft(_evidence()).profile_payload
    diagnostics = draft["generated_by"]["constraints_builder_diagnostics"]

    assert "orders" not in str(draft["constraints"]).lower()
    assert "conversion" not in str(draft["constraints"]).lower()
    assert "orders" not in str(draft["hard_conflicts"]).lower()
    assert "conversion" not in str(draft["hard_conflicts"]).lower()
    assert "orders" not in str(draft["scoring"]).lower()
    assert "conversion" not in str(draft["user_bucket_labels"]).lower()
    assert "orders" not in str(diagnostics).lower()
    assert "conversion" not in str(diagnostics).lower()
    assert diagnostics["economic_fields_used_for_build_decisions"] is False


def test_weak_evidence_does_not_invent_constraint_conflicts() -> None:
    draft = build_category_profile_draft(
        _evidence(constraint_axes=["unseen special mode"], weak_axes=True)
    ).profile_payload
    diagnostics = draft["generated_by"]["constraints_builder_diagnostics"]

    assert draft["constraints"]["derive_from_query_tokens"] == []
    assert draft["constraints"]["derive_from_sku_meaning"] == []
    assert all("constraint" not in rule["when_query_has"] for rule in draft["hard_conflicts"])
    assert diagnostics["constraint_axes"]["skipped_constraint_axes"] == [
        {"axis": "unseen special mode", "reason": "no_query_token_or_phrase_evidence"}
    ]
    assert "negative_constraint_axes" in diagnostics["constraint_axes"]["skipped_weak_axis_groups"]


def test_noisy_related_candidates_do_not_become_product_type_conflicts() -> None:
    evidence = _evidence()
    evidence["axes"]["axes_payload"].update(
        {
            "product_type_axes": ["carrier", "audience token", "attribute token", "case"],
            "audience_axes": ["audience token"],
            "attribute_axes": ["attribute token"],
        }
    )
    evidence["query_candidates"] = [
        {"normalized_query": "carrier audience token", "display_query": "", "frequency_total": "80"},
        {"normalized_query": "carrier attribute token", "display_query": "", "frequency_total": "80"},
        {"normalized_query": "case", "display_query": "", "frequency_total": "30"},
    ]
    evidence["query_token_counts"] = {
        "carrier": 400,
        "audience": 80,
        "token": 160,
        "attribute": 80,
        "case": 30,
    }

    draft = build_category_profile_draft(evidence).profile_payload
    conflict_product_types = {
        rule["when_query_has"]["product_type"]
        for rule in draft["hard_conflicts"]
        if "product_type" in rule["when_query_has"]
    }
    skipped_axes = {
        item["axis"]
        for item in draft["generated_by"]["builder_diagnostics"]["related_product_type_axes"]["skipped"]
    }

    assert "audience token" not in conflict_product_types
    assert "attribute token" not in conflict_product_types
    assert {"audience token", "attribute token"} <= skipped_axes
    assert "case" in conflict_product_types


def test_cooccurring_modifier_axes_do_not_become_hard_conflicts() -> None:
    evidence = _evidence()
    evidence["axes"]["axes_payload"].update(
        {"product_type_axes": ["carrier", "compact", "bundle", "side case"]}
    )
    evidence["query_candidates"] = [
        {"normalized_query": "carrier compact", "display_query": "", "frequency_total": "80"},
        {"normalized_query": "carrier bundle", "display_query": "", "frequency_total": "70"},
        {"normalized_query": "side case", "display_query": "", "frequency_total": "30"},
    ]
    evidence["query_token_counts"] = {
        "carrier": 400,
        "compact": 80,
        "bundle": 70,
        "side": 30,
        "case": 30,
    }

    draft = build_category_profile_draft(evidence).profile_payload
    conflict_product_types = {
        rule["when_query_has"]["product_type"]
        for rule in draft["hard_conflicts"]
        if "product_type" in rule["when_query_has"]
    }
    skipped = {
        item["axis"]: item["reason"]
        for item in draft["generated_by"]["builder_diagnostics"]["related_product_type_axes"]["skipped"]
    }

    assert "compact" not in conflict_product_types
    assert "bundle" not in conflict_product_types
    assert "side case" in conflict_product_types
    assert skipped["compact"] == "cooccurring_modifier_without_standalone_product_evidence"
    assert skipped["bundle"] == "cooccurring_modifier_without_standalone_product_evidence"


def test_constraints_builder_output_is_compatible_with_step2_builder() -> None:
    draft = build_category_profile_draft(_evidence()).profile_payload

    assert draft["schema_version"] == "category_profile_v1"
    assert draft["generated_by"]["builder_diagnostics"]["economic_fields_used_for_build_decisions"] is False
    assert draft["generated_by"]["constraints_builder_diagnostics"]["builder_method"] == CONSTRAINTS_BUILDER_METHOD
    assert validate_category_profile_payload(draft, vocabulary=load_global_vocabulary()).status == "passed"
