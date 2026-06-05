"""Profile-driven helpers for the meaning-aware query matcher."""

from __future__ import annotations

from typing import Any, Mapping

from app.models import SeoQueryMeaning
from app.services.seo.category_profile import CategoryProfile
from app.services.seo.category_profile_rules import (
    RuleFeatures,
    matches_primary_subject_text,
    predicate_matches,
    product_type_compatibility_reason,
    product_type_alias_matches,
)
from app.services.seo.query_meaning_matcher._legacy.matcher import (
    _FeatureSet,
    _expand_audience,
    _expand_expressive,
    _expand_visual_terms,
    _first_text,
    _material_set,
)
from app.services.seo.query_meaning_matcher.canonical import (
    build_sku_canonical_text,
    listify,
    normalize_query_meaning_payload,
    normalized_tokens,
)


def _normalize_text(value: Any) -> str:
    return str(value or "").lower().replace("ё", "е")


def _normalize_markers(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_normalize_text(item) for item in values if _normalize_text(item))


def _matches_text_marker(text: str, marker: str) -> bool:
    marker_text = _normalize_text(marker)
    return bool(marker_text and marker_text in text)


def _resolve_subject_product_type(text: str, profile: CategoryProfile) -> str:
    normalized = _normalize_text(text)
    if not normalized:
        return ""

    for canonical, rule in profile.product_type_aliases.items():
        if product_type_alias_matches(normalized, rule):
            return canonical

    primary_markers = _normalize_markers((profile.subject.primary, *profile.subject.primary_aliases))
    if any(_matches_text_marker(normalized, marker) for marker in primary_markers):
        return profile.subject.primary

    for related in profile.subject.related_but_different:
        related_markers = _normalize_markers((related.subject, *related.aliases))
        if any(_matches_text_marker(normalized, marker) for marker in related_markers):
            return related.subject

    if matches_primary_subject_text(normalized, profile.subject):
        return profile.subject.primary
    return ""


def _derive_query_constraints(
    profile: CategoryProfile,
    *,
    canonical_text: str,
    seed_constraints: set[str],
) -> set[str]:
    constraints = set(seed_constraints)
    normalized = _normalize_text(canonical_text)
    for rule in profile.constraints.get("derive_from_query_tokens", ()):
        constraint = str(rule.get("constraint") or "").strip()
        markers = tuple(str(item) for item in listify(rule.get("when_query_contains_any")) if str(item).strip())
        if constraint and any(_matches_text_marker(normalized, marker) for marker in markers):
            constraints.add(constraint)
    return constraints


def _derive_sku_constraints(
    profile: CategoryProfile,
    *,
    functional: Mapping[str, Any],
    canonical_text: str,
    seed_constraints: set[str],
) -> set[str]:
    constraints = set(seed_constraints)
    haystack = " ".join(
        str(item)
        for item in (
            listify(functional.get("product_type"))
            + listify(functional.get("attributes"))
            + listify(functional.get("use_cases"))
            + [canonical_text]
        )
    )
    normalized = _normalize_text(haystack)
    for rule in profile.constraints.get("derive_from_sku_meaning", ()):
        constraint = str(rule.get("constraint") or "").strip()
        markers = tuple(str(item) for item in listify(rule.get("when_functional_attribute_contains")) if str(item).strip())
        if constraint and any(_matches_text_marker(normalized, marker) for marker in markers):
            constraints.add(constraint)
    return constraints


def _sku_features(meaning: Mapping[str, Any], *, profile: CategoryProfile) -> _FeatureSet:
    functional = meaning.get("functional") if isinstance(meaning.get("functional"), dict) else {}
    expressive = meaning.get("expressive") if isinstance(meaning.get("expressive"), dict) else {}
    canonical_text = build_sku_canonical_text(meaning)
    positive_text = " ".join(listify(functional) + listify(expressive) + listify(meaning.get("audience")))
    all_tokens = normalized_tokens(functional, expressive, meaning.get("audience"))
    use_case_terms = normalized_tokens(functional.get("use_cases"))
    attribute_terms = _expand_visual_terms(normalized_tokens(functional.get("attributes")))
    expressive_terms = _expand_expressive(
        normalized_tokens(
            expressive.get("styles"),
            expressive.get("vibes"),
            expressive.get("emotions"),
            expressive.get("gift_contexts"),
        )
    )
    audience_terms = _expand_audience(normalized_tokens(meaning.get("audience"), functional.get("attributes"), functional.get("use_cases")))
    occasion_terms = normalized_tokens(expressive.get("gift_contexts"))
    negative_terms = normalized_tokens(meaning.get("negative_constraints"))
    negative_audience_terms = _expand_audience(negative_terms)
    if "подар" in positive_text.lower().replace("ё", "е"):
        occasion_terms.add("подарок")

    product_type = _normalize_text(_first_text(functional.get("product_type")))
    if not product_type:
        product_type = _resolve_subject_product_type(canonical_text, profile)
    constraints = _derive_sku_constraints(
        profile,
        functional=functional,
        canonical_text=canonical_text,
        seed_constraints=set(),
    )

    return _FeatureSet(
        product_type=product_type,
        tokens=all_tokens,
        use_case_terms=use_case_terms,
        attribute_terms=attribute_terms,
        expressive_terms=expressive_terms,
        audience_terms=audience_terms,
        occasion_terms=occasion_terms,
        negative_terms=negative_terms,
        negative_audience_terms=negative_audience_terms,
        constraints=constraints,
        materials=_material_set(all_tokens, constraints),
        canonical_text=canonical_text,
    )


