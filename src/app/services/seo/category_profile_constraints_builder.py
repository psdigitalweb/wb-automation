"""Generic constraint and hard-conflict builder for category profiles.

This layer enriches an in-memory ``category_profile_v1`` draft from existing
derive evidence. It does not persist, activate, call LLMs, or use category
economics as a decision signal.
"""

from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.services.seo.category_profile_derive_evidence import CategoryProfileDeriveEvidence


CONSTRAINTS_BUILDER_METHOD = "generic_constraints_hard_conflicts_builder_v1"
_WORD_RE = re.compile(r"[0-9a-zA-Zа-яА-ЯёЁ.]+", re.IGNORECASE)
_SKIPPED_WEAK_AXIS_KEYS = (
    "use_case_axes",
    "attribute_axes",
    "audience_axes",
    "expressive_axes",
    "occasion_axes",
    "negative_constraint_axes",
)


@dataclass(frozen=True)
class CategoryProfileConstraintsDraft:
    """Profile payload enriched with generic constraints and diagnostics."""

    profile_payload: Mapping[str, Any]
    diagnostics: Mapping[str, Any]


def enrich_profile_constraints(
    profile_payload: Mapping[str, Any],
    evidence: CategoryProfileDeriveEvidence | Mapping[str, Any],
) -> CategoryProfileConstraintsDraft:
    """Return a deterministic draft payload with generic constraints/conflicts."""

    evidence_input = evidence.to_builder_input() if isinstance(evidence, CategoryProfileDeriveEvidence) else dict(evidence)
    payload = copy.deepcopy(dict(profile_payload))
    axes_payload = _mapping(_mapping(evidence_input.get("axes")).get("axes_payload"))
    query_token_counts = _int_mapping(evidence_input.get("query_token_counts"))
    query_texts = _query_texts(evidence_input.get("query_candidates"))

    related_subjects = _related_subjects(payload)
    product_conflicts, product_diagnostics = _product_type_conflicts(related_subjects)
    constraint_rules, sku_rules, constraint_conflicts, constraint_diagnostics = _constraint_rules(
        axes_payload,
        query_token_counts=query_token_counts,
        query_texts=query_texts,
    )
    hard_conflicts = _dedupe_conflicts([*product_conflicts, *constraint_conflicts])

    payload["constraints"] = {
        "derive_from_query_tokens": constraint_rules,
        "derive_from_sku_meaning": sku_rules,
    }
    payload["hard_conflicts"] = hard_conflicts

    diagnostics = _diagnostics(
        evidence_input,
        related_subjects=related_subjects,
        product_diagnostics=product_diagnostics,
        constraint_diagnostics=constraint_diagnostics,
        constraint_rules_count=len(constraint_rules),
        hard_conflicts_count=len(hard_conflicts),
    )
    generated_by = payload.get("generated_by")
    if isinstance(generated_by, dict):
        generated_by["constraints_builder_diagnostics"] = diagnostics

    return CategoryProfileConstraintsDraft(profile_payload=payload, diagnostics=diagnostics)


