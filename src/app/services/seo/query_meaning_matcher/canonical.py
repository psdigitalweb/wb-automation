"""Canonical text and normalization helpers for meaning matching."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from app.schemas.seo_query_meaning_matcher import QueryMeaningPayload


_WORD_RE = re.compile(r"[0-9a-zA-Zа-яА-ЯёЁ]+", re.IGNORECASE)


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, dict):
        items: list[str] = []
        for item in value.values():
            items.extend(listify(item))
        return items
    text_value = str(value).strip()
    return [text_value] if text_value else []


def normalized_tokens(*values: Any) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        for item in listify(value):
            tokens.update(token.lower().replace("ё", "е") for token in _WORD_RE.findall(item))
    return {token for token in tokens if token}


def unique_strings(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower().replace("ё", "е")
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def normalize_query_meaning_payload(payload: Mapping[str, Any] | QueryMeaningPayload | None) -> QueryMeaningPayload:
    raw = payload.model_dump(mode="json") if isinstance(payload, QueryMeaningPayload) else dict(payload or {})

    functional = raw.get("functional") if isinstance(raw.get("functional"), dict) else {}
    expressive = raw.get("expressive") if isinstance(raw.get("expressive"), dict) else {}
    genericness = str(raw.get("genericness") or "specific").strip()
    if genericness not in {"specific", "broad", "generic"}:
        genericness = "specific"

    confidence_raw = raw.get("confidence")
    confidence: dict[str, float] = {}
    if isinstance(confidence_raw, dict):
        for key, value in confidence_raw.items():
            try:
                numeric = float(value)
            except Exception:
                continue
            confidence[str(key)] = max(0.0, min(1.0, numeric))

    return QueryMeaningPayload(
        functional=functional,
        expressive=expressive,
        audience=unique_strings(listify(raw.get("audience"))),
        occasion=unique_strings(listify(raw.get("occasion"))),
        constraints=unique_strings(listify(raw.get("constraints"))),
        conflicts_if_missing=unique_strings(listify(raw.get("conflicts_if_missing"))),
        genericness=genericness,  # type: ignore[arg-type]
        confidence=confidence,
    )


def _line(label: str, values: Iterable[Any] | Any) -> str:
    parts = unique_strings(listify(values))
    return f"{label}: {', '.join(parts)}"


def build_query_canonical_text(payload: QueryMeaningPayload) -> str:
    functional = payload.functional or {}
    expressive = payload.expressive or {}
    return "\n".join(
        [
            _line("товар", functional.get("product_type")),
            _line("сценарии", functional.get("use_cases")),
            _line("атрибуты", functional.get("attributes")),
            _line("стиль", [*listify(expressive.get("styles")), *listify(expressive.get("vibes"))]),
            _line("эмоции", expressive.get("emotions")),
            _line("аудитория", payload.audience),
            _line("повод", [*payload.occasion, *listify(expressive.get("gift_contexts"))]),
            _line("ограничения", payload.constraints),
            f"общность: {payload.genericness}",
        ]
    )


def build_sku_canonical_text(meaning_payload: Mapping[str, Any]) -> str:
    functional = meaning_payload.get("functional") if isinstance(meaning_payload.get("functional"), dict) else {}
    expressive = meaning_payload.get("expressive") if isinstance(meaning_payload.get("expressive"), dict) else {}
    return "\n".join(
        [
            _line("товар", functional.get("product_type")),
            _line("сценарии", functional.get("use_cases")),
            _line("атрибуты", functional.get("attributes")),
            _line("стиль", [*listify(expressive.get("styles")), *listify(expressive.get("vibes"))]),
            _line("эмоции", expressive.get("emotions")),
            _line("аудитория", meaning_payload.get("audience")),
            _line("повод", expressive.get("gift_contexts")),
            _line("не оптимизировать", meaning_payload.get("negative_constraints")),
        ]
    )
