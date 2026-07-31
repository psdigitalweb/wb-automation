"""Deterministic guardrails for meaning atoms extraction.

The LLM owns semantic interpretation. Guards only normalize explicit facts that
are visible in the text or structured product evidence.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from app.services.seo.atoms.v1.schemas import MeaningAtom, QueryAtoms, SkuAtoms
from app.services.seo.category_profile import CategoryProfile
from app.services.seo.query_meaning_matcher.canonical import listify
from app.services.seo.visual_motifs import canonicalize_motif_value, extract_visual_motifs


_VOLUME_RE = re.compile(r"(?P<value>\d{2,4})\s*(?:мл|ml)\b", re.IGNORECASE)
_QUANTITY_RE = re.compile(r"(?P<value>\d{1,2})\s*(?:шт|штук|предмет)", re.IGNORECASE)
_WORD_RE = re.compile(r"[0-9a-zA-Zа-яА-ЯёЁ]+", re.IGNORECASE)

_RECIPIENTS = {
    "пап": "папа",
    "отец": "папа",
    "отц": "папа",
    "мам": "мама",
    "подруг": "подруга",
    "сестр": "сестра",
    "брат": "брат",
    "мужчин": "мужчина",
    "мужу": "муж",
    "мужа": "муж",
    "супруг": "муж",
    "жене": "жена",
    "жену": "жена",
    "жена": "жена",
    "супруга": "жена",
    "коллег": "коллега",
    "девуш": "девушка",
    "парн": "парень",
    "дедуш": "дедушка",
    "бабуш": "бабушка",
}

_EXPRESSIVE = {
    "милая": ("мил", "милаш", "няш", "cute", "adorable", "sweet"),
    "красивая": ("красив", "эстет", "пинтерест", "pinterest", "стильн", "aesthetic", "pretty", "beautiful"),
    "уютная": ("уют", "cozy", "cosy"),
    "смешная": ("смешн", "прикол", "funny", "meme"),
    "праздничная": ("праздн", "новогод", "new year", "holiday", "festive"),
}

_CUTE_EXACT = {"милая", "милый", "милые", "милую", "милого", "милота", "няшная", "няшный", "няшные", "cute", "adorable", "sweet"}


def _has_expressive_marker(text: str, canonical: str, markers: Iterable[str]) -> bool:
    text_tokens = tokens(text)
    if canonical == "милая":
        return bool(text_tokens & _CUTE_EXACT) or any(token.startswith("милаш") for token in text_tokens)
    return any(any(token.startswith(marker) for marker in markers) for token in text_tokens) or any(
        " " in marker and marker in text for marker in markers
    )

_COLORS = {
    "бел": "белый",
    "white": "белый",
    "черн": "черный",
    "black": "черный",
    "красн": "красный",
    "red": "красный",
    "син": "синий",
    "blue": "синий",
    "голуб": "голубой",
    "light_blue": "голубой",
    "light blue": "голубой",
    "розов": "розовый",
    "pink": "розовый",
    "зелен": "зеленый",
    "green": "зеленый",
    "желт": "желтый",
    "yellow": "желтый",
    "фиолет": "фиолетовый",
    "purple": "фиолетовый",
    "beige": "бежевый",
    "cream": "кремовый",
}


def normalize_text(value: Any) -> str:
    return str(value or "").lower().replace("ё", "е")


def tokens(value: Any) -> set[str]:
    return {item.lower().replace("ё", "е") for item in _WORD_RE.findall(str(value or ""))}


def canonical_value(field: str, value: Any) -> str:
    text = normalize_text(value).strip()
    if field in {"recipient", "audience"}:
        if "женск" in text or "женщ" in text:
            return "женщина"
        if "мужск" in text or "мужчин" in text:
            return "мужчина"
        if any(marker in text for marker in ("любимому", "любимого", "любимый")):
            return "любимый"
        if any(marker in text for marker in ("любимой", "любимая", "любимую")):
            return "любимая"
        if "девоч" in text:
            return "девочка"
        if "подрост" in text:
            return "подростки"
        for marker, canonical in _RECIPIENTS.items():
            if text.startswith(marker) or marker in text:
                return canonical
    if field in {"expressive", "style"}:
        for canonical, markers in _EXPRESSIVE.items():
            if _has_expressive_marker(text, canonical, markers):
                return canonical
    if field == "color":
        for marker, canonical in _COLORS.items():
            if text.startswith(marker) or marker in text:
                return canonical
    if field == "design" and text in {"has_print", "print", "рисунок", "принт"}:
        return "print"
    if field == "motif":
        canonical_motif = canonicalize_motif_value(text)
        if canonical_motif:
            return canonical_motif
    if field == "motif" and any(marker in text for marker in ("new year", "holiday", "новогод", "праздн")):
        return "новый год"
    if field == "packaging" and any(marker in text for marker in ("gift", "box", "короб", "упаков")):
        return "подарочная упаковка"
    return text


def _recipient_values_from_text(text: str) -> list[str]:
    recipients: list[str] = []

    def add(value: str) -> None:
        if value not in recipients:
            recipients.append(value)

    # Explicit roles are stronger than broad "любим*" wording.
    for marker, canonical in _RECIPIENTS.items():
        if marker in text:
            add(canonical)
    if any(marker in text for marker in ("любимому", "любимого", "любимый")):
        add("любимый")
    if any(marker in text for marker in ("любимой", "любимая", "любимую")):
        add("любимая")
    return recipients


def field_family(field: str) -> str:
    normalized = normalize_text(field)
    if normalized in {"recipient", "audience", "gift_recipient"}:
        return "recipient"
    if normalized in {"expressive", "style", "styles", "vibe", "vibes", "emotion", "emotions"}:
        return "expressive"
    if normalized in {"use_case", "beverage", "beverage_type", "context"}:
        return "use_case"
    if normalized in {"package", "packaging", "gift_box", "box"}:
        return "packaging"
    if normalized in {"volume", "volume_ml", "capacity_ml"}:
        return "volume_ml"
    if normalized in {"qty", "quantity", "set_quantity"}:
        return "quantity"
    return normalized


def atom_label(atom: MeaningAtom) -> str:
    family = field_family(atom.field)
    value = canonical_value(family, atom.value)
    return f"{atom.type}:{family}:{value}"


def atoms_equivalent(left: MeaningAtom, right: MeaningAtom) -> bool:
    left_field = field_family(left.field)
    right_field = field_family(right.field)
    if left_field != right_field:
        return False
    return canonical_value(left_field, left.value) == canonical_value(right_field, right.value)


def atom_matches(left: MeaningAtom, right: MeaningAtom) -> bool:
    if atoms_equivalent(left, right):
        return True
    left_field = field_family(left.field)
    right_field = field_family(right.field)
    if left_field != right_field:
        return False
    left_value = canonical_value(left_field, left.value)
    right_value = canonical_value(right_field, right.value)
    if left_field in {"expressive", "recipient", "color", "motif"}:
        return left_value == right_value
    left_tokens = tokens(left_value)
    right_tokens = tokens(right_value)
    return bool(left_tokens and right_tokens and left_tokens & right_tokens)


def append_atom_unique(items: list[MeaningAtom], atom: MeaningAtom) -> None:
    if any(atoms_equivalent(existing, atom) and existing.type == atom.type for existing in items):
        return
    items.append(atom)


def _add_required(query: QueryAtoms, *, atom_type: str, field: str, value: Any, operator: str = "equals") -> None:
    append_atom_unique(
        query.required_atoms,
        MeaningAtom(
            type=atom_type,  # type: ignore[arg-type]
            field=field,
            value=value,
            operator=operator,  # type: ignore[arg-type]
            importance="hard",
            source="deterministic_guard",
            confidence=0.95,
        ),
    )


def _add_preferred(query: QueryAtoms, *, atom_type: str, field: str, value: Any) -> None:
    append_atom_unique(
        query.preferred_atoms,
        MeaningAtom(
            type=atom_type,  # type: ignore[arg-type]
            field=field,
            value=value,
            importance="soft",
            source="deterministic_guard",
            confidence=0.85,
        ),
    )


def _add_excluded(query: QueryAtoms, *, field: str, value: Any) -> None:
    append_atom_unique(
        query.excluded_atoms,
        MeaningAtom(
            type="exclusion",
            field=field,
            value=value,
            operator="excludes",
            importance="hard",
            source="deterministic_guard",
            confidence=0.95,
        ),
    )


def _mapping_items(value: Any) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, tuple):
        return tuple(item for item in value if isinstance(item, Mapping))
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, Mapping))
    return ()


def _contains_guard_marker(text: str, marker: Any) -> bool:
    marker_text = normalize_text(marker).strip()
    if not marker_text:
        return False
    return marker_text in text


def _add_required_from_guard(query: QueryAtoms, atom: Mapping[str, Any]) -> None:
    atom_type = str(atom.get("type") or "attribute")
    field = str(atom.get("field") or atom_type)
    operator = str(atom.get("operator") or "equals")
    _add_required(query, atom_type=atom_type, field=field, value=atom.get("value"), operator=operator)


def _apply_profile_query_guards(query: QueryAtoms, *, primary_text: str, profile: CategoryProfile | None) -> None:
    if profile is None:
        return

    query_guards = profile.query_guards
    for rule in _mapping_items(query_guards.get("product_type_detection")):
        if not _contains_guard_marker(primary_text, rule.get("when_contains")):
            continue
        unless_set = bool(rule.get("unless_set"))
        if not (unless_set and query.product_type):
            new_product_type = str(rule.get("set_product_type") or "").strip()
            if new_product_type:
                query.product_type = new_product_type
        for atom in _mapping_items(rule.get("add_required")):
            _add_required_from_guard(query, atom)

    for rule in _mapping_items(query_guards.get("required_atoms")):
        if _contains_guard_marker(primary_text, rule.get("when_contains")):
            atom = rule.get("atom")
            if isinstance(atom, Mapping):
                _add_required_from_guard(query, atom)

    for rule in _mapping_items(query_guards.get("excluded_atoms")):
        if _contains_guard_marker(primary_text, rule.get("when_contains")):
            atom = rule.get("exclude")
            if isinstance(atom, Mapping):
                _add_excluded(query, field=str(atom.get("field") or ""), value=atom.get("value"))


def _is_empty_characteristic_value(value_text: str) -> bool:
    return value_text.strip() in {"", "нет", "без", "none", "n/a", "null"}


def _parse_guard_target_value(*, target: Mapping[str, Any], raw_value: Any, value_text: str) -> Any | None:
    parser = normalize_text(target.get("parser"))
    if parser == "int_first":
        found = re.search(r"\d{1,4}", value_text)
        return int(found.group(0)) if found else None
    if parser == "boolean_keyword":
        truthy = {"1", "true", "yes", "y", "да", "есть", "+"}
        falsey = {"0", "false", "no", "n", "нет", "без"}
        words = tokens(value_text)
        if words & truthy:
            return target.get("value_true", target.get("value", True))
        if words & falsey:
            return target.get("value_false", target.get("value", False))
        return None
    if "value_if_any" in target:
        return None if _is_empty_characteristic_value(value_text) else target.get("value_if_any")
    if "value" in target:
        return target.get("value")
    if parser == "as_is":
        return raw_value
    return raw_value


def _add_sku_target_atom(
    sku: SkuAtoms,
    *,
    target: Mapping[str, Any],
    raw_value: Any,
    source: str,
) -> None:
    atom_type = str(target.get("type") or "attribute")
    field = str(target.get("field") or atom_type)
    value_text = normalize_text(raw_value)
    parsed_value = _parse_guard_target_value(target=target, raw_value=raw_value, value_text=value_text)
    if parsed_value is None:
        return

    if atom_type == "visual" and field == "motif":
        _add_sku_positive(sku, atom_type=atom_type, field=field, value=parsed_value, source=source)
        return
    if atom_type in {"recipient", "occasion", "expressive"}:
        _add_sku_positive(sku, atom_type=atom_type, field=field, value=parsed_value, source=source)
        return
    _add_sku_fact(sku, atom_type=atom_type, field=field, value=parsed_value, source=source)


def _apply_profile_sku_characteristics(
    sku: SkuAtoms,
    *,
    profile: CategoryProfile | None,
    characteristics: Any,
) -> None:
    if profile is None:
        return

    mappings = _mapping_items(profile.sku_guards.get("characteristic_mappings"))
    for name, raw_value in _iter_characteristics(characteristics):
        name_norm = normalize_text(name)
        values = _flatten_values(raw_value)
        for rule in mappings:
            if not _contains_guard_marker(name_norm, rule.get("name_contains")):
                continue
            for value in values:
                value_text = normalize_text(value)
                target = rule.get("target")
                if isinstance(target, Mapping):
                    _add_sku_target_atom(sku, target=target, raw_value=value, source="product_characteristics")
                for keyword_rule in _mapping_items(rule.get("target_keywords")):
                    if _contains_guard_marker(value_text, keyword_rule.get("when_value_contains")):
                        keyword_target = keyword_rule.get("target")
                        if isinstance(keyword_target, Mapping):
                            _add_sku_target_atom(sku, target=keyword_target, raw_value=value, source="product_characteristics")


def _apply_profile_sku_functional_tokens(
    sku: SkuAtoms,
    *,
    profile: CategoryProfile | None,
    meaning_payload: Mapping[str, Any],
) -> None:
    if profile is None:
        return

    functional = meaning_payload.get("functional") if isinstance(meaning_payload.get("functional"), Mapping) else {}
    mappings = _mapping_items(profile.sku_guards.get("functional_token_mappings"))
    for value in listify(functional.get("attributes")) + listify(functional.get("use_cases")):
        value_text = normalize_text(value)
        for rule in mappings:
            if _contains_guard_marker(value_text, rule.get("when_contains")):
                target = rule.get("target")
                if isinstance(target, Mapping):
                    _add_sku_target_atom(sku, target=target, raw_value=value, source="sku_meaning")


def apply_query_guards(
    query: QueryAtoms,
    query_texts: Iterable[str],
    *,
    profile: CategoryProfile | None = None,
) -> QueryAtoms:
    """Apply deterministic query-atom guards using global and profile-driven rules."""

    result = query.model_copy(deep=True)
    texts = [str(item or "") for item in query_texts if str(item or "").strip()]
    primary_text = normalize_text(texts[0] if texts else "")

    _apply_profile_query_guards(result, primary_text=primary_text, profile=profile)

    for match in _VOLUME_RE.finditer(primary_text):
        _add_required(result, atom_type="numeric", field="volume_ml", value=int(match.group("value")), operator="close_to")
    if re.search(r"\b(?:литровая|литровый|литровые|литр|1\s*л)\b", primary_text):
        _add_required(result, atom_type="numeric", field="volume_ml", value=1000, operator="close_to")

    for match in _QUANTITY_RE.finditer(primary_text):
        _add_required(result, atom_type="numeric", field="quantity", value=int(match.group("value")))
    if "набор" in primary_text or "комплект" in primary_text:
        _add_required(result, atom_type="attribute", field="quantity", value="set")

    if "прозрач" in primary_text:
        _add_required(result, atom_type="visual", field="transparency", value="transparent")
    for motif in extract_visual_motifs(primary_text):
        _add_required(result, atom_type="visual", field="motif", value=motif)
        if result.genericness in {"generic", "broad"}:
            result.genericness = "specific"

    for canonical in _recipient_values_from_text(primary_text):
        _add_required(result, atom_type="recipient", field="recipient", value=canonical)

    if "день рождения" in primary_text:
        _add_preferred(result, atom_type="occasion", field="occasion", value="день рождения")
    if "новый год" in primary_text or "новогод" in primary_text:
        _add_preferred(result, atom_type="occasion", field="occasion", value="новый год")

    for canonical, markers in _EXPRESSIVE.items():
        if _has_expressive_marker(primary_text, canonical, markers):
            _add_preferred(result, atom_type="expressive", field="expressive", value=canonical)
            if result.genericness in {"generic", "broad"}:
                result.genericness = "specific"

    for marker, canonical in _COLORS.items():
        if marker in primary_text:
            _add_preferred(result, atom_type="attribute", field="color", value=canonical)

    return result


def _iter_characteristics(characteristics: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(characteristics, list):
        for item in characteristics:
            if isinstance(item, Mapping):
                yield str(item.get("name") or item.get("key") or ""), item.get("value")
    elif isinstance(characteristics, Mapping):
        for key, value in characteristics.items():
            yield str(key), value


def _add_sku_fact(sku: SkuAtoms, *, atom_type: str, field: str, value: Any, source: str = "product_characteristics") -> None:
    append_atom_unique(
        sku.facts,
        MeaningAtom(
            type=atom_type,  # type: ignore[arg-type]
            field=field,
            value=value,
            source=source,
            confidence=0.95,
        ),
    )


def _add_sku_positive(sku: SkuAtoms, *, atom_type: str, field: str, value: Any, source: str = "sku_meaning") -> None:
    append_atom_unique(
        sku.positive_atoms,
        MeaningAtom(
            type=atom_type,  # type: ignore[arg-type]
            field=field,
            value=value,
            source=source,
            confidence=0.85,
        ),
    )


def _flatten_values(value: Any) -> list[Any]:
    if isinstance(value, list):
        result: list[Any] = []
        for item in value:
            result.extend(_flatten_values(item))
        return result
    return [value]


def apply_sku_guards(
    sku: SkuAtoms,
    *,
    evidence: Mapping[str, Any] | None = None,
    meaning_payload: Mapping[str, Any] | None = None,
    profile: CategoryProfile | None = None,
) -> SkuAtoms:
    """Apply deterministic SKU-atom guards using global and profile-driven rules."""

    result = sku.model_copy(deep=True)
    evidence = evidence or {}
    meaning_payload = meaning_payload or {}
    product = evidence.get("product") if isinstance(evidence.get("product"), Mapping) else {}
    characteristics = product.get("characteristics") if isinstance(product, Mapping) else None

    functional = meaning_payload.get("functional") if isinstance(meaning_payload.get("functional"), Mapping) else {}
    expressive = meaning_payload.get("expressive") if isinstance(meaning_payload.get("expressive"), Mapping) else {}
    product_type = str(functional.get("product_type") or result.product_type or "").strip()
    if product_type:
        result.product_type = product_type
        _add_sku_fact(result, atom_type="product_type", field="product_type", value=product_type, source="sku_meaning")

    _apply_profile_sku_characteristics(result, profile=profile, characteristics=characteristics)
    _apply_profile_sku_functional_tokens(result, profile=profile, meaning_payload=meaning_payload)

    for value in listify(expressive.get("vibes")) + listify(expressive.get("styles")):
        _add_sku_positive(result, atom_type="expressive", field="expressive", value=value)
    for value in listify(expressive.get("gift_contexts")):
        _add_sku_positive(result, atom_type="occasion", field="occasion", value=value)
    for value in listify(meaning_payload.get("audience")):
        _add_sku_positive(result, atom_type="recipient", field="recipient", value=value)
    for value in listify(meaning_payload.get("negative_constraints")):
        append_atom_unique(
            result.negative_fit_atoms,
            MeaningAtom(
                type="attribute",
                field="negative",
                value=value,
                source="sku_meaning",
                confidence=0.8,
            ),
        )

    return result