def _query_features(row: SeoQueryMeaning, *, profile: CategoryProfile) -> _FeatureSet:
    payload = normalize_query_meaning_payload(row.meaning_payload or {})
    functional = payload.functional or {}
    expressive = payload.expressive or {}
    canonical_text = str(row.canonical_text or "")
    seed_constraints = {
        str(item).lower().replace("ё", "е")
        for item in listify(row.constraints or payload.constraints)
        if str(item).strip()
    }
    constraints = _derive_query_constraints(profile, canonical_text=canonical_text, seed_constraints=seed_constraints)
    all_tokens = normalized_tokens(canonical_text, functional, expressive, payload.audience, payload.occasion, constraints)
    use_case_terms = normalized_tokens(functional.get("use_cases"))
    attribute_terms = _expand_visual_terms(normalized_tokens(functional.get("attributes"), canonical_text))
    expressive_terms = _expand_expressive(
        normalized_tokens(
            expressive.get("styles"),
            expressive.get("vibes"),
            expressive.get("emotions"),
            expressive.get("gift_contexts"),
        )
    )
    product_type = _normalize_text(_first_text(functional.get("product_type")))
    if not product_type:
        product_type = _resolve_subject_product_type(canonical_text, profile)

    return _FeatureSet(
        product_type=product_type,
        tokens=all_tokens,
        use_case_terms=use_case_terms,
        attribute_terms=attribute_terms,
        expressive_terms=expressive_terms,
        audience_terms=_expand_audience(normalized_tokens(payload.audience, functional.get("use_cases"), functional.get("attributes"))),
        occasion_terms=normalized_tokens(payload.occasion, expressive.get("gift_contexts")),
        negative_terms=set(),
        negative_audience_terms=set(),
        constraints=constraints,
        materials=_material_set(all_tokens, constraints),
        canonical_text=canonical_text,
    )


def _hard_conflicts(sku: _FeatureSet, query: _FeatureSet, *, profile: CategoryProfile) -> list[str]:
    query_features = RuleFeatures.from_values(
        product_type=query.product_type,
        constraints=sorted(query.constraints),
        tokens=sorted(query.tokens),
    )
    sku_features = RuleFeatures.from_values(
        product_type=sku.product_type,
        constraints=sorted(sku.constraints),
        tokens=sorted(sku.tokens),
    )
    conflicts: list[str] = []
    for rule in profile.hard_conflicts:
        if not predicate_matches(rule.when_query_has, query_features):
            continue
        if any(predicate_matches(requirement, sku_features) for requirement in rule.requires_sku_any):
            continue
        conflicts.append(rule.message or rule.name or "profile hard conflict")

    if query.materials and sku.materials and not (query.materials & sku.materials):
        conflicts.append(f"material conflict: requires {', '.join(sorted(query.materials))}")
    negative_audience = (sku.negative_audience_terms & query.audience_terms) & {
        "женская",
        "мужская",
        "школьники",
        "подростки",
    }
    if negative_audience:
        conflicts.append(f"blocked by SKU negative constraint: {', '.join(sorted(negative_audience))}")
    return conflicts


def _product_type_score(sku: _FeatureSet, query: _FeatureSet, *, profile: CategoryProfile) -> tuple[float, list[str]]:
    if not query.product_type:
        return 0.0, []

    weights = profile.scoring.weights
    match_weight = float(weights.get("product_type_match", 0.22))
    compat_weight = float(weights.get("product_type_compat", 0.16))
    weak_weight = float(weights.get("product_type_weak", -0.18))

    compatibility_reason = product_type_compatibility_reason(
        query.product_type,
        sku.product_type,
        profile=profile,
    )
    if compatibility_reason is not None:
        score = match_weight if compatibility_reason.startswith("product_type matched") else compat_weight
        return score, [compatibility_reason]

    query_rule = profile.product_type_aliases.get(query.product_type)
    if query_rule is not None and product_type_alias_matches(sku.canonical_text or sku.product_type, query_rule):
        compat_score = float(query_rule.score_bonus) if query_rule.score_bonus is not None else compat_weight
        return compat_score, [f"product_type compatible: {query.product_type}"]

    if query.product_type == profile.subject.primary and matches_primary_subject_text(sku.canonical_text, profile.subject):
        return compat_weight, [f"product_type compatible: {query.product_type}"]

    return weak_weight, [f"product_type weak/conflicting: {query.product_type}"]


__all__ = [
    "_FeatureSet",
    "_hard_conflicts",
    "_product_type_score",
    "_query_features",
    "_sku_features",
]
