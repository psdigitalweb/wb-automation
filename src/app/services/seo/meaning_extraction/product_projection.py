"""Deterministic ProductProjection builder (Meaning Extraction MVP).

Builds SKU-level projection into CategoryMeaning space per (project_id × category_id × nm_id).

Constraints:
- Only confirmed product evidence fields are used: title, description, characteristics, sizes, colors, dimensions.
- No reviews dependency, no LLM, no embeddings.
- Expressive layer uses a deterministic whitelist lexicon and a fixed weak/strong rule (see docs/seo-module).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.seo.meaning_extraction.category_meaning import build_category_meaning
from app.services.seo.meaning_extraction.types import (
    CategoryMeaning,
    ProductExpressiveProfile,
    ProductFunctionalProfile,
    ProductProjection,
)
from app.services.seo.query_pipeline import normalize_query_text


class ProductProjectionError(Exception):
    """Base ProductProjection error."""


class ProductProjectionNotFoundError(ProductProjectionError):
    """Raised when SKU is unavailable in selected project."""


class ProductProjectionScopeError(ProductProjectionError):
    """Raised when SKU falls outside selected category scope."""


_STOP_TOKENS = {
    "без",
    "в",
    "во",
    "для",
    "до",
    "из",
    "и",
    "или",
    "к",
    "ко",
    "на",
    "над",
    "от",
    "по",
    "под",
    "при",
    "с",
    "со",
    "у",
    "не",
}
_NUMBER_LIKE_RE = re.compile(r"^\d+(?:[.,]\d+)?$", re.IGNORECASE)
_LATIN_RE = re.compile(r"[a-z]", re.IGNORECASE)
_ADJECTIVE_ENDINGS = (
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
    "ую",
    "юю",
    "ых",
    "их",
    "ыми",
    "ими",
)

# Must match CategoryMeaning MVP vibe whitelist.
_VIBE_TOKENS = {
    "premium",
    "премиум",
    "aesthetic",
    "cute",
    "meme",
    "мем",
    "minimal",
    "минимализм",
}


@dataclass(frozen=True)
class ProductProjectionBuildFlags:
    """Minimal explainability flags for debug exposure (Task 05)."""

    weak_expressive_signal: bool
    strong_expressive_signal: bool
    used_category_prior: bool
    applied_sku_vibes: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "weak_expressive_signal": bool(self.weak_expressive_signal),
            "strong_expressive_signal": bool(self.strong_expressive_signal),
            "used_category_prior": bool(self.used_category_prior),
            "applied_sku_vibes": bool(self.applied_sku_vibes),
        }


def _is_number_like(token: str) -> bool:
    return bool(_NUMBER_LIKE_RE.match(token))


def _is_latin_like(token: str) -> bool:
    return bool(_LATIN_RE.search(token))


def _is_adjective_like(token: str) -> bool:
    normalized = str(token or "")
    return any(normalized.endswith(ending) for ending in _ADJECTIVE_ENDINGS)


def _tokenize(text_value: str) -> list[str]:
    normalized = normalize_query_text(text_value or "")
    return [token for token in normalized.split(" ") if token]


def _dedupe_ordered(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _json_loads_maybe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped[:1] in {"[", "{"}:
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value
        return value
    return value


def _flatten_jsonish(value: Any) -> list[str]:
    resolved = _json_loads_maybe(value)
    if resolved is None:
        return []
    if isinstance(resolved, str):
        return [resolved]
    if isinstance(resolved, (int, float, bool)):
        return [str(resolved)]
    if isinstance(resolved, dict):
        if "value" in resolved and len(resolved) <= 3:
            return _flatten_jsonish(resolved.get("value"))
        parts: list[str] = []
        for item in resolved.values():
            parts.extend(_flatten_jsonish(item))
        return parts
    if isinstance(resolved, list):
        parts: list[str] = []
        for item in resolved:
            parts.extend(_flatten_jsonish(item))
        return parts
    return [str(resolved)]


def _build_attributes_text(row: Mapping[str, Any]) -> str:
    parts: list[str] = []
    parts.extend(_flatten_jsonish(row.get("characteristics")))
    parts.extend(_flatten_jsonish(row.get("sizes")))
    parts.extend(_flatten_jsonish(row.get("colors")))
    parts.extend(_flatten_jsonish(row.get("dimensions")))
    return " ".join(part for part in (str(part or "").strip() for part in parts) if part)


def _fetch_sku_row(session: Session, *, project_id: int, nm_id: int) -> dict[str, Any]:
    row = session.execute(
        text(
            """
            SELECT
                project_id,
                nm_id,
                subject_id,
                title,
                description,
                characteristics,
                sizes,
                colors,
                dimensions
            FROM products
            WHERE project_id = :project_id
              AND nm_id = :nm_id
            ORDER BY updated_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ),
        {"project_id": project_id, "nm_id": nm_id},
    ).mappings().first()
    if row is None:
        raise ProductProjectionNotFoundError(f"SKU nm_id={nm_id} is not available in project_id={project_id}")
    return dict(row)


