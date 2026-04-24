"""Shared visual motif extraction and normalization for SEO matching."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


_WORD_RE = re.compile(r"[0-9a-zA-Zа-яА-ЯёЁ]+", re.IGNORECASE)
_VISUAL_CONTEXT_RE = re.compile(
    r"(?:принт|рисунок|изображени[ея]|картинк[аи]|дизайн|узор|арт|мем|персонаж|герой)"
    r"(?:\s+с)?\s+(?P<tail>[0-9a-zA-Zа-яА-ЯёЁ\s-]{3,80})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class VisualMotifRule:
    canonical: str
    exact: tuple[str, ...] = ()
    prefixes: tuple[str, ...] = ()
    phrases: tuple[str, ...] = ()


VISUAL_MOTIF_RULES: tuple[VisualMotifRule, ...] = (
    VisualMotifRule("капибара", exact=("capybara",), prefixes=("капибар",), phrases=("capybara",)),
    VisualMotifRule("кот", exact=("кот", "кота", "коту", "котом", "коте", "коты", "cat", "cats", "kitty"), prefixes=("кошк", "котик", "котен", "котят"), phrases=("hello kitty",)),
    VisualMotifRule("собака", exact=("dog", "dogs", "пес", "пса", "псу", "псом", "псы", "пёс"), prefixes=("собак", "щенк"), phrases=("hot dog",)),
    VisualMotifRule("лиса", exact=("лиса", "лису", "лисой", "лисы", "лисе", "fox"), prefixes=("лисич", "лисен", "лисён")),
    VisualMotifRule("медведь", exact=("bear", "bears", "мишка", "мишки", "мишкой"), prefixes=("медвед", "мишк")),
    VisualMotifRule("панда", exact=("panda", "pandas"), prefixes=("панд",)),
    VisualMotifRule("заяц", exact=("заяц", "зайца", "зайцу", "зайцем", "зайцы", "bunny", "rabbit"), prefixes=("зайк", "зайчик", "кролик")),
    VisualMotifRule("единорог", exact=("unicorn",), prefixes=("единорог",)),
    VisualMotifRule("гусь", exact=("гусь", "гуся", "гусю", "гусем", "гуси", "goose"), prefixes=("гусен",)),
    VisualMotifRule("лягушка", exact=("frog",), prefixes=("лягуш",)),
    VisualMotifRule("утка", exact=("duck",), prefixes=("утк", "уточк")),
    VisualMotifRule("динозавр", exact=("dino",), prefixes=("динозавр",)),
    VisualMotifRule("дракон", exact=("dragon",), prefixes=("дракон",)),
    VisualMotifRule("сова", exact=("сова", "сову", "совой", "совы", "сове", "owl")),
    VisualMotifRule("лошадка", exact=("horse", "rocking_horse"), prefixes=("лошад",)),
    VisualMotifRule("рыба", exact=("fish",), prefixes=("рыб",)),
    VisualMotifRule("бабочка", exact=("butterfly",), prefixes=("бабочк",)),
    VisualMotifRule("птица", exact=("bird",), prefixes=("птиц", "птичк")),
    VisualMotifRule("сердце", exact=("heart",), prefixes=("сердц",)),
    VisualMotifRule("звезда", exact=("star",), prefixes=("звезд", "звёзд")),
    VisualMotifRule("цветы", exact=("цветы", "цветами", "flower", "flowers", "floral"), prefixes=("цветоч",), phrases=("с цветами",)),
    VisualMotifRule("мухомор", exact=("мухомор", "мухоморы"), prefixes=("мухомор",)),
    VisualMotifRule("авокадо", exact=("авокадо", "avocado"), prefixes=("авокад",)),
    VisualMotifRule("стич", exact=("stitch",), prefixes=("стич",)),
    VisualMotifRule("аниме", exact=("anime", "аниме"), prefixes=("аним",)),
)

_STOP_MOTIF_TOKENS = {
    "арт",
    "белый",
    "блюдце",
    "большой",
    "дизайн",
    "женский",
    "изображение",
    "имя",
    "картинка",
    "керамика",
    "коробка",
    "красивый",
    "кружка",
    "крышка",
    "ложка",
    "мальчик",
    "милый",
    "мужской",
    "надпись",
    "набор",
    "подарок",
    "подогрев",
    "подруга",
    "принт",
    "рисунок",
    "розовый",
    "ситечко",
    "стекло",
    "текст",
    "узор",
    "упаковка",
    "цвет",
    "цветной",
    "чашка",
}

_RU_ENDINGS = (
    "ями",
    "ами",
    "ого",
    "ему",
    "ому",
    "ими",
    "ыми",
    "ой",
    "ей",
    "ий",
    "ый",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ов",
    "ев",
    "ам",
    "ям",
    "ах",
    "ях",
    "ом",
    "ем",
    "ую",
    "юю",
    "а",
    "я",
    "у",
    "ю",
    "ы",
    "и",
    "е",
)


def normalize_visual_text(value: Any) -> str:
    return str(value or "").lower().replace("ё", "е").replace("_", " ").strip()


def visual_tokens(value: Any) -> list[str]:
    return [token.lower().replace("ё", "е") for token in _WORD_RE.findall(str(value or ""))]


def _matches_rule(rule: VisualMotifRule, text: str, tokens: Iterable[str]) -> bool:
    token_set = set(tokens)
    if any(phrase and phrase in text for phrase in rule.phrases):
        return True
    if token_set & set(rule.exact):
        return True
    return any(token.startswith(prefix) for token in token_set for prefix in rule.prefixes)


def canonicalize_motif_value(value: Any) -> str | None:
    text = normalize_visual_text(value)
    tokens = visual_tokens(text)
    for rule in VISUAL_MOTIF_RULES:
        if _matches_rule(rule, text, tokens):
            return rule.canonical
    return None


def _normalize_unknown_motif_token(token: str) -> str | None:
    normalized = normalize_visual_text(token)
    if len(normalized) < 4 or normalized in _STOP_MOTIF_TOKENS:
        return None
    for ending in _RU_ENDINGS:
        if normalized.endswith(ending) and len(normalized) - len(ending) >= 4:
            normalized = normalized[: -len(ending)]
            break
    if normalized in _STOP_MOTIF_TOKENS or len(normalized) < 4:
        return None
    return normalized


def _append_unique(values: list[str], value: str | None) -> None:
    if not value:
        return
    key = normalize_visual_text(value)
    if key and key not in {normalize_visual_text(item) for item in values}:
        values.append(value)


def extract_visual_motifs(*texts: Any) -> list[str]:
    combined = " ".join(str(text or "") for text in texts if str(text or "").strip())
    normalized = normalize_visual_text(combined)
    tokens = visual_tokens(normalized)
    motifs: list[str] = []
    for rule in VISUAL_MOTIF_RULES:
        if _matches_rule(rule, normalized, tokens):
            _append_unique(motifs, rule.canonical)

    for match in _VISUAL_CONTEXT_RE.finditer(normalized):
        tail_tokens = visual_tokens(match.group("tail"))[:4]
        for token in tail_tokens:
            canonical = canonicalize_motif_value(token) or _normalize_unknown_motif_token(token)
            _append_unique(motifs, canonical)
    return motifs


def expand_visual_tokens(tokens: set[str]) -> set[str]:
    expanded = set(tokens)
    for token in tokens:
        canonical = canonicalize_motif_value(token)
        if canonical:
            expanded.add(canonical)
    return expanded


def embedding_markers() -> tuple[str, ...]:
    markers: list[str] = []
    for rule in VISUAL_MOTIF_RULES:
        markers.extend(rule.exact)
        markers.extend(f"^{prefix}" for prefix in rule.prefixes)
        markers.extend(rule.phrases)
    return tuple(dict.fromkeys(markers))