def _constraint_rules(
    axes_payload: Mapping[str, Any],
    *,
    query_token_counts: Mapping[str, int],
    query_texts: Sequence[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    sku_rules: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for axis in _string_list(axes_payload.get("constraint_axes")):
        markers = _markers_for_axis(axis, query_token_counts=query_token_counts, query_texts=query_texts)
        if not markers:
            skipped.append({"axis": axis, "reason": "no_query_token_or_phrase_evidence"})
            continue
        constraint = _constraint_name(axis)
        rules.append({"constraint": constraint, "when_query_contains_any": list(markers)})
        sku_rules.append({"constraint": constraint, "when_functional_attribute_contains": list(markers)})
        conflicts.append(
            {
                "name": f"constraint_{_slug(constraint)}_required",
                "when_query_has": {"constraint": constraint},
                "requires_sku_any": [{"constraint": constraint}],
                "message": f"requires constraint: {constraint}",
            }
        )
        accepted.append({"axis": axis, "constraint": constraint, "markers": list(markers), "source": "axes.constraint_axes"})

    return (
        rules,
        sku_rules,
        conflicts,
        {
            "accepted_constraints": accepted,
            "skipped_constraint_axes": skipped,
            "skipped_weak_axis_groups": {
                key: "not promoted to hard conflicts without explicit constraint evidence"
                for key in _SKIPPED_WEAK_AXIS_KEYS
                if _string_list(axes_payload.get(key))
            },
        },
    )


def _product_type_conflicts(
    related_subjects: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    conflicts: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for item in related_subjects:
        subject = _normalize(item.get("subject"))
        if not subject:
            diagnostics.append({"subject": "", "status": "skipped", "reason": "empty_related_subject"})
            continue
        requirements: list[dict[str, str]] = [{"product_type": subject}]
        prefix = _first_prefix(_string_list(item.get("aliases")), fallback=subject)
        if prefix:
            requirements.append({"token_prefix": prefix})
        conflicts.append(
            {
                "name": f"product_type_{_slug(subject)}_mismatch",
                "when_query_has": {"product_type": subject},
                "requires_sku_any": requirements,
                "message": f"product_type conflict: query requires {subject}",
            }
        )
        diagnostics.append(
            {
                "subject": subject,
                "status": "covered",
                "source": "profile.subject.related_but_different",
                "requirements": requirements,
            }
        )
    return conflicts, diagnostics


def _markers_for_axis(
    axis: str,
    *,
    query_token_counts: Mapping[str, int],
    query_texts: Sequence[str],
) -> tuple[str, ...]:
    normalized = _normalize(axis)
    if not normalized:
        return ()
    markers: list[str] = []
    if any(normalized in text for text in query_texts):
        markers.append(normalized)
    tokens = _tokens(normalized)
    if tokens and all(query_token_counts.get(token, 0) > 0 for token in tokens):
        if len(tokens) == 1:
            markers.append(_stem(tokens[0]))
        else:
            markers.append(normalized)
    return _unique_strings(markers)[:4]


def _dedupe_conflicts(conflicts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for conflict in conflicts:
        name = str(conflict.get("name") or "")
        key = name or _stable_key(conflict)
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(conflict))
    return sorted(result, key=lambda item: str(item.get("name") or ""))


def _diagnostics(
    evidence_input: Mapping[str, Any],
    *,
    related_subjects: Sequence[Mapping[str, Any]],
    product_diagnostics: Sequence[Mapping[str, Any]],
    constraint_diagnostics: Mapping[str, Any],
    constraint_rules_count: int,
    hard_conflicts_count: int,
) -> dict[str, Any]:
    covered_related = [
        str(item.get("subject") or "")
        for item in product_diagnostics
        if item.get("status") == "covered" and str(item.get("subject") or "")
    ]
    all_related = [_normalize(item.get("subject")) for item in related_subjects if _normalize(item.get("subject"))]
    uncovered_related = [item for item in all_related if item not in covered_related]
    return {
        "builder_method": CONSTRAINTS_BUILDER_METHOD,
        "input_evidence_hash": str(evidence_input.get("evidence_hash") or ""),
        "inputs_used": [
            "profile.subject.related_but_different",
            "axes.constraint_axes",
            "query_token_counts",
            "query_candidates.normalized_query",
        ],
        "heuristics_applied": [
            "related_subjects_get_product_type_hard_conflicts",
            "constraint_axes_promoted_only_when_backed_by_query_tokens",
            "weak_axes_recorded_as_diagnostics_not_hard_conflicts",
        ],
        "hard_conflicts_count": hard_conflicts_count,
        "constraint_rules_count": constraint_rules_count,
        "uncovered_related_subjects": uncovered_related,
        "product_type_conflicts": list(product_diagnostics),
        "constraint_axes": dict(constraint_diagnostics),
        "economic_fields_used_for_build_decisions": False,
        "limitations": [
            "use_case, attribute, audience, expressive, occasion, and negative axes are not promoted to hard conflicts without explicit constraint evidence",
            "LLM refinement is not used in Phase 1 Step 3",
        ],
    }


def _related_subjects(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    subject = _mapping(payload.get("subject"))
    value = subject.get("related_but_different")
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _query_texts(value: Any) -> tuple[str, ...]:
    rows = value if isinstance(value, list) else []
    texts: list[str] = []
    for item in rows:
        if not isinstance(item, Mapping):
            continue
        for key in ("normalized_query", "display_query"):
            text = _normalize(item.get(key))
            if text:
                texts.append(text)
    return _unique_strings(texts)


def _constraint_name(axis: str) -> str:
    tokens = _tokens(axis)
    if not tokens:
        return _slug(axis)
    return "_".join(tokens[:6])


def _first_prefix(aliases: Sequence[str], *, fallback: str) -> str:
    source = aliases[0] if aliases else fallback
    tokens = _tokens(source)
    if not tokens:
        return ""
    return _stem(tokens[0])


def _stem(token: str) -> str:
    normalized = _normalize(token)
    if len(normalized) <= 5:
        return normalized
    return normalized[: max(4, min(8, len(normalized)))]


def _tokens(value: Any) -> tuple[str, ...]:
    return tuple(match.group(0).lower().replace("ё", "е") for match in _WORD_RE.finditer(str(value or "")))


def _slug(value: str) -> str:
    normalized = _normalize(value)
    encoded = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:8]
    ascii_part = re.sub(r"[^0-9a-zA-Z]+", "_", normalized).strip("_")
    return ascii_part or encoded


def _stable_key(value: Mapping[str, Any]) -> str:
    return hashlib.sha1(str(sorted(value.items())).encode("utf-8")).hexdigest()


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


def _int_mapping(value: Any) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, int] = {}
    for key, item in value.items():
        if isinstance(key, str) and isinstance(item, int):
            result[_normalize(key)] = int(item)
    return result


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


__all__ = [
    "CONSTRAINTS_BUILDER_METHOD",
    "CategoryProfileConstraintsDraft",
    "enrich_profile_constraints",
]