def _extract_product_type(title_tokens: list[str], category_meaning: CategoryMeaning) -> str | None:
    axes = [token for token in category_meaning.functional.product_types if token]
    if axes:
        for idx, token in enumerate(title_tokens):
            if token in _STOP_TOKENS:
                continue
            if idx > 0 and title_tokens[idx - 1] in {"для", "под"}:
                continue
            if token in axes:
                return token

    for idx, token in enumerate(title_tokens):
        if token in _STOP_TOKENS:
            continue
        if idx > 0 and title_tokens[idx - 1] in {"для", "под"}:
            continue
        if len(token) < 3:
            continue
        if _is_number_like(token) or _is_latin_like(token):
            continue
        if _is_adjective_like(token):
            continue
        return token
    return None


def _extract_use_cases(title_tokens: list[str], description_tokens: list[str], category_meaning: CategoryMeaning) -> list[str]:
    combined_tokens = [*title_tokens, *description_tokens]
    extracted: list[str] = []
    for idx, token in enumerate(combined_tokens[:-1]):
        if token not in {"для", "под"}:
            continue
        next_token = combined_tokens[idx + 1]
        if not next_token or next_token in _STOP_TOKENS:
            continue
        if _is_number_like(next_token):
            continue
        extracted.append(f"{token} {next_token}")

    extracted = _dedupe_ordered(extracted)
    axes = set(token for token in category_meaning.functional.use_cases if token)
    if axes:
        return [value for value in extracted if value in axes]
    return extracted


def _extract_attributes(attributes_tokens: list[str], category_meaning: CategoryMeaning) -> list[str]:
    extracted = _dedupe_ordered(
        [
            token
            for token in attributes_tokens
            if token
            and token not in _STOP_TOKENS
            and len(token) >= 3
            and not _is_number_like(token)
        ]
    )
    axes = set(token for token in category_meaning.functional.attributes if token)
    if axes:
        return [value for value in extracted if value in axes]
    return extracted


def _extract_vibes(tokens: list[str]) -> list[str]:
    return _dedupe_ordered([token for token in tokens if token in _VIBE_TOKENS])


def _is_strong_expressive_signal(
    *,
    title_vibes: list[str],
    description_vibes: list[str],
    category_prior_vibes: list[str],
) -> bool:
    # MVP rule from docs:
    # 1) >= 2 candidates in title
    if len(title_vibes) >= 2:
        return True
    # 2) >= 1 candidate in title that intersects category prior axis
    if title_vibes and set(title_vibes) & set(category_prior_vibes or []):
        return True
    # 3) >= 3 total candidates and at least 1 from title
    total = len(_dedupe_ordered([*title_vibes, *description_vibes]))
    if total >= 3 and len(title_vibes) >= 1:
        return True
    return False


def build_product_projection(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    category_meaning: CategoryMeaning | None = None,
) -> tuple[ProductProjection, ProductProjectionBuildFlags]:
    """Build deterministic ProductProjection for one SKU in one category scope."""

    sku_row = _fetch_sku_row(session, project_id=project_id, nm_id=nm_id)
    subject_id = sku_row.get("subject_id")
    if subject_id is not None and int(subject_id) != int(category_id):
        raise ProductProjectionScopeError(
            f"SKU nm_id={nm_id} subject_id={subject_id} is outside category_id={category_id} scope"
        )

    resolved_category_meaning = category_meaning or build_category_meaning(
        session, project_id=project_id, category_id=category_id
    )

    title_text = str(sku_row.get("title") or "").strip()
    description_text = str(sku_row.get("description") or "").strip()
    attributes_text = _build_attributes_text(sku_row)

    title_tokens = _tokenize(title_text)
    description_tokens = _tokenize(description_text)
    attributes_tokens = _tokenize(attributes_text)

    functional = ProductFunctionalProfile(
        product_type=_extract_product_type(title_tokens, resolved_category_meaning),
        use_cases=_extract_use_cases(title_tokens, description_tokens, resolved_category_meaning),
        attributes=_extract_attributes(attributes_tokens, resolved_category_meaning),
    ).normalized()

    title_vibes = _extract_vibes(title_tokens)
    description_vibes = _extract_vibes(description_tokens)
    category_prior_vibes = list(resolved_category_meaning.expressive.vibes or [])

    strong = _is_strong_expressive_signal(
        title_vibes=title_vibes,
        description_vibes=description_vibes,
        category_prior_vibes=category_prior_vibes,
    )
    weak = not strong

    sku_vibes = _dedupe_ordered([*title_vibes, *description_vibes])
    if weak:
        expressive_vibes = list(category_prior_vibes)
        applied_sku_vibes = False
        used_prior = True if category_prior_vibes else False
    else:
        # Strong signal: apply SKU vibes and keep prior as baseline (SKU-first ordering).
        expressive_vibes = _dedupe_ordered([*sku_vibes, *category_prior_vibes])
        applied_sku_vibes = bool(sku_vibes)
        used_prior = bool(category_prior_vibes)

    projection = ProductProjection(
        project_id=int(project_id),
        category_id=int(category_id),
        nm_id=int(nm_id),
        functional=functional,
        expressive=ProductExpressiveProfile(vibes=expressive_vibes).normalized(),
    ).normalized()

    flags = ProductProjectionBuildFlags(
        weak_expressive_signal=weak,
        strong_expressive_signal=strong,
        used_category_prior=used_prior,
        applied_sku_vibes=applied_sku_vibes,
    )
    return projection, flags

