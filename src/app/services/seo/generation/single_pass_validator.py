"""Deterministic validation for single-pass SEO generation experiments."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

BLACKLIST_PATTERNS: tuple[str, ...] = (
    "идеальный выбор",
    "идеальный вариант",
    "идеальное решение",
    "идеальна как",
    "идеален для",
    "практичный выбор",
    "универсальный подарок",
    "подойдёт всем",
    "подойдет всем",
    "вещь, которая радует",
    "вещь, которая греет",
    "захочется использовать каждый день",
    "источник уюта",
    "источник тепла",
    "источник вдохновения",
    "наполнит теплом",
    "подарит настроение",
    "дарит настроение",
    "создаёт атмосферу",
    "создает атмосферу",
    "день становится теплее",
    "день становится светлее",
    "теплеет на душе",
    "становится чуть теплее",
    "удобно держится в руке",
    "удобно лежит в ладони",
    "удобно держать",
    "удобная для ладони",
    "приятна в руках",
    "керамика гладкая",
    "не занимает много места",
    "не требует много места",
    "компактный размер",
    "гарантирует долгое служение",
    "прослужит долго",
    "инвестиция в удобство",
    "инвестиция в качество",
    "инвестиция в комфорт",
    "соответствует стандартам качества",
    "оптимальный объём",
    "оптимальный объем",
    "не просто посуда",
    "не просто кружка",
    "не просто вещь",
    "больше, чем просто",
    "маленькая, но важная деталь",
    "с характером и душой",
    "дарить близким",
    "дарить друзьям",
    "дарить радость",
)


def validate_format(parsed_result: dict[str, Any]) -> list[str]:
    """Check the parsed section structure expected from the shared parser."""
    errors: list[str] = []
    title = str(parsed_result.get("title") or "")
    if not title:
        errors.append("missing_title")
    elif len(title) > 60:
        errors.append(f"title_too_long:{len(title)}")

    blocks = parsed_result.get("description_blocks", [])
    if not isinstance(blocks, list):
        blocks = []
    if len(blocks) != 6:
        errors.append(f"wrong_block_count:{len(blocks)}")

    for index, block in enumerate(blocks):
        if not str(block or "").strip():
            errors.append(f"empty_block:{index + 1}")

    return errors


def validate_keyword_coverage(text: str, priority_queries: Sequence[str]) -> dict[str, list[str]]:
    """Check that every priority query is covered in at least one sentence."""
    text_lower = text.lower()
    sentences = re.split(r"[.!?\n]+", text_lower)

    covered: list[str] = []
    missing: list[str] = []

    for query in priority_queries:
        query_text = str(query or "").strip()
        if not query_text:
            continue
        query_words = query_text.lower().split()
        found = any(all(word in sentence for word in query_words) for sentence in sentences)
        (covered if found else missing).append(query_text)

    return {"covered": covered, "missing": missing}


def validate_blacklist(text: str) -> list[str]:
    """Return blacklist phrases found in generated text."""
    text_lower = text.lower()
    return [pattern for pattern in BLACKLIST_PATTERNS if pattern.lower() in text_lower]


def validate_main_query_in_title(title: str, main_query: str) -> bool:
    """Check exact case-insensitive main-query inclusion in the title."""
    query = str(main_query or "").strip()
    if not query:
        return True
    return query.lower() in str(title or "").lower()


def validate_generation(
    parsed_result: dict[str, Any],
    priority_queries: Sequence[str],
    main_query: str,
) -> dict[str, Any]:
    """Run all deterministic checks for the single-pass Sonnet strategy."""
    title = str(parsed_result.get("title") or "")
    description = str(parsed_result.get("description") or "")
    full_text = f"{title} {description}"

    format_errors = validate_format(parsed_result)
    keyword_result = validate_keyword_coverage(full_text, priority_queries)
    blacklist_hits = validate_blacklist(full_text)
    main_query_ok = validate_main_query_in_title(title, main_query)

    passed = (
        len(format_errors) == 0
        and len(keyword_result["missing"]) == 0
        and len(blacklist_hits) == 0
        and main_query_ok
    )

    return {
        "passed": passed,
        "format_errors": format_errors,
        "keyword_coverage": keyword_result,
        "blacklist_hits": blacklist_hits,
        "main_query_in_title": main_query_ok,
    }
