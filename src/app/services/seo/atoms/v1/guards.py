"""Deterministic guardrails for meaning atoms extraction.

The LLM owns semantic interpretation. Guards only normalize explicit facts that
are visible in the text or structured product evidence.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

from app.services.seo.atoms.v1.schemas import MeaningAtom, QueryAtoms, SkuAtoms
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


def apply_query_guards(query: QueryAtoms, query_texts: Iterable[str]) -> QueryAtoms:
    result = query.model_copy(deep=True)
    texts = [str(item or "") for item in query_texts if str(item or "").strip()]
    primary_text = normalize_text(texts[0] if texts else "")

    if "термокруж" in primary_text or re.search(r"\bтермос", primary_text):
        result.product_type = result.product_type or "термокружка"
        _add_required(result, atom_type="product_type", field="product_type", value="термокружка")
        _add_required(result, atom_type="compatibility", field="thermal", value=True)
    elif "круж" in primary_text and not result.product_type:
        result.product_type = "кружка"

    for match in _VOLUME_RE.finditer(primary_text):
        _add_required(result, atom_type="numeric", field="volume_ml", value=int(match.group("value")), operator="close_to")
    if re.search(r"\b(?:литровая|литровый|литровые|литр|1\s*л)\b", primary_text):
        _add_required(result, atom_type="numeric", field="volume_ml", value=1000, operator="close_to")

    for match in _QUANTITY_RE.finditer(primary_text):
        _add_required(result, atom_type="numeric", field="quantity", value=int(match.group("value")))
    if "набор" in primary_text or "комплект" in primary_text:
        _add_required(result, atom_type="attribute", field="quantity", value="set")

    if "без рисун" in primary_text or "без принт" in primary_text:
        _add_excluded(result, field="design", value="print")
    if "без крыш" in primary_text:
        _add_excluded(result, field="feature", value="lid")
    if "прозрач" in primary_text:
        _add_required(result, atom_type="visual", field="transparency", value="transparent")
    for motif in extract_visual_motifs(primary_text):
        _add_required(result, atom_type="visual", field="motif", value=motif)
        if result.genericness in {"generic", "broad"}:
            result.genericness = "specific"

    if "кофемаш" in primary_text:
        _add_required(result, atom_type="compatibility", field="compatibility", value="coffee_machine")
    if "в машину" in primary_text or "для машины" in primary_text or "авто" in primary_text:
        _add_required(result, atom_type="use_case", field="context", value="car")
    if "пивн" in primary_text:
        _add_required(result, atom_type="use_case", field="use_case", value="beer")

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


def apply_sku_guards(sku: SkuAtoms, *, evidence: Mapping[str, Any] | None = None, meaning_payload: Mapping[str, Any] | None = None) -> SkuAtoms:
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

    for name, raw_value in _iter_characteristics(characteristics):
        name_norm = normalize_text(name)
        values = _flatten_values(raw_value)
        for value in values:
            value_text = normalize_text(value)
            if "объем" in name_norm:
                found = _VOLUME_RE.search(f"{value_text} мл") or re.search(r"\d{2,4}", value_text)
                if found:
                    numeric = int(found.group("value") if "value" in found.groupdict() else found.group(0))
                    _add_sku_fact(result, atom_type="numeric", field="volume_ml", value=numeric)
            if "цвет" in name_norm:
                _add_sku_fact(result, atom_type="attribute", field="color", value=value)
            if "материал" in name_norm:
                _add_sku_fact(result, atom_type="attribute", field="material", value=value)
            if "количество" in name_norm:
                found = re.search(r"\d{1,2}", value_text)
                if found:
                    _add_sku_fact(result, atom_type="numeric", field="quantity", value=int(found.group(0)))
            if "рисунок" in name_norm or "декоратив" in name_norm:
                if value_text and value_text not in {"нет", "без", "none"}:
                    _add_sku_fact(result, atom_type="visual", field="design", value="print")
                    _add_sku_positive(result, atom_type="visual", field="motif", value=value, source="product_characteristics")
            if "особенности" in name_norm:
                if "свч" in value_text:
                    _add_sku_fact(result, atom_type="compatibility", field="compatibility", value="microwave")
                if "посудом" in value_text:
                    _add_sku_fact(result, atom_type="compatibility", field="compatibility", value="dishwasher")
            if "назначение подарка" in name_norm:
                _add_sku_positive(result, atom_type="recipient", field="recipient", value=value, source="product_characteristics")
            if name_norm == "повод" or "повод" in name_norm:
                _add_sku_positive(result, atom_type="occasion", field="occasion", value=value, source="product_characteristics")

    for value in listify(functional.get("attributes")) + listify(functional.get("use_cases")):
        value_norm = normalize_text(value)
        if "термокруж" in value_norm:
            _add_sku_fact(result, atom_type="compatibility", field="thermal", value=True, source="sku_meaning")
        if "посудом" in value_norm:
            _add_sku_fact(result, atom_type="compatibility", field="compatibility", value="dishwasher", source="sku_meaning")
        if "свч" in value_norm:
            _add_sku_fact(result, atom_type="compatibility", field="compatibility", value="microwave", source="sku_meaning")

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
