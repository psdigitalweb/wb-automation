"""Pure helpers for interpreting category-profile runtime rules."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Mapping

from app.services.seo.category_profile import ProductTypeAliasRule, ScoringProfile, SubjectProfile

if TYPE_CHECKING:
    from app.services.seo.category_profile import CategoryProfile


_WORD_RE = re.compile(r"[0-9a-zA-Zа-яА-ЯёЁ]+", re.IGNORECASE)


def normalize_text(value: object) -> str:
    return str(value or "").lower().replace("ё", "е")


def token_set(value: object) -> frozenset[str]:
    return frozenset(token.lower().replace("ё", "е") for token in _WORD_RE.findall(str(value or "")))


@dataclass(frozen=True)
class RuleFeatures:
    product_type: str = ""
    constraints: frozenset[str] = field(default_factory=frozenset)
    tokens: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_values(
        cls,
        *,
        product_type: str = "",
        constraints: frozenset[str] | set[str] | tuple[str, ...] | list[str] = (),
        tokens: frozenset[str] | set[str] | tuple[str, ...] | list[str] = (),
    ) -> "RuleFeatures":
        return cls(
            product_type=normalize_text(product_type),
            constraints=frozenset(normalize_text(item) for item in constraints),
            tokens=frozenset(normalize_text(item) for item in tokens),
        )


def predicate_matches(predicate: Mapping[str, object], features: RuleFeatures) -> bool:
    """Evaluate one hard-conflict predicate against normalized rule features."""

    for key, value in predicate.items():
        normalized_value = normalize_text(value)
        if key == "constraint":
            if normalized_value not in features.constraints:
                return False
            continue
        if key == "constraint_prefix":
            if not any(item.startswith(normalized_value) for item in features.constraints):
                return False
            continue
        if key == "product_type":
            if normalize_text(features.product_type) != normalized_value:
                return False
            continue
        if key == "product_type_contains":
            if normalized_value not in normalize_text(features.product_type):
                return False
            continue
        if key == "token_prefix":
            if not any(token.startswith(normalized_value) for token in features.tokens):
                return False
            continue
        return False
    return True


def get_bucket_cutoff(scoring: ScoringProfile, bucket: str) -> float:
    """Return one bucket cutoff from the scoring section."""

    return float(scoring.bucket_cutoffs[str(bucket)])


def product_type_alias_matches(text: object, rule: ProductTypeAliasRule) -> bool:
    """Check whether text matches a product-type alias by any configured prefix."""

    tokens = token_set(text)
    return any(token.startswith(prefix) for token in tokens for prefix in rule.match_any_prefix)


def matches_primary_subject_text(text: object, subject: SubjectProfile) -> bool:
    """Check whether text looks like the profile's primary subject, not a related one."""

    tokens = token_set(text)
    if any(token.startswith(prefix) for token in tokens for prefix in subject.detection_hints.negative_token_prefixes):
        return False
    if any(token.startswith(prefix) for token in tokens for prefix in subject.detection_hints.token_prefixes):
        return True
    normalized = normalize_text(text)
    return any(alias in normalized for alias in subject.primary_aliases)


def product_type_compatibility_reason(
    query_type: object,
    sku_type: object,
    *,
    profile: "CategoryProfile",
) -> str | None:
    """Explain product-type compatibility using the active CategoryProfile.

    This treats the profile primary subject and its aliases as one equivalence
    group while preserving true conflicts with related or unrelated product
    types.
    """

    query_norm = normalize_text(query_type)
    sku_norm = normalize_text(sku_type)
    if not query_norm:
        return "product_type compatible: query has no product type requirement"
    if query_norm == sku_norm:
        return f"product_type matched: {query_norm}"

    if _is_primary_subject_product_type(query_norm, profile) and _is_primary_subject_product_type(sku_norm, profile):
        return f"product_type compatible via category profile alias: {query_norm}"

    query_rule = profile.product_type_aliases.get(query_norm)
    if query_rule is not None and product_type_alias_matches(sku_norm, query_rule):
        return f"product_type compatible: {query_norm}"

    return None


def _is_primary_subject_product_type(value: str, profile: "CategoryProfile") -> bool:
    normalized = normalize_text(value)
    if not normalized:
        return False

    subject = profile.subject
    primary_values = {
        normalize_text(subject.primary),
        *(normalize_text(alias) for alias in subject.primary_aliases),
    }
    if normalized in primary_values:
        return True

    primary_rule = profile.product_type_aliases.get(subject.primary)
    if primary_rule is not None and product_type_alias_matches(normalized, primary_rule):
        return True

    return matches_primary_subject_text(normalized, subject)
