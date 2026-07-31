"""Generic heuristic builder for draft category-profile payloads.

The builder consumes the Phase 1 evidence pack and produces an in-memory
``category_profile_v1`` draft. It does not persist, activate, call external
APIs, or use category economics as profile signals.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from app.services.seo.category_profile_constraints_builder import enrich_profile_constraints
from app.services.seo.category_profile_derive_evidence import CategoryProfileDeriveEvidence
from app.services.seo.category_profile_guard_builder import enrich_profile_guards


BUILDER_METHOD = "generic_heuristic_profile_builder_v1"
_WORD_RE = re.compile(r"[0-9a-zA-Zа-яА-ЯёЁ.]+", re.IGNORECASE)
_DEFAULT_SCORING = {
    "weights": {
        "product_type_match": 0.22,
        "product_type_compat": 0.16,
        "product_type_weak": -0.18,
        "use_case_overlap": 0.10,
        "attribute_overlap": 0.08,
        "expressive_overlap": 0.08,
        "audience_overlap": 0.06,
        "occasion_overlap": 0.04,
        "material_mismatch": -0.25,
        "negative_audience": -1.00,
    },
    "bucket_cutoffs": {
        "primary": 0.60,
        "secondary": 0.35,
        "broad": 0.15,
    },
    "bucket_caps": {
        "primary": 100,
        "secondary": 300,
        "broad": 500,
    },
    "materials_relevant": [],
}
_DEFAULT_BUCKET_LABELS = {
    "primary": "Лучшие",
    "secondary": "Подходящие",
    "broad": "Слишком общие",
    "rejected": "Не подходят",
}


class CategoryProfileBuilderError(Exception):
    """Base error for generic profile builder input problems."""


class WeakProfileEvidenceError(CategoryProfileBuilderError):
    """Raised when evidence is insufficient for a controlled draft."""


@dataclass(frozen=True)
class CategoryProfileDraft:
    """In-memory draft profile and explainability diagnostics."""

    profile_payload: Mapping[str, Any]
    diagnostics: Mapping[str, Any]


def build_category_profile_draft(
    evidence: CategoryProfileDeriveEvidence | Mapping[str, Any],
    *,
    primary_subject_hint: str | None = None,
    generated_at: datetime | None = None,
) -> CategoryProfileDraft:
    """Build a deterministic ``category_profile_v1`` draft from evidence."""

    evidence_input = evidence.to_builder_input() if isinstance(evidence, CategoryProfileDeriveEvidence) else dict(evidence)
    axes_payload = _mapping(_mapping(evidence_input.get("axes")).get("axes_payload"))
    product_type_axes = _string_list(axes_payload.get("product_type_axes"))
    if not product_type_axes:
        raise WeakProfileEvidenceError("product_type_axes evidence is required to build a category profile draft")

    query_token_counts = _int_mapping(evidence_input.get("query_token_counts"))
    primary, primary_source = _choose_primary_subject(
        product_type_axes,
        query_token_counts=query_token_counts,
        primary_subject_hint=primary_subject_hint,
    )
    synonym_groups = _synonym_groups(axes_payload.get("synonym_groups"))
    query_texts = _query_texts(evidence_input.get("query_candidates"))
    weak_axis_index = _weak_axis_index(axes_payload)
    primary_aliases = _unique_strings(
        [
            *_aliases_for_axis(primary, synonym_groups=synonym_groups, query_tokens=query_token_counts),
            *_component_axes_for_primary(primary, product_type_axes=product_type_axes, query_tokens=query_token_counts),
        ]
    )[:8]
    related_subjects = _related_subjects(
        product_type_axes,
        primary=primary,
        primary_aliases=primary_aliases,
        synonym_groups=synonym_groups,
        query_tokens=query_token_counts,
        query_texts=query_texts,
        weak_axis_index=weak_axis_index,
    )
    accepted_related_subjects = tuple(item for item, _diagnostic in related_subjects if item)
    related_axis_diagnostics = tuple(diagnostic for _item, diagnostic in related_subjects)
    token_prefixes = _prefixes_for_aliases(primary_aliases, fallback=primary)
    negative_token_prefixes = tuple(
        prefix
        for item in accepted_related_subjects
        for prefix in _prefixes_for_aliases(item["aliases"], fallback=item["subject"])
        if prefix not in token_prefixes
    )
    product_type_aliases = _product_type_aliases(
        primary=primary,
        primary_aliases=primary_aliases,
        related_subjects=accepted_related_subjects,
    )
    diagnostics = _build_diagnostics(
        evidence_input,
        primary=primary,
        primary_source=primary_source,
        product_type_axes=product_type_axes,
        related_subjects=accepted_related_subjects,
        related_axis_diagnostics=related_axis_diagnostics,
        token_prefixes=token_prefixes,
        negative_token_prefixes=negative_token_prefixes,
    )
    timestamp = _isoformat(generated_at or datetime(1970, 1, 1, tzinfo=timezone.utc))
    profile_payload = {
        "schema_version": "category_profile_v1",
        "subject": {
            "primary": primary,
            "primary_aliases": list(primary_aliases),
            "related_but_different": list(accepted_related_subjects),
            "detection_hints": {
                "token_prefixes": list(token_prefixes),
                "negative_token_prefixes": list(negative_token_prefixes),
            },
        },
        "product_type_aliases": product_type_aliases,
        "constraints": {
            "derive_from_query_tokens": [],
            "derive_from_sku_meaning": [],
        },
        "hard_conflicts": [],
        "scoring": json.loads(json.dumps(_DEFAULT_SCORING, sort_keys=True)),
        "user_bucket_labels": dict(_DEFAULT_BUCKET_LABELS),
        "sku_guards": {
            "characteristic_mappings": [],
            "functional_token_mappings": [],
        },
        "query_guards": {
            "product_type_detection": [],
            "required_atoms": [],
            "excluded_atoms": [],
        },
        "generated_by": {
            "method": BUILDER_METHOD,
            "llm_model": None,
            "prompt_version": None,
            "evidence_hash": str(evidence_input.get("evidence_hash") or ""),
            "generated_at": timestamp,
            "corpus_signals": {
                "queries_sampled": _int_from_path(evidence_input, "corpus", "query_count"),
                "distinct_queries": _int_from_path(evidence_input, "corpus", "distinct_query_count"),
                "top_queries_sampled": _int_from_path(evidence_input, "corpus", "top_queries_count"),
                "product_type_axes_count": len(product_type_axes),
                "economic_field_names_present_count": len(
                    _string_list(_mapping(evidence_input.get("corpus")).get("economic_field_names_present"))
                ),
            },
            "builder_diagnostics": diagnostics,
        },
    }
    constraints_draft = enrich_profile_constraints(profile_payload, evidence_input)
    guards_draft = enrich_profile_guards(constraints_draft.profile_payload, evidence_input)
    return CategoryProfileDraft(profile_payload=guards_draft.profile_payload, diagnostics=diagnostics)


def _choose_primary_subject(
    product_type_axes: Sequence[str],
    *,
    query_token_counts: Mapping[str, int],
    primary_subject_hint: str | None,
) -> tuple[str, str]:
    hint = _normalize(primary_subject_hint)
    axes = tuple(_normalize(axis) for axis in product_type_axes if _normalize(axis))
    if hint:
        for axis in axes:
            if hint == axis or hint in _tokens(axis) or axis in _tokens(hint):
                return axis, "primary_subject_hint"
        return hint, "primary_subject_hint"

    def axis_score(item: tuple[int, str]) -> tuple[int, int, int]:
        index, axis = item
        tokens = _tokens(axis)
        token_score = sum(int(query_token_counts.get(token, 0)) for token in tokens)
        phrase_score = int(query_token_counts.get(axis, 0))
        return (token_score + phrase_score, -len(tokens), -index)

    broad_candidate = max(enumerate(axes), key=axis_score)[1]
    specific_candidate = _more_specific_primary_candidate(
        broad_candidate,
        axes=axes,
        query_token_counts=query_token_counts,
        axis_score=axis_score,
    )
    if specific_candidate is not None:
        return specific_candidate, "product_type_axes_specific_product_type"
    return broad_candidate, "product_type_axes_token_frequency"


def _aliases_for_axis(
    axis: str,
    *,
    synonym_groups: Mapping[str, tuple[str, ...]],
    query_tokens: Mapping[str, int],
) -> tuple[str, ...]:
    aliases = [axis, *synonym_groups.get(axis, ())]
    axis_tokens = set(_tokens(axis))
    for token, _count in sorted(query_tokens.items(), key=lambda item: (-item[1], item[0])):
        normalized = _normalize(token)
        if normalized in axis_tokens or normalized == axis:
            aliases.append(normalized)
    return _unique_strings(aliases)[:8]


def _related_subjects(
    product_type_axes: Sequence[str],
    *,
    primary: str,
    primary_aliases: Sequence[str],
    synonym_groups: Mapping[str, tuple[str, ...]],
    query_tokens: Mapping[str, int],
    query_texts: Sequence[str],
    weak_axis_index: Mapping[str, tuple[str, ...]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    related: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for axis in product_type_axes:
        normalized = _normalize(axis)
        if not normalized or normalized == primary:
            continue
        if _is_axis_component_of_primary(normalized, primary):
            continue
        axis_evidence = _product_type_axis_evidence(
            normalized,
            primary=primary,
            primary_aliases=primary_aliases,
            query_tokens=query_tokens,
            query_texts=query_texts,
            synonym_groups=synonym_groups,
            weak_axis_index=weak_axis_index,
        )
        diagnostic = {
            "axis": normalized,
            "status": "accepted" if axis_evidence["accepted"] else "skipped",
            "reason": str(axis_evidence["reason"]),
            "evidence": dict(axis_evidence["evidence"]),
        }
        if not axis_evidence["accepted"]:
            related.append(({}, diagnostic))
            continue
        aliases = _aliases_for_axis(normalized, synonym_groups=synonym_groups, query_tokens=query_tokens)
        related.append(({"subject": normalized, "aliases": list(aliases)}, diagnostic))
    accepted_count = 0
    result: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item, diagnostic in related:
        if item:
            if accepted_count >= 6:
                continue
            accepted_count += 1
        result.append((item, diagnostic))
    return result


def _product_type_axis_evidence(
    axis: str,
    *,
    primary: str,
    primary_aliases: Sequence[str],
    query_tokens: Mapping[str, int],
    query_texts: Sequence[str],
    synonym_groups: Mapping[str, tuple[str, ...]],
    weak_axis_index: Mapping[str, tuple[str, ...]],
) -> dict[str, Any]:
    tokens = _tokens(axis)
    weak_groups = _weak_groups_for_axis(axis, weak_axis_index)
    phrase_rows = tuple(text for text in query_texts if _contains_axis_phrase(text, axis))
    primary_probe_tokens = _primary_probe_tokens(primary=primary, primary_aliases=primary_aliases)
    cooccurring_rows = tuple(text for text in phrase_rows if _contains_any_token(text, primary_probe_tokens))
    standalone_rows = tuple(text for text in phrase_rows if text not in cooccurring_rows)
    phrase_rows_count = len(phrase_rows)
    evidence = {
        "token_count": sum(int(query_tokens.get(token, 0)) for token in tokens),
        "direct_phrase": bool(phrase_rows),
        "direct_phrase_count": phrase_rows_count,
        "cooccurs_with_primary_count": len(cooccurring_rows),
        "standalone_phrase_count": len(standalone_rows),
        "cooccurs_with_primary_share": round(len(cooccurring_rows) / phrase_rows_count, 4)
        if phrase_rows_count
        else 0.0,
        "synonym_group_size": len(synonym_groups.get(axis, ())),
        "weak_axis_groups": list(weak_groups),
        "single_token_descriptor_shape": _looks_like_descriptor_token(axis),
    }
    if not tokens:
        return {"accepted": False, "reason": "empty_axis", "evidence": evidence}
    if evidence["single_token_descriptor_shape"]:
        return {"accepted": False, "reason": "descriptor_token_shape", "evidence": evidence}
    if _is_primary_qualifier_axis(axis, primary=primary, primary_aliases=primary_aliases):
        return {"accepted": False, "reason": "primary_component_or_qualifier_axis", "evidence": evidence}
    if _is_cooccurring_modifier_axis(axis, evidence=evidence):
        return {"accepted": False, "reason": "cooccurring_modifier_without_standalone_product_evidence", "evidence": evidence}
    if weak_groups and not _has_strong_product_evidence(axis, evidence=evidence):
        return {"accepted": False, "reason": "weak_axis_group_without_product_evidence", "evidence": evidence}
    if evidence["token_count"] <= 0 and not evidence["direct_phrase"]:
        return {"accepted": False, "reason": "no_query_token_or_phrase_evidence", "evidence": evidence}
    if not _has_standalone_product_evidence(axis, evidence=evidence):
        return {"accepted": False, "reason": "no_standalone_product_evidence", "evidence": evidence}
    return {"accepted": True, "reason": "product_type_axis_with_query_evidence", "evidence": evidence}


def _has_strong_product_evidence(axis: str, *, evidence: Mapping[str, Any]) -> bool:
    tokens = _tokens(axis)
    if len(tokens) > 1 and int(evidence.get("standalone_phrase_count") or 0) > 0:
        return True
    return (
        int(evidence.get("synonym_group_size") or 0) > 1
        and int(evidence.get("token_count") or 0) > 0
        and int(evidence.get("standalone_phrase_count") or 0) > 0
    )


def _has_standalone_product_evidence(axis: str, *, evidence: Mapping[str, Any]) -> bool:
    if int(evidence.get("standalone_phrase_count") or 0) <= 0:
        return False
    if len(_tokens(axis)) > 1:
        return True
    if int(evidence.get("synonym_group_size") or 0) > 1:
        return True
    return not bool(evidence.get("single_token_descriptor_shape"))


def _is_cooccurring_modifier_axis(axis: str, *, evidence: Mapping[str, Any]) -> bool:
    if len(_tokens(axis)) != 1:
        return False
    direct_phrase_count = int(evidence.get("direct_phrase_count") or 0)
    if direct_phrase_count <= 0:
        return False
    if int(evidence.get("standalone_phrase_count") or 0) > 0:
        return False
    return float(evidence.get("cooccurs_with_primary_share") or 0.0) >= 0.75


def _is_primary_qualifier_axis(axis: str, *, primary: str, primary_aliases: Sequence[str]) -> bool:
    axis_tokens = set(_tokens(axis))
    if not axis_tokens:
        return False
    primary_tokens = set(_tokens(primary))
    for alias in primary_aliases:
        primary_tokens.update(_tokens(alias))
    return bool(axis_tokens & primary_tokens)


def _primary_probe_tokens(*, primary: str, primary_aliases: Sequence[str]) -> tuple[str, ...]:
    tokens: list[str] = []
    for value in (primary, *primary_aliases):
        tokens.extend(_tokens(value))
    return _unique_strings(tokens)


def _contains_any_token(text: str, probes: Sequence[str]) -> bool:
    text_tokens = set(_tokens(text))
    return any(probe in text_tokens for probe in probes)


def _contains_axis_phrase(text: str, axis: str) -> bool:
    axis_tokens = _tokens(axis)
    text_tokens = _tokens(text)
    if not axis_tokens or len(axis_tokens) > len(text_tokens):
        return False
    window_size = len(axis_tokens)
    return any(tuple(text_tokens[index : index + window_size]) == axis_tokens for index in range(len(text_tokens)))


def _weak_groups_for_axis(axis: str, weak_axis_index: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    axis_tokens = set(_tokens(axis))
    axis_stems = {key for token in axis_tokens for key in _token_family_keys(token)}
    groups: list[str] = []
    for weak_axis, source_groups in weak_axis_index.items():
        weak_tokens = set(_tokens(weak_axis))
        weak_stems = {key for token in weak_tokens for key in _token_family_keys(token)}
        if axis == weak_axis or axis_tokens & weak_tokens or axis_stems & weak_stems:
            groups.extend(source_groups)
    return _unique_strings(groups)


def _token_family_keys(token: str) -> tuple[str, ...]:
    normalized = _normalize(token)
    if not normalized:
        return ()
    keys = [normalized, _stem(normalized)]
    if re.fullmatch(r"[а-яё]+", normalized):
        if len(normalized) > 4:
            keys.append(normalized[:-1])
        if len(normalized) > 6:
            keys.append(normalized[:6])
    return _unique_strings(keys)


def _looks_like_descriptor_token(axis: str) -> bool:
    tokens = _tokens(axis)
    if len(tokens) != 1:
        return False
    token = tokens[0]
    if not re.fullmatch(r"[а-яё]+", token):
        return False
    descriptor_suffixes = (
        "ый",
        "ий",
        "ой",
        "ая",
        "яя",
        "ое",
        "ее",
        "ые",
        "ие",
        "ого",
        "его",
        "ому",
        "ему",
        "ым",
        "им",
        "ом",
        "ем",
        "ия",
        "ами",
        "ями",
    )
    return len(token) > 4 and token.endswith(descriptor_suffixes)


def _product_type_aliases(
    *,
    primary: str,
    primary_aliases: Sequence[str],
    related_subjects: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {
        primary: {"match_any_prefix": list(_prefixes_for_aliases(primary_aliases, fallback=primary)), "score_bonus": 0.22}
    }
    for item in related_subjects:
        subject = str(item.get("subject") or "")
        aliases = _string_list(item.get("aliases"))
        if subject:
            result[subject] = {
                "match_any_prefix": list(_prefixes_for_aliases(aliases, fallback=subject)),
                "score_bonus": 0.08,
            }
    return dict(sorted(result.items(), key=lambda item: item[0]))


def _build_diagnostics(
    evidence_input: Mapping[str, Any],
    *,
    primary: str,
    primary_source: str,
    product_type_axes: Sequence[str],
    related_subjects: Sequence[Mapping[str, Any]],
    related_axis_diagnostics: Sequence[Mapping[str, Any]],
    token_prefixes: Sequence[str],
    negative_token_prefixes: Sequence[str],
) -> dict[str, Any]:
    fallback_fields = [
        "scoring",
        "user_bucket_labels",
        "sku_guards",
        "query_guards.required_atoms",
        "query_guards.excluded_atoms",
    ]
    return {
        "builder_method": BUILDER_METHOD,
        "input_evidence_hash": str(evidence_input.get("evidence_hash") or ""),
        "inputs_used": [
            "axes.product_type_axes",
            "axes.synonym_groups",
            "query_token_counts",
            "corpus.query_count",
            "corpus.distinct_query_count",
        ],
        "heuristics_applied": [
            "primary_subject_from_hint_or_product_type_axis_frequency",
            "primary_subject_prefers_specific_product_axis_over_component_axis",
            "aliases_from_axes_synonyms_and_query_tokens",
            "related_subjects_from_product_type_axes_with_generic_product_evidence",
            "weak_descriptor_use_case_audience_axes_skipped_from_related_subjects",
            "detection_prefixes_from_aliases",
            "default_scoring_from_category_profile_v1_contract",
        ],
        "primary_subject": primary,
        "primary_subject_source": primary_source,
        "product_type_axes_considered": list(product_type_axes),
        "related_subjects_count": len(related_subjects),
        "related_product_type_axes": {
            "accepted": [dict(item) for item in related_axis_diagnostics if item.get("status") == "accepted"],
            "skipped": [dict(item) for item in related_axis_diagnostics if item.get("status") == "skipped"],
        },
        "token_prefixes_count": len(token_prefixes),
        "negative_token_prefixes_count": len(negative_token_prefixes),
        "fallback_fields": fallback_fields,
        "economic_fields_used_for_build_decisions": False,
    }


def _synonym_groups(value: Any) -> dict[str, tuple[str, ...]]:
    groups: dict[str, tuple[str, ...]] = {}
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, Mapping):
            continue
        label = _normalize(item.get("label"))
        variants = _unique_strings([label, *_string_list(item.get("variants"))])
        if label and variants:
            groups[label] = variants
    return groups


def _weak_axis_index(axes_payload: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    weak_keys = (
        "use_case_axes",
        "attribute_axes",
        "audience_axes",
        "expressive_axes",
        "occasion_axes",
        "negative_constraint_axes",
    )
    result: dict[str, tuple[str, ...]] = {}
    for key in weak_keys:
        for axis in _string_list(axes_payload.get(key)):
            existing = list(result.get(axis, ()))
            existing.append(key)
            result[axis] = _unique_strings(existing)
    return result


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


def _more_specific_primary_candidate(
    broad_candidate: str,
    *,
    axes: Sequence[str],
    query_token_counts: Mapping[str, int],
    axis_score: Any,
) -> str | None:
    if not broad_candidate:
        return None
    specific_axes = [
        axis
        for axis in axes
        if axis != broad_candidate
        and _is_axis_component_of_primary(broad_candidate, axis)
        and _has_direct_axis_evidence(axis, query_token_counts=query_token_counts)
    ]
    if not specific_axes:
        return None

    indexed_axes = {axis: index for index, axis in enumerate(axes)}
    return max(
        specific_axes,
        key=lambda axis: (
            len(_tokens(axis)),
            len(axis),
            axis_score((indexed_axes[axis], axis))[0],
            -indexed_axes[axis],
        ),
    )


def _component_axes_for_primary(
    primary: str,
    *,
    product_type_axes: Sequence[str],
    query_tokens: Mapping[str, int],
) -> tuple[str, ...]:
    return _unique_strings(
        [
            axis
            for axis in product_type_axes
            if _is_axis_component_of_primary(_normalize(axis), primary)
            and _has_direct_axis_evidence(_normalize(axis), query_token_counts=query_tokens)
        ]
    )


def _is_axis_component_of_primary(axis: str, primary: str) -> bool:
    axis_tokens = _tokens(axis)
    primary_tokens = _tokens(primary)
    if not axis_tokens or not primary_tokens or axis == primary:
        return False
    if len(axis_tokens) == 1:
        axis_token = axis_tokens[0]
        return any(
            primary_token != axis_token
            and len(primary_token) >= len(axis_token) + 2
            and (primary_token.startswith(axis_token) or axis_token in primary_token)
            for primary_token in primary_tokens
        )
    return all(token in primary_tokens for token in axis_tokens) and len(primary_tokens) > len(axis_tokens)


def _has_direct_axis_evidence(axis: str, *, query_token_counts: Mapping[str, int]) -> bool:
    tokens = _tokens(axis)
    if not tokens:
        return False
    if query_token_counts.get(axis, 0) > 0:
        return True
    return all(query_token_counts.get(token, 0) > 0 for token in tokens)


def _prefixes_for_aliases(aliases: Sequence[str], *, fallback: str) -> tuple[str, ...]:
    prefixes: list[str] = []
    for alias in aliases:
        normalized = _normalize(alias)
        if not normalized:
            continue
        tokens = _tokens(normalized)
        if len(tokens) == 1:
            prefixes.append(_stem(tokens[0]))
        else:
            prefixes.append(normalized)
    if not prefixes:
        prefixes.append(_stem(_normalize(fallback)))
    return _unique_strings(prefixes)[:6]


def _stem(token: str) -> str:
    normalized = _normalize(token)
    if len(normalized) <= 5:
        return normalized
    return normalized[: max(4, min(8, len(normalized)))]


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(match.group(0).lower().replace("ё", "е") for match in _WORD_RE.finditer(value or ""))


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


def _int_from_path(value: Mapping[str, Any], *path: str) -> int:
    current: Any = value
    for key in path:
        current = _mapping(current).get(key)
    return int(current) if isinstance(current, int) else 0


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "BUILDER_METHOD",
    "CategoryProfileBuilderError",
    "CategoryProfileDraft",
    "WeakProfileEvidenceError",
    "build_category_profile_draft",
]
