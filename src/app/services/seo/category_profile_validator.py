"""Self-check validator for category profile payloads."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from app.schemas.seo_category_profile import (
    CategoryProfileSelfCheckItem,
    CategoryProfileSelfCheckReport,
)
from app.services.seo.global_vocabulary import GlobalVocabulary


_GLOBAL_ONLY_KEYS = {
    "audience_taxonomy",
    "audience_synonyms",
    "expressive_taxonomy",
    "expressive_synonyms",
    "recipient_synonyms",
    "color_taxonomy",
    "color_synonyms",
    "material_taxonomy",
    "material_synonyms",
    "numeric_parsers",
}
_ALLOWED_QUERY_PREDICATES = {"constraint", "constraint_prefix", "product_type"}
_ALLOWED_SKU_REQUIREMENTS = {
    "constraint",
    "constraint_prefix",
    "product_type",
    "product_type_contains",
    "token_prefix",
}
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


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _bool_result(result: bool) -> str:
    return "pass" if result else "fail"


def _iter_constraint_names(payload: Mapping[str, Any]) -> set[str]:
    constraints = _as_mapping(payload.get("constraints"))
    names: set[str] = set()
    for item in _as_list(constraints.get("derive_from_query_tokens")):
        if isinstance(item, Mapping) and isinstance(item.get("constraint"), str):
            names.add(str(item["constraint"]))
    for item in _as_list(constraints.get("derive_from_sku_meaning")):
        if isinstance(item, Mapping) and isinstance(item.get("constraint"), str):
            names.add(str(item["constraint"]))
    return names


def _referenced_constraints(payload: Mapping[str, Any]) -> set[str]:
    referenced: set[str] = set()
    for rule in _as_list(payload.get("hard_conflicts")):
        if not isinstance(rule, Mapping):
            continue
        when_query_has = _as_mapping(rule.get("when_query_has"))
        if isinstance(when_query_has.get("constraint"), str):
            referenced.add(str(when_query_has["constraint"]))
        if isinstance(when_query_has.get("constraint_prefix"), str):
            referenced.add(str(when_query_has["constraint_prefix"]))
        for requirement in _as_list(rule.get("requires_sku_any")):
            if not isinstance(requirement, Mapping):
                continue
            if isinstance(requirement.get("constraint"), str):
                referenced.add(str(requirement["constraint"]))
            if isinstance(requirement.get("constraint_prefix"), str):
                referenced.add(str(requirement["constraint_prefix"]))
    return referenced


def _iter_guard_targets(payload: Mapping[str, Any]) -> Iterable[str]:
    sku_guards = _as_mapping(payload.get("sku_guards"))
    for mapping_item in _as_list(sku_guards.get("characteristic_mappings")):
        if not isinstance(mapping_item, Mapping):
            continue
        target = _as_mapping(mapping_item.get("target"))
        if isinstance(target.get("field"), str):
            yield str(target["field"])
        for keyword_item in _as_list(mapping_item.get("target_keywords")):
            if not isinstance(keyword_item, Mapping):
                continue
            keyword_target = _as_mapping(keyword_item.get("target"))
            if isinstance(keyword_target.get("field"), str):
                yield str(keyword_target["field"])
    for mapping_item in _as_list(sku_guards.get("functional_token_mappings")):
        if not isinstance(mapping_item, Mapping):
            continue
        target = _as_mapping(mapping_item.get("target"))
        if isinstance(target.get("field"), str):
            yield str(target["field"])

    query_guards = _as_mapping(payload.get("query_guards"))
    for mapping_item in _as_list(query_guards.get("product_type_detection")):
        if not isinstance(mapping_item, Mapping):
            continue
        for required in _as_list(mapping_item.get("add_required")):
            if not isinstance(required, Mapping):
                continue
            if isinstance(required.get("field"), str):
                yield str(required["field"])
    for mapping_item in _as_list(query_guards.get("required_atoms")):
        if not isinstance(mapping_item, Mapping):
            continue
        atom = _as_mapping(mapping_item.get("atom"))
        if isinstance(atom.get("field"), str):
            yield str(atom["field"])
    for mapping_item in _as_list(query_guards.get("excluded_atoms")):
        if not isinstance(mapping_item, Mapping):
            continue
        atom = _as_mapping(mapping_item.get("exclude"))
        if isinstance(atom.get("field"), str):
            yield str(atom["field"])


def validate_category_profile_payload(
    payload: Mapping[str, Any],
    *,
    vocabulary: GlobalVocabulary | None = None,
    subject_match_share: float | None = None,
) -> CategoryProfileSelfCheckReport:
    """Validate a category-profile payload against the Phase 0 Step 3 contract."""

    checks: list[CategoryProfileSelfCheckItem] = []

    schema_ok = payload.get("schema_version") == "category_profile_v1"
    checks.append(
        CategoryProfileSelfCheckItem(
            name="schema_version_is_v1",
            result=_bool_result(schema_ok),
            detail=f"schema_version={payload.get('schema_version')!r}",
        )
    )

    subject = _as_mapping(payload.get("subject"))
    primary = str(subject.get("primary") or "").strip()
    aliases = [item for item in _as_list(subject.get("primary_aliases")) if isinstance(item, str) and item.strip()]
    subject_ok = bool(primary and aliases)
    checks.append(
        CategoryProfileSelfCheckItem(
            name="subject_non_empty",
            result=_bool_result(subject_ok),
            detail=f"primary={primary!r}, aliases={len(aliases)}",
        )
    )

    coverage_value = subject_match_share
    if coverage_value is None:
        generated_by = _as_mapping(payload.get("generated_by"))
        corpus_signals = _as_mapping(generated_by.get("corpus_signals"))
        raw_share = corpus_signals.get("csv_subject_match_share")
        if isinstance(raw_share, (int, float)):
            coverage_value = float(raw_share)
    if coverage_value is None:
        coverage_ok = subject_ok
        coverage_detail = "coverage input absent; using subject_non_empty as skeleton fallback"
    else:
        coverage_ok = float(coverage_value) >= 0.70
        coverage_detail = f"subject_match_share={float(coverage_value):.4f}"
    checks.append(
        CategoryProfileSelfCheckItem(
            name="subject_coverage",
            result=_bool_result(coverage_ok),
            detail=coverage_detail,
        )
    )

    hard_conflicts = [item for item in _as_list(payload.get("hard_conflicts")) if isinstance(item, Mapping)]
    related_subjects = [
        str(item.get("subject"))
        for item in _as_list(subject.get("related_but_different"))
        if isinstance(item, Mapping) and isinstance(item.get("subject"), str)
    ]
    covered_subjects: set[str] = set()
    for rule in hard_conflicts:
        when_query_has = _as_mapping(rule.get("when_query_has"))
        if isinstance(when_query_has.get("product_type"), str):
            covered_subjects.add(str(when_query_has["product_type"]))
        for requirement in _as_list(rule.get("requires_sku_any")):
            if isinstance(requirement, Mapping) and isinstance(requirement.get("product_type"), str):
                covered_subjects.add(str(requirement["product_type"]))
    uncovered = [item for item in related_subjects if item not in covered_subjects]
    checks.append(
        CategoryProfileSelfCheckItem(
            name="hard_conflicts_cover_related",
            result=_bool_result(not uncovered),
            detail="all related subjects covered" if not uncovered else f"missing subjects: {', '.join(uncovered)}",
        )
    )

    syntax_errors: list[str] = []
    for index, rule in enumerate(hard_conflicts):
        when_query_has = _as_mapping(rule.get("when_query_has"))
        invalid_query_keys = sorted(set(when_query_has) - _ALLOWED_QUERY_PREDICATES)
        if invalid_query_keys:
            syntax_errors.append(f"hard_conflicts[{index}].when_query_has -> {', '.join(invalid_query_keys)}")
        for requirement in _as_list(rule.get("requires_sku_any")):
            if not isinstance(requirement, Mapping):
                syntax_errors.append(f"hard_conflicts[{index}].requires_sku_any contains non-object")
                continue
            invalid_requirement_keys = sorted(set(requirement) - _ALLOWED_SKU_REQUIREMENTS)
            if invalid_requirement_keys:
                syntax_errors.append(
                    f"hard_conflicts[{index}].requires_sku_any -> {', '.join(invalid_requirement_keys)}"
                )
    checks.append(
        CategoryProfileSelfCheckItem(
            name="hard_conflicts_syntax",
            result=_bool_result(not syntax_errors),
            detail="syntax ok" if not syntax_errors else "; ".join(syntax_errors),
        )
    )

    scoring = _as_mapping(payload.get("scoring"))
    cutoffs = _as_mapping(scoring.get("bucket_cutoffs"))
    primary_cutoff = cutoffs.get("primary")
    secondary_cutoff = cutoffs.get("secondary")
    broad_cutoff = cutoffs.get("broad")
    monotonic_ok = all(isinstance(item, (int, float)) for item in (primary_cutoff, secondary_cutoff, broad_cutoff))
    if monotonic_ok:
        monotonic_ok = float(primary_cutoff) > float(secondary_cutoff) > float(broad_cutoff) > 0.0
    checks.append(
        CategoryProfileSelfCheckItem(
            name="bucket_cutoffs_monotonic",
            result=_bool_result(monotonic_ok),
            detail=f"primary={primary_cutoff}, secondary={secondary_cutoff}, broad={broad_cutoff}",
        )
    )

    defined_constraints = _iter_constraint_names(payload)
    referenced_constraints = _referenced_constraints(payload)
    unused_constraints = sorted(item for item in defined_constraints if item not in referenced_constraints)
    checks.append(
        CategoryProfileSelfCheckItem(
            name="constraint_references",
            result=_bool_result(not unused_constraints),
            detail="all constraints referenced" if not unused_constraints else f"unused: {', '.join(unused_constraints)}",
        )
    )

    unknown_guard_fields = sorted({field for field in _iter_guard_targets(payload) if field not in _KNOWN_GUARD_FIELDS})
    checks.append(
        CategoryProfileSelfCheckItem(
            name="guards_target_known_fields",
            result=_bool_result(not unknown_guard_fields),
            detail="all guard targets known" if not unknown_guard_fields else f"unknown fields: {', '.join(unknown_guard_fields)}",
        )
    )

    duplicate_keys = sorted(key for key in _GLOBAL_ONLY_KEYS if key in payload)
    if vocabulary is not None and duplicate_keys:
        detail = f"duplicates shared vocabulary sections: {', '.join(duplicate_keys)}"
    else:
        detail = "no shared vocabulary sections duplicated" if not duplicate_keys else f"duplicated keys: {', '.join(duplicate_keys)}"
    checks.append(
        CategoryProfileSelfCheckItem(
            name="no_cross_category_duplication",
            result=_bool_result(not duplicate_keys),
            detail=detail,
        )
    )

    checks.append(
        CategoryProfileSelfCheckItem(
            name="eval_smoke",
            result="skip",
            detail="Deferred to Phase 0 Step 8 real derive/eval gate",
        )
    )

    status = "failed" if any(item.result == "fail" for item in checks) else "passed"
    return CategoryProfileSelfCheckReport(status=status, checks=checks)
