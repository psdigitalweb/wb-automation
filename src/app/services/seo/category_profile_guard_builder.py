"""Generic guard builder for category-profile drafts.

This layer enriches an in-memory ``category_profile_v1`` draft with
declarative query and SKU guards. It is intentionally conservative: only
explicit product-type aliases, constraint markers, and known target fields are
materialized. Weak axes stay in diagnostics.
"""

from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.services.seo.category_profile_derive_evidence import CategoryProfileDeriveEvidence


GUARD_BUILDER_METHOD = "generic_guard_builder_v1"
_WORD_RE = re.compile(r"[0-9a-zA-Zа-яА-ЯёЁ.]+", re.IGNORECASE)
_KNOWN_GUARD_FIELDS = {
    "volume_ml",
    "color",
    "material",
    "quantity",
    "design",
    "feature",
    "compatibility",
    "thermal",
    "transparency",
    "context",
    "use_case",
    "product_type",
}
_WEAK_AXIS_KEYS = (
    "use_case_axes",
    "attribute_axes",
    "audience_axes",
    "expressive_axes",
    "occasion_axes",
    "negative_constraint_axes",
)
_CHARACTERISTIC_AXIS_KEYS = ("sku_characteristic_axes", "characteristic_axes", "product_characteristic_axes")
_EXPLICIT_EXCLUSION_AXIS_KEYS = ("query_exclusion_axes", "excluded_atom_axes")


@dataclass(frozen=True)
class CategoryProfileGuardDraft:
    """Profile payload enriched with generic guards and diagnostics."""

    profile_payload: Mapping[str, Any]
    diagnostics: Mapping[str, Any]


def enrich_profile_guards(
    profile_payload: Mapping[str, Any],
    evidence: CategoryProfileDeriveEvidence | Mapping[str, Any],
) -> CategoryProfileGuardDraft:
    """Return a deterministic draft payload with conservative profile guards."""

    evidence_input = evidence.to_builder_input() if isinstance(evidence, CategoryProfileDeriveEvidence) else dict(evidence)
    payload = copy.deepcopy(dict(profile_payload))
    axes_payload = _mapping(_mapping(evidence_input.get("axes")).get("axes_payload"))

    product_type_rules, product_type_diagnostics = _product_type_detection_rules(payload)
    required_atoms, required_diagnostics = _required_atom_rules(payload)
    excluded_atoms, excluded_diagnostics = _excluded_atom_rules(axes_payload)
    characteristic_mappings, characteristic_diagnostics = _characteristic_mappings(axes_payload)
    functional_mappings, functional_diagnostics = _functional_token_mappings(payload)

    payload["query_guards"] = {
        "product_type_detection": product_type_rules,
        "required_atoms": required_atoms,
        "excluded_atoms": excluded_atoms,
    }
    payload["sku_guards"] = {
        "characteristic_mappings": characteristic_mappings,
        "functional_token_mappings": functional_mappings,
    }

    diagnostics = _diagnostics(
        evidence_input,
        product_type_diagnostics=product_type_diagnostics,
        required_diagnostics=required_diagnostics,
        excluded_diagnostics=excluded_diagnostics,
        characteristic_diagnostics=characteristic_diagnostics,
        functional_diagnostics=functional_diagnostics,
        product_type_rules_count=len(product_type_rules),
        required_atoms_count=len(required_atoms),
        excluded_atoms_count=len(excluded_atoms),
        characteristic_mappings_count=len(characteristic_mappings),
        functional_mappings_count=len(functional_mappings),
    )
    generated_by = payload.get("generated_by")
    if isinstance(generated_by, dict):
        generated_by["guard_builder_diagnostics"] = diagnostics

    return CategoryProfileGuardDraft(profile_payload=payload, diagnostics=diagnostics)


