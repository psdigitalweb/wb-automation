from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.seo.category_profile import CategoryProfile
from app.services.seo.query_meaning_matcher import matcher


TEMPLATE_PATH = Path("config/seo/category_profiles/templates/812_skeleton_v1.json")
ACTIVE_MATCHER_PATH = Path("src/app/services/seo/query_meaning_matcher/matcher.py")
LEGACY_MATCHER_PATH = Path("src/app/services/seo/query_meaning_matcher/_legacy/matcher.py")
BASELINE_DIR = Path("tests/seo/phase0/baselines/812_pre_phase0")


def _profile() -> CategoryProfile:
    payload = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    return CategoryProfile.from_payload(
        profile_id=1,
        project_id=1,
        category_id=812,
        version="v1.812.test",
        payload=payload,
    )


def _features(
    *,
    product_type: str = "",
    constraints: set[str] | None = None,
    tokens: set[str] | None = None,
    canonical_text: str = "",
) -> matcher._FeatureSet:
    return matcher._FeatureSet(
        product_type=product_type,
        tokens=tokens or set(),
        use_case_terms=set(),
        attribute_terms=set(),
        expressive_terms=set(),
        audience_terms=set(),
        occasion_terms=set(),
        negative_terms=set(),
        negative_audience_terms=set(),
        constraints=constraints or set(),
        materials=set(),
        canonical_text=canonical_text,
    )


def _query_row(text: str, *, constraints: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        canonical_text=text,
        meaning_payload={
            "functional": {},
            "expressive": {},
            "audience": [],
            "occasion": [],
            "constraints": constraints or [],
        },
        constraints=constraints or [],
    )


def test_product_type_score_uses_profile_aliases_and_scoring_weights() -> None:
    profile = _profile()
    sku = _features(
        canonical_text="товар: кружка\nатрибуты: керамика",
        tokens={"кружка", "керамика"},
    )
    query = _features(product_type="кружка", canonical_text="кружка капибара", tokens={"кружка", "капибара"})

    score, reasons = matcher._product_type_score(sku, query, profile=profile)

    assert score == pytest.approx(profile.product_type_aliases["кружка"].score_bonus or 0.0)
    assert any("product_type compatible" in reason for reason in reasons)


def test_hard_conflicts_are_read_from_profile_rules() -> None:
    profile = _profile()
    sku = _features(product_type="кружка", canonical_text="товар: кружка", tokens={"кружка"})
    query = _features(
        product_type="термокружка",
        canonical_text="термокружка с трубочкой",
        constraints={"thermal"},
        tokens={"термокружка", "трубочкой"},
    )

    conflicts = matcher._hard_conflicts(sku, query, profile=profile)

    assert any("requires thermal" in conflict for conflict in conflicts)
    assert any("product_type conflict" in conflict for conflict in conflicts)


def test_constraint_derivation_comes_from_profile_constraints() -> None:
    profile = _profile()

    query_features = matcher._query_features(_query_row("пивная кружка"), profile=profile)
    sku_features = matcher._sku_features(
        {
            "functional": {
                "product_type": "термокружка",
                "attributes": ["термокружка дорожная"],
                "use_cases": ["для кофе"],
            }
        },
        profile=profile,
    )

    assert "beer_use_case" in query_features.constraints
    assert "thermal" in sku_features.constraints


def test_related_but_different_logic_uses_812_profile_subject_rules() -> None:
    profile = _profile()

    primary = matcher._query_features(_query_row("кружка капибара"), profile=profile)
    related = matcher._query_features(_query_row("термокружка с трубочкой"), profile=profile)

    assert primary.product_type == "кружка"
    assert related.product_type == "термокружка"


def test_active_matcher_has_no_category_literals_and_legacy_keeps_isolated_path() -> None:
    active_source = ACTIVE_MATCHER_PATH.read_text(encoding="utf-8")
    legacy_source = LEGACY_MATCHER_PATH.read_text(encoding="utf-8")

    for literal in ("термокруж", "круж", "пивн", "кофемаш", "рюкзак", "сумка", "в машину"):
        assert literal not in active_source, f"{literal!r} leaked into active matcher.py"

    assert "термокруж" in legacy_source


def test_matcher_v2_baseline_comparison_is_deferred_until_profile_reaches_v2_stages() -> None:
    artifacts = sorted(BASELINE_DIR.glob("matcher_v2_sku_*.json"))
    assert artifacts, "Step 1 matcher_v2 baseline artifacts are missing"

    payload = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert payload["metrics"]["category_profile_active"] is False
    assert str(payload["matcher_version"]).startswith("meaning_aware_matcher_v1_atoms_gate+v2_candidate")

    pytest.skip(
        "Full matcher_v2 drift comparison is deferred until Step 9/10 because matcher_v2 stages "
        "still consume legacy matcher helpers and do not execute the profile-driven path directly."
    )
