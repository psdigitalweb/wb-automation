"""Typed Atoms v1 normalizer and matcher for the shadow experiment."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.seo.atoms.v1.guards import atom_matches, canonical_value, field_family, normalize_text
from app.services.seo.atoms.v1.schemas import AtomsMatchResult, MeaningAtom, QueryAtoms, SkuAtoms


ATOMS_V1_SCHEMA_VERSION = "atoms_v1"
ATOMS_MATCHER_V1_VERSION = "atoms_matcher_v1_2_candidate"
_ALLOWED_LEGACY_TYPES = {
    "product_type",
    "attribute",
    "numeric",
    "visual",
    "recipient",
    "occasion",
    "use_case",
    "compatibility",
    "expressive",
    "exclusion",
}
_ALLOWED_LEGACY_OPERATORS = {"equals", "close_to", "contains", "excludes", "compatible_with"}

AtomRoleV1 = Literal[
    "hard_fact",
    "hard_requirement",
    "soft_signal",
    "audience_hypothesis",
    "negative_intent",
    "unsupported_if_missing",
    "unknown",
]
AtomPolarityV1 = Literal["positive", "negative", "exclusion"]
EvidenceTypeV1 = Literal[
    "product_data",
    "review",
    "vision",
    "query_llm",
    "deterministic_guard",
    "sku_meaning",
    "query_meaning",
    "unknown",
]


class MeaningAtomV1(BaseModel):
    type: str
    field: str
    value: Any
    operator: str = "equals"
    role: AtomRoleV1
    polarity: AtomPolarityV1 = "positive"
    evidence_type: EvidenceTypeV1 = "unknown"
    evidence_ref: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_version: str | None = None


class SkuAtomsV1(BaseModel):
    schema_version: str = "sku_atoms_v1"
    project_id: int | None = None
    category_id: int | None = None
    nm_id: int | None = None
    product_type: str = ""
    product_identity: str = ""
    hard_facts: list[MeaningAtomV1] = Field(default_factory=list)
    soft_signals: list[MeaningAtomV1] = Field(default_factory=list)
    audience_hypotheses: list[MeaningAtomV1] = Field(default_factory=list)
    negative_intents: list[MeaningAtomV1] = Field(default_factory=list)
    unknowns: list[MeaningAtomV1] = Field(default_factory=list)
    source_summary: dict[str, Any] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)


class QueryAtomsV1(BaseModel):
    schema_version: str = "query_atoms_v1"
    cluster_key: str | None = None
    query: str | None = None
    product_type: str = ""
    required_atoms: list[MeaningAtomV1] = Field(default_factory=list)
    preferred_atoms: list[MeaningAtomV1] = Field(default_factory=list)
    excluded_atoms: list[MeaningAtomV1] = Field(default_factory=list)
    generic_context_atoms: list[MeaningAtomV1] = Field(default_factory=list)
    genericness: str = "specific"
    confidence: dict[str, float] = Field(default_factory=dict)


def _evidence_type(source: str) -> EvidenceTypeV1:
    source_norm = normalize_text(source)
    if "vision" in source_norm:
        return "vision"
    if "product_characteristics" in source_norm:
        return "product_data"
    if "deterministic_guard" in source_norm:
        return "deterministic_guard"
    if "sku_meaning" in source_norm:
        return "sku_meaning"
    if "query_meaning" in source_norm:
        return "query_meaning"
    if "llm" in source_norm:
        return "query_llm"
    return "unknown"


def _legacy_atom(atom: MeaningAtomV1) -> MeaningAtom:
    atom_type = atom.type if atom.type in _ALLOWED_LEGACY_TYPES else "attribute"
    operator = atom.operator if atom.operator in _ALLOWED_LEGACY_OPERATORS else "equals"
    return MeaningAtom(
        type=atom_type,  # type: ignore[arg-type]
        field=atom.field,
        value=atom.value,
        operator=operator,  # type: ignore[arg-type]
        importance="hard" if atom.role in {"hard_fact", "hard_requirement"} else "soft",
        source=atom.evidence_type,
        confidence=atom.confidence,
    )


def _atom_label(atom: MeaningAtomV1) -> str:
    family = field_family(atom.field)
    value = canonical_value(family, atom.value)
    return f"{atom.role}:{atom.type}:{family}:{value}"


def _atoms_match(left: MeaningAtomV1, right: MeaningAtomV1) -> bool:
    return atom_matches(_legacy_atom(left), _legacy_atom(right))


def _append_unique(items: list[MeaningAtomV1], atom: MeaningAtomV1) -> None:
    if any(existing.role == atom.role and existing.polarity == atom.polarity and _atoms_match(existing, atom) for existing in items):
        return
    items.append(atom)


def _atom_v1(
    atom: MeaningAtom,
    *,
    role: AtomRoleV1,
    polarity: AtomPolarityV1 = "positive",
    source_version: str | None = None,
) -> MeaningAtomV1:
    return MeaningAtomV1(
        type=str(atom.type),
        field=field_family(atom.field),
        value=atom.value,
        operator=str(atom.operator),
        role=role,
        polarity=polarity,
        evidence_type=_evidence_type(atom.source),
        confidence=float(atom.confidence),
        source_version=source_version or atom.source,
    )


def _is_broad_audience(atom: MeaningAtomV1) -> bool:
    if field_family(atom.field) != "recipient":
        return False
    value = canonical_value("recipient", atom.value)
    return value in {"женщина", "мужчина", "девочка", "девушка", "подростки"}


def _query_value_mentioned(atom: MeaningAtomV1, query_text: str) -> bool:
    text = normalize_text(query_text)
    field = field_family(atom.field)
    raw = normalize_text(atom.value)
    canonical = canonical_value(field, atom.value)
    if raw and raw in text:
        return True
    if canonical and canonical in text:
        return True
    color_markers = {
        "белый": ("бел", "white"),
        "черный": ("черн", "black"),
        "красный": ("красн", "red"),
        "синий": ("син", "blue"),
        "голубой": ("голуб", "light blue", "light_blue"),
        "розовый": ("розов", "pink"),
        "зеленый": ("зелен", "green"),
        "желтый": ("желт", "yellow"),
        "фиолетовый": ("фиолет", "purple"),
    }
    expressive_markers = {
        "милая": ("мил", "милаш", "няш", "cute", "adorable"),
        "красивая": ("красив", "эстет", "пинтерест", "pinterest", "стильн"),
        "уютная": ("уют", "cozy"),
        "смешная": ("смешн", "прикол", "funny", "meme"),
        "праздничная": ("праздн", "новогод", "holiday", "festive"),
    }
    if field == "color" and any(marker in text for marker in color_markers.get(canonical, ())):
        return True
    if field == "expressive" and any(marker in text for marker in expressive_markers.get(canonical, ())):
        return True
    recipient_markers = {
        "папа": ("пап", "отец", "отц"),
        "мама": ("мам",),
        "подруга": ("подруг",),
        "любимая": ("любимая", "любимой", "любимую"),
        "любимый": ("любимый", "любимому", "любимого"),
        "сестра": ("сестр",),
        "брат": ("брат",),
        "муж": ("мужу", "мужа", "супруг"),
        "мужчина": ("мужчин", "мужск"),
        "жена": ("жене", "жену", "супруга"),
        "женщина": ("женщ", "женск"),
        "коллега": ("коллег",),
        "дедушка": ("дедуш",),
        "бабушка": ("бабуш",),
    }
    return any(marker in text for marker in recipient_markers.get(canonical, ()))


def _is_strict_query_requirement(atom: MeaningAtomV1, *, query_text: str) -> bool:
    field = field_family(atom.field)
    value = canonical_value(field, atom.value)
    text = normalize_text(query_text)
    soft_values = {"чай", "чая", "кофе", "подарок", "подарочная", "подарочная упаковка", "день рождения", "новый год", "8 марта", "просто так"}
    if field in {"color", "occasion"}:
        return False
    if field == "quantity":
        return bool(re.search(r"\b\d{1,2}\s*(?:шт|штук|предмет)", text)) or any(marker in text for marker in ("набор", "комплект"))
    if field == "volume_ml":
        if str(atom.value) == "1000" and re.search(r"\b(?:литровая|литровый|литровые|литр|1\s*л)\b", text):
            return True
        return bool(re.search(rf"\b{re.escape(str(atom.value))}\s*(?:мл|ml)\b", text))
    if atom.type in {"compatibility", "visual", "product_type"}:
        return True
    if atom.type == "numeric":
        return _query_value_mentioned(atom, query_text)
    if field in {"thermal", "compatibility", "motif", "material", "transparency"}:
        return True
    if field in {"design", "feature"} and _query_value_mentioned(atom, query_text):
        return True
    if atom.type == "attribute" and _query_value_mentioned(atom, query_text):
        return value not in soft_values
    if field == "use_case":
        return value in {"car", "beer", "coffee_machine"} or any(marker in text for marker in ("машин", "авто", "пивн", "кофемаш"))
    if field == "recipient":
        personal = {"папа", "мама", "подруга", "любимая", "любимый", "сестра", "брат", "муж", "мужчина", "жена", "коллега", "дедушка", "бабушка"}
        return value in personal and _query_value_mentioned(atom, query_text)
    return False


def _explicit_accessory_product_type(query_text: str) -> str | None:
    text = normalize_text(query_text)
    accessory_patterns = (
        ("крышка", ("крышка", "крышку", "крышки", "крышечка", "крышечку")),
        ("ситечко", ("сеточка", "ситечко", "сито", "фильтр")),
        ("ложка", ("ложка", "ложку", "ложечки")),
        ("подставка", ("подставка", "подставку", "подставки")),
    )
    for product_type, markers in accessory_patterns:
        if any(text.startswith(marker + " ") or f" {marker} " in f" {text} " for marker in markers):
            return product_type
    return None


def normalize_sku_atoms_v1(sku: SkuAtoms) -> SkuAtomsV1:
    result = SkuAtomsV1(
        project_id=sku.project_id,
        category_id=sku.category_id,
        nm_id=sku.nm_id,
        product_type=sku.product_type,
        product_identity=sku.product_identity,
        confidence=dict(sku.confidence or {}),
    )
    if sku.product_type:
        _append_unique(
            result.hard_facts,
            MeaningAtomV1(
                type="product_type",
                field="product_type",
                value=sku.product_type,
                role="hard_fact",
                evidence_type="sku_meaning",
                confidence=0.9,
                source_version="sku_atoms_v0",
            ),
        )
    for atom in sku.facts:
        role: AtomRoleV1 = "hard_fact"
        if _evidence_type(atom.source) == "vision" and field_family(atom.field) in {"recipient", "occasion", "expressive", "query_intent"}:
            role = "soft_signal"
        _append_unique(result.hard_facts if role == "hard_fact" else result.soft_signals, _atom_v1(atom, role=role, source_version="sku_atoms_v0"))
    for atom in sku.positive_atoms:
        evidence = _evidence_type(atom.source)
        field = field_family(atom.field)
        if field == "recipient" and evidence == "vision":
            target = result.audience_hypotheses
            role = "audience_hypothesis"
        elif field == "recipient" and evidence != "product_data":
            target = result.audience_hypotheses
            role = "audience_hypothesis"
        else:
            target = result.soft_signals
            role = "soft_signal"
        _append_unique(target, _atom_v1(atom, role=role, source_version="sku_atoms_v0"))
    for atom in sku.negative_fit_atoms:
        _append_unique(result.negative_intents, _atom_v1(atom, role="negative_intent", polarity="negative", source_version="sku_atoms_v0"))
    result.source_summary = {
        "hard_facts": len(result.hard_facts),
        "soft_signals": len(result.soft_signals),
        "audience_hypotheses": len(result.audience_hypotheses),
        "negative_intents": len(result.negative_intents),
    }
    return result


def normalize_query_atoms_v1(query: QueryAtoms, *, query_text: str) -> QueryAtomsV1:
    explicit_accessory = _explicit_accessory_product_type(query_text)
    result = QueryAtomsV1(
        cluster_key=query.cluster_key,
        query=query.query or query_text,
        product_type=explicit_accessory or query.product_type,
        genericness=query.genericness,
        confidence=dict(query.confidence or {}),
    )
    if result.product_type:
        _append_unique(
            result.required_atoms,
            MeaningAtomV1(
                type="product_type",
                field="product_type",
                value=result.product_type,
                role="hard_requirement",
                evidence_type="deterministic_guard" if explicit_accessory else "query_meaning",
                confidence=0.9,
                source_version="atoms_v1_1_accessory_guard" if explicit_accessory else "query_atoms_v0",
            ),
        )
    for atom in query.required_atoms:
        candidate = _atom_v1(atom, role="hard_requirement", source_version="query_atoms_v0")
        if candidate.field == "product_type":
            _append_unique(result.required_atoms, candidate)
            continue
        explicit_broad_audience = (
            candidate.evidence_type == "deterministic_guard"
            and field_family(candidate.field) == "recipient"
            and _query_value_mentioned(candidate, query_text)
        )
        if (_is_broad_audience(candidate) and not explicit_broad_audience) or not _is_strict_query_requirement(candidate, query_text=query_text):
            candidate.role = "soft_signal"
            _append_unique(result.preferred_atoms, candidate)
        else:
            _append_unique(result.required_atoms, candidate)
    for atom in query.preferred_atoms:
        candidate = _atom_v1(atom, role="soft_signal", source_version="query_atoms_v0")
        if field_family(candidate.field) == "recipient":
            candidate.role = "audience_hypothesis"
        _append_unique(result.preferred_atoms, candidate)
    for atom in query.excluded_atoms:
        _append_unique(result.excluded_atoms, _atom_v1(atom, role="hard_requirement", polarity="exclusion", source_version="query_atoms_v0"))
    for atom in query.negative_fit_atoms:
        _append_unique(result.generic_context_atoms, _atom_v1(atom, role="negative_intent", polarity="negative", source_version="query_atoms_v0"))
    return result


def _all_sku_positive_atoms(sku: SkuAtomsV1) -> list[MeaningAtomV1]:
    return [*sku.hard_facts, *sku.soft_signals, *sku.audience_hypotheses]


def _find_match(atom: MeaningAtomV1, candidates: list[MeaningAtomV1]) -> MeaningAtomV1 | None:
    for candidate in candidates:
        if _atoms_match(atom, candidate):
            return candidate
    return None


def _product_type_compatible(query_type: str, sku_type: str) -> bool:
    query_norm = normalize_text(query_type)
    sku_norm = normalize_text(sku_type)
    if not query_norm:
        return True
    if query_norm == sku_norm:
        return True
    if query_norm in {"кружка", "кружки"} and "круж" in sku_norm and "термо" not in sku_norm:
        return True
    return False


def _default_product_type_compatibility_reason(query_type: str, sku_type: str) -> str | None:
    if _product_type_compatible(query_type, sku_type):
        return f"product_type matched: {normalize_text(query_type)}"
    return None


def _numeric_match(query_atom: MeaningAtomV1, candidates: list[MeaningAtomV1]) -> tuple[bool, str | None]:
    try:
        expected = float(query_atom.value)
    except Exception:
        return _find_match(query_atom, candidates) is not None, None
    field_candidates = [item for item in candidates if field_family(item.field) == field_family(query_atom.field)]
    if not field_candidates:
        return False, f"missing numeric fact: {query_atom.field}={query_atom.value}"
    for candidate in field_candidates:
        try:
            actual = float(candidate.value)
        except Exception:
            continue
        if field_family(query_atom.field) == "volume_ml":
            tolerance = max(50.0, expected * 0.15)
            if abs(actual - expected) <= tolerance:
                return True, None
            return False, f"numeric mismatch: requires {expected:g} {query_atom.field}, SKU has {actual:g}"
        if actual == expected:
            return True, None
        return False, f"numeric mismatch: requires {expected:g} {query_atom.field}, SKU has {actual:g}"
    return False, f"missing numeric fact: {query_atom.field}={query_atom.value}"


def _negative_intent_conflict(query_atom: MeaningAtomV1, negatives: list[MeaningAtomV1]) -> str | None:
    query_field = field_family(query_atom.field)
    query_value = canonical_value(query_field, query_atom.value)
    for negative in negatives:
        negative_text = normalize_text(negative.value)
        if _atoms_match(query_atom, negative):
            return f"blocked by negative intent: {_atom_label(query_atom)}"
        if "без рисун" in negative_text and query_field == "design" and query_value == "print":
            return "blocked by negative intent: no_print"
        if "без рисун" in negative_text and query_atom.polarity == "exclusion" and query_value == "print":
            return "blocked by negative intent: no_print"
        if "прозрач" in negative_text and "прозрач" in normalize_text(query_atom.value):
            return "blocked by negative intent: transparent"
        if ("мужск" in negative_text or "мужчин" in negative_text or "для мужчины" in negative_text) and query_field == "recipient":
            if query_value in {"муж", "мужчина", "папа", "дедушка"}:
                return f"blocked by negative intent: male_recipient:{query_value}"
        if "строг" in negative_text and query_field == "expressive" and "строг" in normalize_text(query_atom.value):
            return "blocked by negative intent: strict_style"
    return None


def _ranking_boost(value: float | None, *, allow: bool) -> float:
    if not allow or value is None or value <= 0:
        return 0.0
    return min(0.05, math.log10(float(value) + 1.0) / 120.0)


def _is_product_only(query: QueryAtomsV1) -> bool:
    meaningful = [
        *[atom for atom in query.required_atoms if field_family(atom.field) != "product_type"],
        *query.preferred_atoms,
        *query.excluded_atoms,
    ]
    return not meaningful


def _is_low_signal_atom(atom: MeaningAtomV1) -> bool:
    field = field_family(atom.field)
    value = canonical_value(field, atom.value)
    if field in {"color", "use_case", "occasion"}:
        return True
    if field == "attribute" and value in {"чай", "чая", "для чая", "кофе", "для кофе", "кружка"}:
        return True
    if field in {"buyer_intent", "attributes"}:
        return True
    if field == "expressive" and value in {"подарочная"}:
        return True
    return False


def _low_signal_bucket(query: QueryAtomsV1) -> str:
    required = [atom for atom in query.required_atoms if field_family(atom.field) != "product_type"]
    meaningful = [*required, *query.preferred_atoms, *query.excluded_atoms]
    values = {canonical_value(field_family(atom.field), atom.value) for atom in meaningful}
    fields = {field_family(atom.field) for atom in meaningful}
    if fields <= {"attribute", "use_case"} and values & {"чай", "чая", "для чая", "кофе", "для кофе", "кружка"}:
        return "broad"
    return "rejected"


def _is_low_signal_only(query: QueryAtomsV1) -> bool:
    required = [atom for atom in query.required_atoms if field_family(atom.field) != "product_type"]
    meaningful = [*required, *query.preferred_atoms, *query.excluded_atoms]
    return bool(meaningful) and all(_is_low_signal_atom(atom) for atom in meaningful)


def match_atoms_v1(
    sku: SkuAtoms | SkuAtomsV1,
    query: QueryAtoms | QueryAtomsV1,
    *,
    query_text: str,
    cluster_key: str | None = None,
    ranking_value_used: float | None = None,
    product_type_compatibility_reason: Callable[[str, str], str | None] | None = None,
) -> AtomsMatchResult:
    sku_v1 = normalize_sku_atoms_v1(sku) if isinstance(sku, SkuAtoms) else sku
    query_v1 = normalize_query_atoms_v1(query, query_text=query_text) if isinstance(query, QueryAtoms) else query
    positive = _all_sku_positive_atoms(sku_v1)
    negatives = list(sku_v1.negative_intents)
    matched: list[str] = []
    missing_hard: list[str] = []
    missing_soft: list[str] = []
    conflicts: list[str] = []
    reasons: list[str] = []
    required_matched = 0
    required_strong_matches = 0
    preferred_matches = 0
    audience_matches = 0
    strong_signal_matches = 0

    compatibility_reason = product_type_compatibility_reason or _default_product_type_compatibility_reason
    query_product_type = query_v1.product_type or next((str(atom.value) for atom in query_v1.required_atoms if field_family(atom.field) == "product_type"), "")
    product_type_reason = compatibility_reason(query_product_type, sku_v1.product_type) if query_product_type else None
    if query_product_type and product_type_reason is None:
        conflicts.append(f"product_type conflict: query requires {query_product_type}, SKU is {sku_v1.product_type or 'unknown'}")
    elif query_product_type:
        matched.append(f"product_type:{query_product_type}")
        reasons.append(product_type_reason or f"product_type matched: {query_product_type}")

    for atom in query_v1.required_atoms:
        if field_family(atom.field) == "product_type":
            continue
        negative = _negative_intent_conflict(atom, negatives)
        if negative:
            conflicts.append(negative)
            continue
        if atom.type == "numeric":
            ok, reason = _numeric_match(atom, positive)
            if ok:
                required_matched += 1
                matched.append(_atom_label(atom))
                reasons.append(f"required matched: {_atom_label(atom)}")
            else:
                missing_hard.append(reason or f"missing hard requirement: {_atom_label(atom)}")
            continue
        found = _find_match(atom, positive)
        if found:
            required_matched += 1
            field = field_family(atom.field)
            if field in {"motif", "design", "packaging", "color", "material", "transparency"} or atom.type in {
                "visual",
                "compatibility",
            }:
                required_strong_matches += 1
                strong_signal_matches += 1
            matched.append(_atom_label(atom))
            reasons.append(f"required matched: {_atom_label(atom)}")
        else:
            missing_hard.append(f"missing hard requirement: {_atom_label(atom)}")

    for atom in query_v1.excluded_atoms:
        found = _find_match(atom, positive)
        if found:
            conflicts.append(f"exclusion conflicts with SKU fact: {_atom_label(atom)}")
        else:
            reasons.append(f"excluded atom absent: {_atom_label(atom)}")

    for atom in query_v1.preferred_atoms:
        negative = _negative_intent_conflict(atom, negatives)
        if negative and atom.role == "audience_hypothesis":
            missing_soft.append(negative)
            continue
        if negative:
            conflicts.append(negative)
            continue
        found = _find_match(atom, positive)
        if found:
            field = field_family(atom.field)
            variant_audience = field == "recipient" and not _query_value_mentioned(atom, query_text)
            if variant_audience:
                matched.append(_atom_label(atom))
                reasons.append(f"variant audience matched but not used for primary: {_atom_label(atom)}")
                continue
            preferred_matches += 1
            if atom.role == "audience_hypothesis" or field == "recipient":
                if not _is_broad_audience(atom):
                    audience_matches += 1
                    strong_signal_matches += 1
            if field in {"expressive", "motif", "packaging"}:
                strong_signal_matches += 1
            matched.append(_atom_label(atom))
            reasons.append(f"preferred matched: {_atom_label(atom)}")
        elif atom.role == "audience_hypothesis":
            missing_soft.append(f"missing audience hypothesis: {_atom_label(atom)}")

    product_only = _is_product_only(query_v1) or query_v1.genericness == "generic"
    low_signal_only = _is_low_signal_only(query_v1)
    hard_conflicts = [item for item in conflicts if item]
    hard_missing = [item for item in missing_hard if item]
    allow_frequency = not hard_conflicts and not hard_missing and not product_only
    frequency = _ranking_boost(ranking_value_used, allow=allow_frequency)
    required_total = max(1, len([atom for atom in query_v1.required_atoms if field_family(atom.field) != "product_type"]))
    product_score = 0.22 if query_product_type and not hard_conflicts else 0.0
    required_score = 0.25 * min(1.0, required_matched / required_total) if query_v1.required_atoms else 0.0
    required_strong_score = 0.47 if required_strong_matches else 0.0
    preferred_score = min(0.46, 0.27 * preferred_matches)
    audience_score = min(0.14, 0.08 * audience_matches)
    specificity = 0.06 if query_v1.genericness == "specific" and not product_only else 0.0
    conflict_penalty = 0.7 if hard_conflicts else 0.0
    missing_penalty = 0.45 if hard_missing else 0.0
    soft_missing_penalty = min(0.12, 0.04 * len(missing_soft))
    score = round(
        max(
            0.0,
            min(
                1.0,
                product_score
                + required_score
                + required_strong_score
                + preferred_score
                + audience_score
                + specificity
                + frequency
                - conflict_penalty
                - missing_penalty
                - soft_missing_penalty,
            ),
        ),
        4,
    )

    if hard_conflicts:
        bucket = "rejected"
        reasons.append("bucket capped: hard conflict")
    elif hard_missing:
        bucket = "rejected"
        reasons.append("bucket capped: missing hard requirement")
    elif product_only:
        bucket = "broad"
        reasons.append("bucket capped: product-only/generic query")
    elif low_signal_only and not required_matched and not strong_signal_matches:
        bucket = _low_signal_bucket(query_v1)
        reasons.append("bucket capped: low-signal-only query")
    elif required_matched and score >= 0.52:
        bucket = "primary"
    elif score >= 0.56 and strong_signal_matches:
        bucket = "primary"
    elif score >= 0.34:
        bucket = "secondary"
    else:
        bucket = "broad"

    if frequency:
        reasons.append("frequency used as tie-breaker after eligibility")
    if missing_soft:
        reasons.append("soft/audience misses did not hard reject")

    return AtomsMatchResult(
        query=query_text,
        cluster_key=cluster_key,
        bucket=bucket,  # type: ignore[arg-type]
        score=score,
        ranking_value_used=ranking_value_used,
        matched_atoms=sorted(set(matched)),
        missing_atoms=sorted(set([*hard_missing, *missing_soft])),
        conflict_atoms=sorted(set(hard_conflicts)),
        reasons=reasons,
        score_components={
            "product_score": round(product_score, 4),
            "required_score": round(required_score, 4),
            "required_strong_score": round(required_strong_score, 4),
            "preferred_score": round(preferred_score, 4),
            "audience_score": round(audience_score, 4),
            "specificity": round(specificity, 4),
            "frequency": round(frequency, 4),
            "conflict_penalty": round(conflict_penalty, 4),
            "missing_penalty": round(missing_penalty, 4),
            "soft_missing_penalty": round(soft_missing_penalty, 4),
        },
    )
