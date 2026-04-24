from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.services.seo.category_profile import CategoryProfile, CategoryProfileError
from app.services.seo.category_profile_rules import (
    RuleFeatures,
    get_bucket_cutoff,
    matches_primary_subject_text,
    predicate_matches,
    product_type_alias_matches,
    token_set,
)


TEMPLATE_PATH = Path("config/seo/category_profiles/templates/812_skeleton_v1.json")


def _template_payload() -> dict[str, object]:
    return json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))


def _profile() -> CategoryProfile:
    return CategoryProfile.from_payload(
        profile_id=1,
        project_id=1,
        category_id=812,
        version="v1.812.test",
        payload=_template_payload(),
    )


def test_wrapper_accepts_valid_v1_payload_and_exposes_subject_sections() -> None:
    profile = _profile()

    assert profile.schema_version == "category_profile_v1"
    assert profile.subject_primary == "кружка"
    assert "кружка" in profile.subject_primary_aliases
    assert len(profile.subject_related) >= 2
    assert profile.subject_related[0].subject == "термокружка"
    assert "кружка" in profile.product_type_aliases


def test_unknown_schema_version_is_rejected() -> None:
    payload = _template_payload()
    payload["schema_version"] = "category_profile_v999"

    with pytest.raises(CategoryProfileError):
        CategoryProfile.from_payload(
            profile_id=1,
            project_id=1,
            category_id=812,
            version="broken",
            payload=payload,
        )


def test_wrapper_does_not_mutate_source_payload() -> None:
    payload = _template_payload()
    before = copy.deepcopy(payload)

    profile = CategoryProfile.from_payload(
        profile_id=1,
        project_id=1,
        category_id=812,
        version="v1.812.test",
        payload=payload,
    )

    assert payload == before
    assert profile.payload["subject"]["primary"] == "кружка"


def test_bucket_cutoffs_are_accessible() -> None:
    profile = _profile()

    assert profile.bucket_cutoffs_map["primary"] > profile.bucket_cutoffs_map["secondary"] > profile.bucket_cutoffs_map["broad"]
    assert get_bucket_cutoff(profile.scoring, "primary") == pytest.approx(0.60)


@pytest.mark.parametrize(
    ("predicate", "features", "expected"),
    [
        ({"constraint": "thermal"}, RuleFeatures.from_values(constraints={"thermal"}), True),
        ({"constraint_prefix": "set"}, RuleFeatures.from_values(constraints={"set_quantity:2"}), True),
        ({"product_type": "термокружка"}, RuleFeatures.from_values(product_type="термокружка"), True),
        ({"product_type_contains": "термокруж"}, RuleFeatures.from_values(product_type="дорожная термокружка"), True),
        ({"token_prefix": "пив"}, RuleFeatures.from_values(tokens=token_set("для пива и бара")), True),
        ({"constraint": "thermal"}, RuleFeatures.from_values(constraints={"set"}), False),
    ],
)
def test_predicate_helper_matches_supported_syntax(
    predicate: dict[str, object],
    features: RuleFeatures,
    expected: bool,
) -> None:
    assert predicate_matches(predicate, features) is expected


def test_product_type_alias_helper_matches_prefixes() -> None:
    profile = _profile()

    assert product_type_alias_matches("кружка капибара", profile.product_type_aliases["кружка"]) is True
    assert product_type_alias_matches("термокружка с трубочкой", profile.product_type_aliases["термокружка"]) is True


def test_detection_hints_distinguish_primary_from_negative_prefix() -> None:
    subject = _profile().subject

    assert matches_primary_subject_text("кружка капибара", subject) is True
    assert matches_primary_subject_text("термокружка с трубочкой", subject) is False
