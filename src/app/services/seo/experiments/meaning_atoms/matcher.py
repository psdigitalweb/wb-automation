"""Eligibility-first matcher for the meaning atoms shadow experiment."""

from __future__ import annotations

import math
from typing import Any

from app.services.seo.atoms.v1.guards import atom_label, atom_matches, canonical_value, field_family, normalize_text
from app.services.seo.atoms.v1.schemas import AtomsMatchResult, MeaningAtom, QueryAtoms, SkuAtoms


def _all_positive_sku_atoms(sku: SkuAtoms) -> list[MeaningAtom]:
    atoms = [*sku.facts, *sku.positive_atoms]
    if sku.product_type:
        atoms.append(
            MeaningAtom(
                type="product_type",
                field="product_type",
                value=sku.product_type,
                source="sku_atoms",
                confidence=0.9,
            )
        )
    return atoms


def _find_match(atom: MeaningAtom, candidates: list[MeaningAtom]) -> MeaningAtom | None:
    for candidate in candidates:
        if atom_matches(atom, candidate):
            return candidate
    return None


def _numeric_match(query_atom: MeaningAtom, candidates: list[MeaningAtom]) -> tuple[bool, str | None]:
    try:
        expected = float(query_atom.value)
    except Exception:
        return _find_match(query_atom, candidates) is not None, None
    query_field = field_family(query_atom.field)
    field_candidates = [item for item in candidates if field_family(item.field) == query_field]
    if not field_candidates:
        return False, f"missing numeric fact: {query_atom.field}={query_atom.value}"
    for candidate in field_candidates:
        try:
            actual = float(candidate.value)
        except Exception:
            continue
        if query_atom.field == "volume_ml":
            tolerance = max(50.0, expected * 0.15)
            if abs(actual - expected) <= tolerance:
                return True, None
            return False, f"numeric mismatch: requires {expected:g} {query_atom.field}, SKU has {actual:g}"
        if actual == expected:
            return True, None
        return False, f"numeric mismatch: requires {expected:g} {query_atom.field}, SKU has {actual:g}"
    return False, f"missing numeric fact: {query_atom.field}={query_atom.value}"


def _product_type_compatible(query_type: str, sku_type: str) -> bool:
    query_norm = normalize_text(query_type)
    sku_norm = normalize_text(sku_type)
    if not query_norm:
        return True
    if query_norm == sku_norm:
        return True
    if query_norm == "кружка" and "круж" in sku_norm and "термо" not in sku_norm:
        return True
    return False


def _ranking_boost(value: float | None, *, allow: bool) -> float:
    if not allow or value is None or value <= 0:
        return 0.0
    return min(0.06, math.log10(float(value) + 1.0) / 110.0)


def _is_product_only(query: QueryAtoms) -> bool:
    meaningful = [
        *query.required_atoms,
        *query.preferred_atoms,
        *query.excluded_atoms,
        *query.negative_fit_atoms,
    ]
    return not meaningful or all(atom.field == "product_type" for atom in meaningful)


def _negative_conflict(query_atom: MeaningAtom, negatives: list[MeaningAtom]) -> str | None:
    for negative in negatives:
        if atom_matches(query_atom, negative):
            return f"blocked by SKU negative fit: {atom_label(query_atom)}"
        if negative.field == "negative":
            negative_text = normalize_text(negative.value)
            value_text = canonical_value(query_atom.field, query_atom.value)
            broad_gift_values = {"подарок", "подарочная", "день рождения", "новый год", "просто так"}
            if value_text in broad_gift_values and negative_text != value_text:
                continue
            if value_text in {"муж", "мужчина"} and any(marker in negative_text for marker in ("мужск", "мужчин", "для мужчины")):
                return f"blocked by SKU negative text: {value_text}"
            if value_text and value_text in negative_text:
                return f"blocked by SKU negative text: {value_text}"
    return None


def _atom_value_mentioned(atom: MeaningAtom, *, query_text: str) -> bool:
    text = normalize_text(query_text)
    raw = normalize_text(atom.value)
    canonical = canonical_value(field_family(atom.field), atom.value)
    return bool((raw and raw in text) or (canonical and canonical in text))


def _is_strict_required(atom: MeaningAtom, *, query_text: str) -> bool:
    field = field_family(atom.field)
    value = canonical_value(field, atom.value)
    text = normalize_text(query_text)
    if atom.type in {"numeric", "compatibility", "visual", "product_type"}:
        return True
    if field in {"volume_ml", "quantity", "thermal", "compatibility", "motif", "material"}:
        return True
    if atom.type == "attribute" and _atom_value_mentioned(atom, query_text=query_text):
        return value not in {"чай", "чая", "кофе", "подарок", "подарочная"}
    if field == "use_case":
        return value in {"car", "beer", "coffee_machine"} or any(marker in text for marker in ("машин", "авто", "пивн", "кофемаш"))
    if field == "recipient":
        personal = {
            "папа": ("пап", "отец", "отц"),
            "мама": ("мам",),
            "подруга": ("подруг",),
            "любимая": ("любим",),
            "сестра": ("сестр",),
            "брат": ("брат",),
            "муж": ("мужу", "мужа", "супруг"),
            "жена": ("жене", "жену", "жена", "супруга"),
            "коллега": ("коллег",),
            "дедушка": ("дедуш",),
            "бабушка": ("бабуш",),
            "любимая": ("любимая", "любимой", "любимую"),
            "любимый": ("любимый", "любимому", "любимого"),
        }
        return any(marker in text for marker in personal.get(value, ()))
    return atom.importance == "hard" and field in {"color", "feature", "design"}


