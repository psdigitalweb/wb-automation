from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.seo.atoms.v1.schemas import SkuAtoms
from app.services.seo.category_profile import CategoryProfile
from app.services.seo.category_profile_rules import product_type_compatibility_reason
from app.services.seo.query_meaning_matcher.profile_matcher import _FeatureSet, _product_type_score
from app.services.seo.query_meaning_matcher.runtime_helpers import _apply_atoms_gate


REPO_ROOT = Path(__file__).resolve().parents[3]


def _payload(*, primary: str = "alpha-kit", aliases: list[str] | None = None) -> dict[str, Any]:
    primary_aliases = aliases or [primary, "alpha"]
    return {
        "schema_version": "category_profile_v1",
        "subject": {
            "primary": primary,
            "primary_aliases": primary_aliases,
            "related_but_different": [
                {"subject": "omega-kit", "aliases": ["omega"]},
            ],
            "detection_hints": {
                "token_prefixes": ["alpha"],
                "negative_token_prefixes": ["omega"],
            },
        },
        "product_type_aliases": {
            primary: {"match_any_prefix": ["alpha"], "score_bonus": 0.17},
            "omega-kit": {"match_any_prefix": ["omega"], "score_bonus": 0.17},
        },
        "constraints": {},
        "hard_conflicts": [],
        "scoring": {
            "weights": {
                "product_type_match": 0.22,
                "product_type_compat": 0.16,
                "product_type_weak": -0.18,
            },
            "bucket_cutoffs": {"primary": 0.60, "secondary": 0.35, "broad": 0.15},
            "bucket_caps": {"primary": 100, "secondary": 300, "broad": 500},
        },
        "user_bucket_labels": {},
        "sku_guards": {},
        "query_guards": {},
        "generated_by": {"method": "test"},
        "self_check": {"status": "passed", "checks": []},
    }


def _profile(*, category_id: int = 1001, primary: str = "alpha-kit") -> CategoryProfile:
    return CategoryProfile.from_payload(
        profile_id=category_id,
        project_id=1,
        category_id=category_id,
        version=f"v1.{category_id}.test",
        payload=_payload(primary=primary),
    )


def _features(product_type: str) -> _FeatureSet:
    return _FeatureSet(
        product_type=product_type,
        tokens=set(),
        use_case_terms=set(),
        attribute_terms=set(),
        expressive_terms=set(),
        audience_terms=set(),
        occasion_terms=set(),
        negative_terms=set(),
        negative_audience_terms=set(),
        constraints=set(),
        materials=set(),
        canonical_text=product_type,
    )


def _atoms_decision(*, profile: CategoryProfile, query_type: str, sku_type: str) -> tuple[str, list[str], list[str]]:
    bucket, _score, _matched, _missing, conflicts, reasons = _apply_atoms_gate(
        bucket="primary",
        score=0.8,
        row=SimpleNamespace(cluster_key="cluster-1"),
        query_display=f"{query_type} sample",
        ranking_value=None,
        sku_atoms=SkuAtoms(product_type=sku_type),
        query_atoms_payload={
            "product_type": query_type,
            "required_atoms": [],
            "preferred_atoms": [],
            "excluded_atoms": [],
            "negative_fit_atoms": [],
            "genericness": "specific",
        },
        category_profile=profile,
    )
    return bucket, conflicts, reasons


def test_query_product_type_alias_and_sku_primary_are_compatible() -> None:
    profile = _profile()

    score, reasons = _product_type_score(
        _features("alpha-kit"),
        _features("alpha"),
        profile=profile,
    )
    bucket, conflicts, atom_reasons = _atoms_decision(profile=profile, query_type="alpha", sku_type="alpha-kit")

    assert score == pytest.approx(0.16)
    assert conflicts == []
    assert bucket != "rejected"
    assert any("category profile alias" in reason for reason in reasons + atom_reasons)


def test_sku_product_type_alias_and_query_primary_are_compatible() -> None:
    profile = _profile()

    score, reasons = _product_type_score(
        _features("alpha"),
        _features("alpha-kit"),
        profile=profile,
    )
    bucket, conflicts, atom_reasons = _atoms_decision(profile=profile, query_type="alpha-kit", sku_type="alpha")

    assert score == pytest.approx(0.16)
    assert conflicts == []
    assert bucket != "rejected"
    assert any("category profile alias" in reason for reason in reasons + atom_reasons)


def test_unrelated_product_type_still_conflicts() -> None:
    profile = _profile()

    assert product_type_compatibility_reason("omega-kit", "alpha-kit", profile=profile) is None
    bucket, conflicts, reasons = _atoms_decision(profile=profile, query_type="omega-kit", sku_type="alpha-kit")

    assert bucket == "rejected"
    assert conflicts == ["product_type conflict: query requires omega-kit, SKU is alpha-kit"]
    assert "bucket capped: hard conflict" in reasons


def test_alias_compatibility_is_category_id_agnostic() -> None:
    first = _profile(category_id=1001, primary="alpha-kit")
    second = _profile(category_id=2002, primary="alpha-kit")

    assert product_type_compatibility_reason("alpha", "alpha-kit", profile=first)
    assert product_type_compatibility_reason("alpha", "alpha-kit", profile=second)


def test_alias_compatibility_does_not_add_category_literals_to_runtime_code() -> None:
    profile = _profile()
    runtime_paths = [
        REPO_ROOT / "src/app/services/seo/category_profile_rules.py",
        REPO_ROOT / "src/app/services/seo/query_meaning_matcher/profile_matcher.py",
        REPO_ROOT / "src/app/services/seo/query_meaning_matcher/runtime_helpers.py",
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in runtime_paths)

    forbidden = {profile.subject.primary, *profile.subject.primary_aliases, "omega-kit", "omega"}
    assert [literal for literal in forbidden if literal in source] == []