def _product_type_detection_rules(payload: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    primary = _normalize(_mapping(payload.get("subject")).get("primary"))
    product_aliases = _mapping(payload.get("product_type_aliases"))
    candidates: list[tuple[str, str, bool]] = []
    diagnostics: list[dict[str, Any]] = []

    for subject, raw_rule in product_aliases.items():
        subject_text = _normalize(subject)
        rule = _mapping(raw_rule)
        markers = _string_list(rule.get("match_any_prefix"))
        if not subject_text or not markers:
            diagnostics.append({"subject": subject_text, "status": "skipped", "reason": "missing_subject_or_markers"})
            continue
        for marker in markers:
            candidates.append((marker, subject_text, subject_text == primary))
        diagnostics.append(
            {
                "subject": subject_text,
                "status": "materialized",
                "source": "profile.product_type_aliases",
                "markers": list(markers),
            }
        )

    candidates.sort(key=lambda item: (item[2], -len(item[0]), item[0], item[1]))
    rules: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for marker, subject, is_primary in candidates:
        key = (marker, subject)
        if key in seen:
            continue
        seen.add(key)
        rule: dict[str, Any] = {"when_contains": marker, "set_product_type": subject}
        if is_primary:
            rule["unless_set"] = True
        rules.append(rule)
    return rules, diagnostics


def _required_atom_rules(payload: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    constraints = _mapping(payload.get("constraints"))
    accepted: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    rules: list[dict[str, Any]] = []
    for item in _mapping_items(constraints.get("derive_from_query_tokens")):
        constraint = _constraint_value(item.get("constraint"))
        markers = _string_list(item.get("when_query_contains_any"))
        if not constraint or not markers:
            skipped.append({"constraint": constraint, "reason": "missing_constraint_or_query_markers"})
            continue
        rules.append(
            {
                "when_contains": markers[0],
                "atom": {"type": "use_case", "field": "use_case", "value": constraint},
            }
        )
        accepted.append(
            {
                "constraint": constraint,
                "marker": markers[0],
                "target": {"type": "use_case", "field": "use_case"},
                "source": "profile.constraints.derive_from_query_tokens",
            }
        )
    return _dedupe_guard_rules(rules, marker_key="when_contains"), {"materialized": accepted, "skipped": skipped}


def _functional_token_mappings(payload: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    constraints = _mapping(payload.get("constraints"))
    accepted: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    rules: list[dict[str, Any]] = []
    for item in _mapping_items(constraints.get("derive_from_sku_meaning")):
        constraint = _constraint_value(item.get("constraint"))
        markers = _string_list(item.get("when_functional_attribute_contains"))
        if not constraint or not markers:
            skipped.append({"constraint": constraint, "reason": "missing_constraint_or_sku_markers"})
            continue
        target = {"type": "use_case", "field": "use_case", "value": constraint}
        if not _is_known_target(target):
            skipped.append({"constraint": constraint, "reason": "unknown_target_field"})
            continue
        rules.append({"when_contains": markers[0], "target": target})
        accepted.append(
            {
                "constraint": constraint,
                "marker": markers[0],
                "target": {"type": "use_case", "field": "use_case"},
                "source": "profile.constraints.derive_from_sku_meaning",
            }
        )
    return _dedupe_guard_rules(rules, marker_key="when_contains"), {"materialized": accepted, "skipped": skipped}


def _characteristic_mappings(axes_payload: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    rules: list[dict[str, Any]] = []
    for source_key in _CHARACTERISTIC_AXIS_KEYS:
        for item in _mapping_items(axes_payload.get(source_key)):
            name_contains = _normalize(item.get("name_contains") or item.get("label") or item.get("name"))
            target = _mapping(item.get("target"))
            if not name_contains or not target:
                skipped.append({"source": source_key, "reason": "missing_name_or_target"})
                continue
            if not _is_known_target(target):
                skipped.append(
                    {
                        "source": source_key,
                        "name_contains": name_contains,
                        "reason": "unknown_target_field",
                    }
                )
                continue
            rules.append({"name_contains": name_contains, "target": dict(target)})
            accepted.append(
                {
                    "source": source_key,
                    "name_contains": name_contains,
                    "target": {"type": str(target.get("type") or ""), "field": str(target.get("field") or "")},
                }
            )
    return _dedupe_guard_rules(rules, marker_key="name_contains"), {"materialized": accepted, "skipped": skipped}


def _excluded_atom_rules(axes_payload: Mapping[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    rules: list[dict[str, Any]] = []

    for source_key in _EXPLICIT_EXCLUSION_AXIS_KEYS:
        for item in _mapping_items(axes_payload.get(source_key)):
            marker = _normalize(item.get("when_contains"))
            exclude = _mapping(item.get("exclude"))
            if not marker or not exclude:
                skipped.append({"source": source_key, "reason": "missing_marker_or_exclude"})
                continue
            if not _is_known_target(exclude):
                skipped.append({"source": source_key, "when_contains": marker, "reason": "unknown_target_field"})
                continue
            rules.append({"when_contains": marker, "exclude": dict(exclude)})
            accepted.append(
                {
                    "source": source_key,
                    "marker": marker,
                    "target": {"field": str(exclude.get("field") or "")},
                }
            )

    weak_skipped = {
        key: "not materialized as exclusions without explicit field/value evidence"
        for key in _WEAK_AXIS_KEYS
        if _string_list(axes_payload.get(key))
    }
    return _dedupe_guard_rules(rules, marker_key="when_contains"), {
        "materialized": accepted,
        "skipped": skipped,
        "skipped_weak_axis_groups": weak_skipped,
    }


def _diagnostics(
    evidence_input: Mapping[str, Any],
    *,
    product_type_diagnostics: Sequence[Mapping[str, Any]],
    required_diagnostics: Mapping[str, Any],
    excluded_diagnostics: Mapping[str, Any],
    characteristic_diagnostics: Mapping[str, Any],
    functional_diagnostics: Mapping[str, Any],
    product_type_rules_count: int,
    required_atoms_count: int,
    excluded_atoms_count: int,
    characteristic_mappings_count: int,
    functional_mappings_count: int,
) -> dict[str, Any]:
    return {
        "builder_method": GUARD_BUILDER_METHOD,
        "input_evidence_hash": str(evidence_input.get("evidence_hash") or ""),
        "inputs_used": [
            "profile.product_type_aliases",
            "profile.constraints.derive_from_query_tokens",
            "profile.constraints.derive_from_sku_meaning",
            "axes.explicit_guard_axes_when_available",
        ],
        "heuristics_applied": [
            "product_type_detection_from_profile_alias_prefixes",
            "constraint_markers_materialized_as_use_case_atoms",
            "sku_functional_markers_materialized_only_to_known_fields",
            "weak_axes_recorded_as_diagnostics_not_guards",
        ],
        "query_guard_counts": {
            "product_type_detection": product_type_rules_count,
            "required_atoms": required_atoms_count,
            "excluded_atoms": excluded_atoms_count,
        },
        "sku_guard_counts": {
            "characteristic_mappings": characteristic_mappings_count,
            "functional_token_mappings": functional_mappings_count,
        },
        "product_type_detection": list(product_type_diagnostics),
        "required_atoms": dict(required_diagnostics),
        "excluded_atoms": dict(excluded_diagnostics),
        "characteristic_mappings": dict(characteristic_diagnostics),
        "functional_token_mappings": dict(functional_diagnostics),
        "market_fields_used_for_build_decisions": False,
    }


def _dedupe_guard_rules(rules: Sequence[Mapping[str, Any]], *, marker_key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for rule in rules:
        key = _stable_key({"marker": rule.get(marker_key), "payload": rule})
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(rule))
    return sorted(result, key=lambda item: (str(item.get(marker_key) or ""), _stable_key(item)))


def _is_known_target(target: Mapping[str, Any]) -> bool:
    field = str(target.get("field") or "").strip()
    return bool(field and field in _KNOWN_GUARD_FIELDS)


def _constraint_value(value: Any) -> str:
    tokens = _tokens(value)
    if not tokens:
        return ""
    return "_".join(tokens[:6])


def _tokens(value: Any) -> tuple[str, ...]:
    return tuple(match.group(0).lower().replace("ё", "е") for match in _WORD_RE.finditer(str(value or "")))


def _normalize(value: Any) -> str:
    return str(value or "").strip().lower().replace("ё", "е")


def _unique_strings(values: Sequence[Any]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _normalize(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return tuple(result)


def _string_list(value: Any) -> tuple[str, ...]:
    return _unique_strings(value if isinstance(value, (list, tuple)) else [])


def _mapping_items(value: Any) -> tuple[Mapping[str, Any], ...]:
    rows = value if isinstance(value, (list, tuple)) else []
    return tuple(item for item in rows if isinstance(item, Mapping))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _stable_key(value: Mapping[str, Any]) -> str:
    return hashlib.sha1(str(sorted(value.items())).encode("utf-8")).hexdigest()


__all__ = [
    "GUARD_BUILDER_METHOD",
    "CategoryProfileGuardDraft",
    "enrich_profile_guards",
]