def match_atoms(
    sku: SkuAtoms,
    query: QueryAtoms,
    *,
    query_text: str,
    cluster_key: str | None = None,
    ranking_value_used: float | None = None,
) -> AtomsMatchResult:
    positive_atoms = _all_positive_sku_atoms(sku)
    negative_atoms = list(sku.negative_fit_atoms)
    matched: list[str] = []
    missing: list[str] = []
    soft_missing: list[str] = []
    conflicts: list[str] = []
    reasons: list[str] = []
    required_matched_count = 0

    query_product_type = query.product_type or next(
        (str(atom.value) for atom in query.required_atoms if atom.field == "product_type"),
        "",
    )
    if query_product_type and not _product_type_compatible(query_product_type, sku.product_type):
        conflicts.append(f"product_type conflict: query requires {query_product_type}, SKU is {sku.product_type or 'unknown'}")
    elif query_product_type:
        matched.append(f"product_type:{query_product_type}")
        reasons.append(f"product_type matched: {query_product_type}")

    for atom in query.required_atoms:
        if atom.field == "product_type":
            continue
        negative = _negative_conflict(atom, negative_atoms)
        if negative:
            conflicts.append(negative)
            continue
        if atom.type == "numeric":
            ok, reason = _numeric_match(atom, positive_atoms)
            if ok:
                required_matched_count += 1
                matched.append(atom_label(atom))
                reasons.append(f"required matched: {atom_label(atom)}")
            else:
                message = reason or f"missing required: {atom_label(atom)}"
                if _is_strict_required(atom, query_text=query_text):
                    missing.append(message)
                else:
                    soft_missing.append(message)
            continue
        found = _find_match(atom, positive_atoms)
        if found is not None:
            required_matched_count += 1
            matched.append(atom_label(atom))
            reasons.append(f"required matched: {atom_label(atom)}")
        else:
            message = f"missing required: {atom_label(atom)}"
            if _is_strict_required(atom, query_text=query_text):
                missing.append(message)
            else:
                soft_missing.append(message)

    for atom in query.excluded_atoms:
        found = _find_match(atom, positive_atoms)
        if found is not None:
            conflicts.append(f"excluded conflicts with SKU fact: {atom_label(atom)}")
        else:
            reasons.append(f"excluded atom absent: {atom_label(atom)}")

    preferred_matches = 0
    for atom in query.preferred_atoms:
        negative = _negative_conflict(atom, negative_atoms)
        if negative:
            conflicts.append(negative)
            continue
        found = _find_match(atom, positive_atoms)
        if found is not None:
            preferred_matches += 1
            matched.append(atom_label(atom))
            reasons.append(f"preferred matched: {atom_label(atom)}")

    hard_missing = [item for item in missing if item]
    hard_conflicts = [item for item in conflicts if item]
    product_only = _is_product_only(query)
    frequency = _ranking_boost(ranking_value_used, allow=not hard_conflicts and not hard_missing and not product_only)
    required_total = max(1, len([atom for atom in query.required_atoms if atom.field != "product_type"]))
    required_score = 0.25 * min(1.0, required_matched_count / required_total) if query.required_atoms else 0.0
    preferred_score = min(0.42, 0.35 * preferred_matches)
    product_score = 0.22 if query_product_type and not hard_conflicts else 0.0
    specificity = 0.06 if query.genericness == "specific" and not product_only else 0.0
    conflict_penalty = 0.7 if hard_conflicts else 0.0
    missing_penalty = 0.45 if hard_missing else 0.0
    soft_missing_penalty = min(0.18, 0.06 * len(soft_missing))
    score = max(
        0.0,
        min(
            1.0,
            product_score
            + required_score
            + preferred_score
            + specificity
            + frequency
            - conflict_penalty
            - missing_penalty
            - soft_missing_penalty,
        ),
    )
    score = round(score, 4)

    if hard_conflicts:
        bucket = "rejected"
        reasons.append("bucket capped: hard conflict")
    elif hard_missing:
        bucket = "rejected"
        reasons.append("bucket capped: missing hard requirement")
    elif product_only or query.genericness == "generic":
        bucket = "broad"
        reasons.append("bucket capped: product-only/generic query")
    elif soft_missing and not preferred_matches:
        bucket = "secondary" if score >= 0.32 else "broad"
        reasons.append("bucket capped: missing soft requirement")
    elif score >= 0.52 and required_matched_count >= 2:
        bucket = "primary"
    elif score >= 0.58 and (preferred_matches or required_matched_count):
        bucket = "primary"
    elif score >= 0.32:
        bucket = "secondary"
    else:
        bucket = "broad"

    if frequency:
        reasons.append("frequency used as tie-breaker after eligibility")
    if soft_missing:
        reasons.append("soft missing requirements did not hard reject")

    return AtomsMatchResult(
        query=query_text,
        cluster_key=cluster_key,
        bucket=bucket,  # type: ignore[arg-type]
        score=score,
        ranking_value_used=ranking_value_used,
        matched_atoms=sorted(set(matched)),
        missing_atoms=sorted(set([*hard_missing, *soft_missing])),
        conflict_atoms=sorted(set(hard_conflicts)),
        reasons=reasons,
        score_components={
            "product_score": round(product_score, 4),
            "required_score": round(required_score, 4),
            "preferred_score": round(preferred_score, 4),
            "specificity": round(specificity, 4),
            "frequency": round(frequency, 4),
            "conflict_penalty": round(conflict_penalty, 4),
            "missing_penalty": round(missing_penalty, 4),
            "soft_missing_penalty": round(soft_missing_penalty, 4),
        },
    )
