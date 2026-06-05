from __future__ import annotations

import copy
from pathlib import Path

from app.services.seo.category_profile import CategoryProfile
from app.services.seo.category_profile_derive_builder import build_category_profile_draft
from app.services.seo.category_profile_guard_builder import GUARD_BUILDER_METHOD, enrich_profile_guards
from app.services.seo.category_profile_validator import validate_category_profile_payload
from app.services.seo.global_vocabulary import load_global_vocabulary


def _evidence(
    *,
    category_id: int = 75010,
    weak_axes: bool = False,
    characteristic_axes: list[dict[str, object]] | None = None,
    excluded_axes: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    axes_payload: dict[str, object] = {
        "product_type_axes": ["carrier", "case", "sleeve"],
        "constraint_axes": ["travel mode"],
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
    if characteristic_axes is not None:
        axes_payload["sku_characteristic_axes"] = characteristic_axes
    if excluded_axes is not None:
        axes_payload["query_exclusion_axes"] = excluded_axes

    return {
        "project_id": 1,
        "category_id": category_id,
        "evidence_hash": f"sha256:guards-synthetic-{category_id}",
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
            "axes_payload": axes_payload,
        },
        "diagnostics": {"status": "ready"},
    }


def test_guard_builder_materializes_explicit_query_and_sku_guards() -> None:
    evidence = _evidence(
        characteristic_axes=[
            {
                "name_contains": "capacity",
                "target": {"type": "numeric", "field": "quantity", "parser": "int_first"},
            }
        ],
        excluded_axes=[
            {
                "when_contains": "without pattern",
                "exclude": {"field": "design", "value": "print"},
            }
        ],
    )
    draft = build_category_profile_draft(evidence).profile_payload
    diagnostics = draft["generated_by"]["guard_builder_diagnostics"]

    assert {
        "when_contains": "carrier bag",
        "set_product_type": "carrier",
        "unless_set": True,
    } in draft["query_guards"]["product_type_detection"]
    assert {"when_contains": "travel mode", "atom": {"type": "use_case", "field": "use_case", "value": "travel_mode"}} in draft[
        "query_guards"
    ]["required_atoms"]
    assert draft["query_guards"]["excluded_atoms"] == [
        {"when_contains": "without pattern", "exclude": {"field": "design", "value": "print"}}
    ]
    assert draft["sku_guards"]["functional_token_mappings"] == [
        {"when_contains": "travel mode", "target": {"type": "use_case", "field": "use_case", "value": "travel_mode"}}
    ]
    assert draft["sku_guards"]["characteristic_mappings"] == [
        {"name_contains": "capacity", "target": {"type": "numeric", "field": "quantity", "parser": "int_first"}}
    ]
    assert diagnostics["builder_method"] == GUARD_BUILDER_METHOD
    assert diagnostics["query_guard_counts"]["required_atoms"] == 1
    assert diagnostics["sku_guard_counts"]["functional_token_mappings"] == 1


def test_guard_builder_is_deterministic_for_identical_input() -> None:
    evidence = _evidence()

    first = build_category_profile_draft(copy.deepcopy(evidence))
    second = build_category_profile_draft(copy.deepcopy(evidence))

    assert first.profile_payload == second.profile_payload
    assert first.profile_payload["generated_by"]["guard_builder_diagnostics"] == second.profile_payload["generated_by"][
        "guard_builder_diagnostics"
    ]


def test_weak_axes_are_skipped_not_materialized_as_hard_guards() -> None:
    draft = build_category_profile_draft(_evidence(weak_axes=True)).profile_payload
    diagnostics = draft["generated_by"]["guard_builder_diagnostics"]

    assert draft["query_guards"]["excluded_atoms"] == []
    assert "negative_constraint_axes" in diagnostics["excluded_atoms"]["skipped_weak_axis_groups"]
    assert "attribute_axes" in diagnostics["excluded_atoms"]["skipped_weak_axis_groups"]
    assert diagnostics["excluded_atoms"]["materialized"] == []


def test_unknown_guard_target_fields_are_rejected_by_builder() -> None:
    draft = build_category_profile_draft(
        _evidence(
            characteristic_axes=[
                {
                    "name_contains": "unsupported slot",
                    "target": {"type": "attribute", "field": "unknown_slot"},
                }
            ],
            excluded_axes=[
                {
                    "when_contains": "without unsupported",
                    "exclude": {"field": "unknown_slot", "value": "x"},
                }
            ],
        )
    ).profile_payload
    diagnostics = draft["generated_by"]["guard_builder_diagnostics"]

    assert draft["sku_guards"]["characteristic_mappings"] == []
    assert draft["query_guards"]["excluded_atoms"] == []
    assert diagnostics["characteristic_mappings"]["skipped"] == [
        {"source": "sku_characteristic_axes", "name_contains": "unsupported slot", "reason": "unknown_target_field"}
    ]
    assert diagnostics["excluded_atoms"]["skipped"] == [
        {"source": "query_exclusion_axes", "when_contains": "without unsupported", "reason": "unknown_target_field"}
    ]


def test_empty_sku_characteristics_still_produce_valid_profile() -> None:
    draft = build_category_profile_draft(_evidence()).profile_payload

    assert draft["sku_guards"]["characteristic_mappings"] == []
    assert draft["sku_guards"]["functional_token_mappings"]
    assert validate_category_profile_payload(draft, vocabulary=load_global_vocabulary()).status == "passed"


def test_guard_output_is_step2_step3_and_runtime_profile_compatible() -> None:
    draft = build_category_profile_draft(_evidence(category_id=75011)).profile_payload

    runtime_profile = CategoryProfile.from_payload(
        profile_id=0,
        project_id=1,
        category_id=75011,
        version="draft",
        payload=draft,
    )
    self_check = validate_category_profile_payload(draft, vocabulary=load_global_vocabulary())

    assert runtime_profile.query_guards["required_atoms"]
    assert runtime_profile.sku_guards["functional_token_mappings"]
    assert draft["generated_by"]["constraints_builder_diagnostics"]["constraint_rules_count"] == 1
    assert draft["generated_by"]["guard_builder_diagnostics"]["market_fields_used_for_build_decisions"] is False
    assert self_check.status == "passed"


def test_guard_builder_does_not_use_market_fields_in_decisions() -> None:
    low = build_category_profile_draft(_evidence(category_id=75012)).profile_payload
    high_evidence = _evidence(category_id=75012)
    high_evidence["corpus"]["economic_field_names_present"] = ["orders", "conversion", "orders_total"]
    high = build_category_profile_draft(high_evidence).profile_payload

    assert low["query_guards"] == high["query_guards"]
    assert low["sku_guards"] == high["sku_guards"]
    assert "orders" not in str(high["query_guards"]).lower()
    assert "conversion" not in str(high["sku_guards"]).lower()
    assert high["generated_by"]["guard_builder_diagnostics"]["market_fields_used_for_build_decisions"] is False


def test_guard_builder_is_generic_and_contains_no_category_branches() -> None:
    source = Path("src/app/services/seo/category_profile_guard_builder.py").read_text(encoding="utf-8")

    for forbidden in ("термокруж", "круж", "рюкзак", "сумка", "тарел", "пивн", "кофемаш", "812", "2841"):
        assert forbidden not in source
    assert GUARD_BUILDER_METHOD in source


def test_guard_builder_is_pure_and_does_not_change_runtime_or_persistence_files() -> None:
    source = Path("src/app/services/seo/category_profile_guard_builder.py").read_text(encoding="utf-8")

    for forbidden in ("Session", "SeoCategoryProfile", "load_active_profile", "activate", "commit", "flush"):
        assert forbidden not in source
    assert enrich_profile_guards
