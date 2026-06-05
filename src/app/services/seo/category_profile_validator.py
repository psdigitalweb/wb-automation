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
_REQUIRED_OPERATIONAL_SECTIONS = (
    "subject",
    "product_type_aliases",
    "constraints",
    "hard_conflicts",
    "scoring",
    "user_bucket_labels",
    "sku_guards",
    "query_guards",
)
_ECONOMIC_DECISION_PATTERNS = (
    "orders",
    "order",
    "conversion",
    "конверсия",
    "заказ",
    "заказали",
)
_REQUIRED_SCORING_KEYS = ("weights", "bucket_cutoffs", "bucket_caps")
_REQUIRED_BUCKETS = ("primary", "secondary", "broad")
_REQUIRED_LABEL_BUCKETS = ("primary", "secondary", "broad", "rejected")
_CONSTRAINT_QUERY_MARKER_KEYS = ("when_query_contains_any",)
_CONSTRAINT_SKU_MARKER_KEYS = ("when_functional_attribute_contains",)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _bool_result(result: bool) -> str:
    return "pass" if result else "fail"


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _string_items(value: Any) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if _is_non_empty_string(item)]


def _has_economic_decision_text(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            _has_economic_decision_text(key) or _has_economic_decision_text(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_has_economic_decision_text(item) for item in value)
    if isinstance(value, str):
        normalized = value.lower().replace("ё", "е")
        return any(pattern in normalized for pattern in _ECONOMIC_DECISION_PATTERNS)
    return False


def _target_field(target: Mapping[str, Any]) -> str | None:
    field = target.get("field")
    return str(field) if isinstance(field, str) else None


def _iter_constraint_names(payload: Mapping[str, Any]) -> set[str]:
    constraints = _as_mapping(payload.get("constraints"))
    names: set[str] = set()
    for item in _as_list(constraints.get("derive_from_query_tokens")):
        if isinstance(item, Mapping) and _is_non_empty_string(item.get("constraint")):
            names.add(str(item["constraint"]))
    for item in _as_list(constraints.get("derive_from_sku_meaning")):
        if isinstance(item, Mapping) and _is_non_empty_string(item.get("constraint")):
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
    query_guards = _as_mapping(payload.get("query_guards"))
    for item in _as_list(query_guards.get("required_atoms")):
        if not isinstance(item, Mapping):
            continue
        atom = _as_mapping(item.get("atom"))
        value = atom.get("value")
        if atom.get("field") == "use_case" and isinstance(value, str):
            referenced.add(value)
    sku_guards = _as_mapping(payload.get("sku_guards"))
    for item in _as_list(sku_guards.get("functional_token_mappings")):
        if not isinstance(item, Mapping):
            continue
        target = _as_mapping(item.get("target"))
        value = target.get("value")
        if target.get("field") == "use_case" and isinstance(value, str):
            referenced.add(value)
    return referenced


def _operational_section_errors(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for section in _REQUIRED_OPERATIONAL_SECTIONS:
        value = payload.get(section)
        if section == "hard_conflicts":
            if not isinstance(value, list):
                errors.append(f"{section} must be a list")
        elif not isinstance(value, Mapping):
            errors.append(f"{section} must be an object")
    return errors


def _subject_structure_errors(subject: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    aliases = _string_items(subject.get("primary_aliases"))
    if len(aliases) != len(_as_list(subject.get("primary_aliases"))):
        errors.append("subject.primary_aliases must contain only non-empty strings")
    hints = _as_mapping(subject.get("detection_hints"))
    if not hints:
        errors.append("subject.detection_hints must be an object")
    for key in ("token_prefixes", "negative_token_prefixes"):
        raw_values = _as_list(hints.get(key))
        values = _string_items(raw_values)
        if len(values) != len(raw_values):
            errors.append(f"subject.detection_hints.{key} must contain only non-empty strings")
    for index, item in enumerate(_as_list(subject.get("related_but_different"))):
        if not isinstance(item, Mapping):
            errors.append(f"subject.related_but_different[{index}] must be an object")
            continue
        if not _is_non_empty_string(item.get("subject")):
            errors.append(f"subject.related_but_different[{index}].subject is required")
        aliases_raw = _as_list(item.get("aliases"))
        if len(_string_items(aliases_raw)) != len(aliases_raw):
            errors.append(f"subject.related_but_different[{index}].aliases must contain only non-empty strings")
    return errors


def _product_type_alias_errors(payload: Mapping[str, Any], primary: str) -> list[str]:
    product_type_aliases = _as_mapping(payload.get("product_type_aliases"))
    errors: list[str] = []
    if primary and primary not in product_type_aliases:
        errors.append(f"product_type_aliases missing primary subject {primary!r}")
    for subject_name, raw_rule in product_type_aliases.items():
        if not _is_non_empty_string(subject_name):
            errors.append("product_type_aliases keys must be non-empty strings")
            continue
        rule = _as_mapping(raw_rule)
        prefixes = _string_items(rule.get("match_any_prefix"))
        if not rule or not prefixes or len(prefixes) != len(_as_list(rule.get("match_any_prefix"))):
            errors.append(f"product_type_aliases[{subject_name!r}].match_any_prefix must be non-empty strings")
        score_bonus = rule.get("score_bonus")
        if score_bonus is not None and not isinstance(score_bonus, (int, float)):
            errors.append(f"product_type_aliases[{subject_name!r}].score_bonus must be numeric when present")
    return errors


def _scoring_structure_errors(payload: Mapping[str, Any]) -> list[str]:
    scoring = _as_mapping(payload.get("scoring"))
    errors: list[str] = []
    for key in _REQUIRED_SCORING_KEYS:
        if not isinstance(scoring.get(key), Mapping):
            errors.append(f"scoring.{key} must be an object")
    weights = _as_mapping(scoring.get("weights"))
    if not weights:
        errors.append("scoring.weights must be non-empty")
    for key, value in weights.items():
        if not _is_non_empty_string(key) or not isinstance(value, (int, float)):
            errors.append("scoring.weights must map non-empty names to numeric values")
            break
    for section_name in ("bucket_cutoffs", "bucket_caps"):
        section = _as_mapping(scoring.get(section_name))
        missing = [bucket for bucket in _REQUIRED_BUCKETS if bucket not in section]
        if missing:
            errors.append(f"scoring.{section_name} missing buckets: {', '.join(missing)}")
        for key, value in section.items():
            expected_type = int if section_name == "bucket_caps" else (int, float)
            if not _is_non_empty_string(key) or not isinstance(value, expected_type):
                errors.append(f"scoring.{section_name} must map bucket names to numeric values")
                break
    labels = _as_mapping(payload.get("user_bucket_labels"))
    missing_labels = [bucket for bucket in _REQUIRED_LABEL_BUCKETS if not _is_non_empty_string(labels.get(bucket))]
    if missing_labels:
        errors.append(f"user_bucket_labels missing buckets: {', '.join(missing_labels)}")
    return errors


def _constraint_structure_errors(payload: Mapping[str, Any]) -> list[str]:
    constraints = _as_mapping(payload.get("constraints"))
    errors: list[str] = []
    for key in ("derive_from_query_tokens", "derive_from_sku_meaning"):
        if not isinstance(constraints.get(key), list):
            errors.append(f"constraints.{key} must be a list")
    for key, marker_keys in (
        ("derive_from_query_tokens", _CONSTRAINT_QUERY_MARKER_KEYS),
        ("derive_from_sku_meaning", _CONSTRAINT_SKU_MARKER_KEYS),
    ):
        for index, item in enumerate(_as_list(constraints.get(key))):
            if not isinstance(item, Mapping):
                errors.append(f"constraints.{key}[{index}] must be an object")
                continue
            if not _is_non_empty_string(item.get("constraint")):
                errors.append(f"constraints.{key}[{index}].constraint is required")
            if not any(_string_items(item.get(marker_key)) for marker_key in marker_keys):
                errors.append(f"constraints.{key}[{index}] must include non-empty marker list")
    return errors


def _guard_structure_errors(payload: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    query_guards = _as_mapping(payload.get("query_guards"))
    sku_guards = _as_mapping(payload.get("sku_guards"))
    for key in ("product_type_detection", "required_atoms", "excluded_atoms"):
        if not isinstance(query_guards.get(key), list):
            errors.append(f"query_guards.{key} must be a list")
    for key in ("characteristic_mappings", "functional_token_mappings"):
        if not isinstance(sku_guards.get(key), list):
            errors.append(f"sku_guards.{key} must be a list")

    for index, item in enumerate(_as_list(query_guards.get("product_type_detection"))):
        if not isinstance(item, Mapping):
            errors.append(f"query_guards.product_type_detection[{index}] must be an object")
            continue
        if not _is_non_empty_string(item.get("when_contains")) or not _is_non_empty_string(
            item.get("set_product_type")
        ):
            errors.append(f"query_guards.product_type_detection[{index}] requires when_contains and set_product_type")
        for required_index, required in enumerate(_as_list(item.get("add_required"))):
            if not isinstance(required, Mapping) or not _target_field(required):
                errors.append(
                    f"query_guards.product_type_detection[{index}].add_required[{required_index}] must target a field"
                )
    for index, item in enumerate(_as_list(query_guards.get("required_atoms"))):
        if not isinstance(item, Mapping):
            errors.append(f"query_guards.required_atoms[{index}] must be an object")
            continue
        atom = _as_mapping(item.get("atom"))
        if not _is_non_empty_string(item.get("when_contains")) or not _target_field(atom):
            errors.append(f"query_guards.required_atoms[{index}] requires when_contains and atom.field")
    for index, item in enumerate(_as_list(query_guards.get("excluded_atoms"))):
        if not isinstance(item, Mapping):
            errors.append(f"query_guards.excluded_atoms[{index}] must be an object")
            continue
        exclude = _as_mapping(item.get("exclude"))
        if not _is_non_empty_string(item.get("when_contains")) or not _target_field(exclude):
            errors.append(f"query_guards.excluded_atoms[{index}] requires when_contains and exclude.field")

    for index, item in enumerate(_as_list(sku_guards.get("characteristic_mappings"))):
        if not isinstance(item, Mapping):
            errors.append(f"sku_guards.characteristic_mappings[{index}] must be an object")
            continue
        has_target = bool(_target_field(_as_mapping(item.get("target"))))
        target_keywords = _as_list(item.get("target_keywords"))
        has_keyword_targets = bool(target_keywords)
        if not _is_non_empty_string(item.get("name_contains")):
            errors.append(f"sku_guards.characteristic_mappings[{index}].name_contains is required")
        if not has_target and not has_keyword_targets:
            errors.append(f"sku_guards.characteristic_mappings[{index}] requires target or target_keywords")
        for keyword_index, keyword in enumerate(target_keywords):
            keyword_target = _as_mapping(keyword.get("target")) if isinstance(keyword, Mapping) else {}
            if (
                not isinstance(keyword, Mapping)
                or not _is_non_empty_string(keyword.get("when_value_contains"))
                or not _target_field(keyword_target)
            ):
                errors.append(
                    f"sku_guards.characteristic_mappings[{index}].target_keywords[{keyword_index}] is malformed"
                )
    for index, item in enumerate(_as_list(sku_guards.get("functional_token_mappings"))):
        if not isinstance(item, Mapping):
            errors.append(f"sku_guards.functional_token_mappings[{index}] must be an object")
            continue
        target = _as_mapping(item.get("target"))
        if not _is_non_empty_string(item.get("when_contains")) or not _target_field(target):
            errors.append(f"sku_guards.functional_token_mappings[{index}] requires when_contains and target.field")
    return errors


def _generated_by_audit_result(payload: Mapping[str, Any]) -> tuple[str, str]:
    generated_by = payload.get("generated_by")
    if generated_by is None:
        return "skip", "generated_by absent; legacy templates must inject it during derive before persistence"
    if not isinstance(generated_by, Mapping):
        return "fail", "generated_by must be an object"

    errors: list[str] = []
    method = generated_by.get("method")
    evidence_hash = generated_by.get("evidence_hash")
    corpus_signals = _as_mapping(generated_by.get("corpus_signals"))
    if not _is_non_empty_string(method):
        errors.append("method is required")
    if not (_is_non_empty_string(evidence_hash) and str(evidence_hash).startswith("sha256:")):
        errors.append("evidence_hash must start with sha256:")
    if not isinstance(corpus_signals.get("queries_sampled"), int):
        errors.append("corpus_signals.queries_sampled is required")
    if not isinstance(corpus_signals.get("product_type_axes_count"), int):
        errors.append("corpus_signals.product_type_axes_count is required")

    diagnostics_keys = (
        "builder_diagnostics",
        "constraints_builder_diagnostics",
        "guard_builder_diagnostics",
    )
    has_builder_diagnostics = any(isinstance(generated_by.get(key), Mapping) for key in diagnostics_keys)
    if method != "skeleton_v0" and not has_builder_diagnostics:
        errors.append("builder diagnostics are required for generic generated profiles")

    return ("fail", "; ".join(errors)) if errors else ("pass", f"method={method!r}")


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

    section_errors = _operational_section_errors(payload)
    checks.append(
        CategoryProfileSelfCheckItem(
            name="operational_sections_present",
            result=_bool_result(not section_errors),
            detail="all operational sections present" if not section_errors else "; ".join(section_errors),
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

    subject_safety_errors = [*_subject_structure_errors(subject), *_product_type_alias_errors(payload, primary)]
    checks.append(
        CategoryProfileSelfCheckItem(
            name="subject_alias_safety",
            result=_bool_result(not subject_safety_errors),
            detail="subject aliases and product-type aliases are safe"
            if not subject_safety_errors
            else "; ".join(subject_safety_errors),
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
        if not _is_non_empty_string(rule.get("name")):
            syntax_errors.append(f"hard_conflicts[{index}].name is required")
        if not _is_non_empty_string(rule.get("message")):
            syntax_errors.append(f"hard_conflicts[{index}].message is required")
        when_query_has = _as_mapping(rule.get("when_query_has"))
        if not when_query_has:
            syntax_errors.append(f"hard_conflicts[{index}].when_query_has is required")
        invalid_query_keys = sorted(set(when_query_has) - _ALLOWED_QUERY_PREDICATES)
        if invalid_query_keys:
            syntax_errors.append(f"hard_conflicts[{index}].when_query_has -> {', '.join(invalid_query_keys)}")
        requirements = _as_list(rule.get("requires_sku_any"))
        if not requirements:
            syntax_errors.append(f"hard_conflicts[{index}].requires_sku_any is required")
        for requirement in requirements:
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

    constraint_structure_errors = _constraint_structure_errors(payload)
    checks.append(
        CategoryProfileSelfCheckItem(
            name="constraints_structure",
            result=_bool_result(not constraint_structure_errors),
            detail="constraints structure ok"
            if not constraint_structure_errors
            else "; ".join(constraint_structure_errors),
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

    scoring_structure_errors = _scoring_structure_errors(payload)
    checks.append(
        CategoryProfileSelfCheckItem(
            name="scoring_labels_structure",
            result=_bool_result(not scoring_structure_errors),
            detail="scoring and labels structure ok"
            if not scoring_structure_errors
            else "; ".join(scoring_structure_errors),
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

    guard_structure_errors = _guard_structure_errors(payload)
    checks.append(
        CategoryProfileSelfCheckItem(
            name="guards_structure",
            result=_bool_result(not guard_structure_errors),
            detail="guards structure ok" if not guard_structure_errors else "; ".join(guard_structure_errors),
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

    decision_sections = {
        "scoring": payload.get("scoring"),
        "user_bucket_labels": payload.get("user_bucket_labels"),
        "constraints": payload.get("constraints"),
        "hard_conflicts": payload.get("hard_conflicts"),
        "query_guards": payload.get("query_guards"),
        "sku_guards": payload.get("sku_guards"),
    }
    economic_sections = sorted(
        section for section, value in decision_sections.items() if _has_economic_decision_text(value)
    )
    checks.append(
        CategoryProfileSelfCheckItem(
            name="no_economic_decision_fields",
            result=_bool_result(not economic_sections),
            detail="no orders/conversion decision fields"
            if not economic_sections
            else f"economic decision text in: {', '.join(economic_sections)}",
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

    generated_by_result, generated_by_detail = _generated_by_audit_result(payload)
    checks.append(
        CategoryProfileSelfCheckItem(
            name="generated_by_auditability",
            result=generated_by_result,
            detail=generated_by_detail,
        )
    )

    checks.append(
        CategoryProfileSelfCheckItem(
            name="eval_smoke",
            result="skip",
            detail="No strict eval labels supplied; semantic/profile integrity checks applied",
        )
    )

    status = "failed" if any(item.result == "fail" for item in checks) else "passed"
    return CategoryProfileSelfCheckReport(status=status, checks=checks)
