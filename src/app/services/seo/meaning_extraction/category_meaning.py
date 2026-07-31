"""Deterministic CategoryMeaning builder (Meaning Extraction MVP).

Builds product-side semantic space per (project_id × category_id) where category_id = WB subject_id.

Constraints:
- Only confirmed product evidence fields are used: title, description, characteristics, sizes, colors, dimensions.
- Functional meaning is deterministic (no reviews, no LLM, no embeddings).
- Expressive meaning is taken from offline LLM cache artifacts (if present), otherwise empty.
- Aggregation keeps only "repeating patterns" using MVP thresholds documented in docs/seo-module.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app import settings
from app.services.seo.expressive_llm.category_input_builder import build_category_expressive_input
from app.services.seo.expressive_llm.reviews_source import fetch_category_review_scope
from app.services.seo.expressive_llm.storage import CategoryExpressiveCacheKey, CategoryExpressiveStore
from app.services.seo.meaning_extraction.types import (
    CategoryExpressiveMeaning,
    CategoryFunctionalMeaning,
    CategoryMeaning,
)
from app.services.seo.query_pipeline import normalize_query_text


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

# Minimal MVP vibe lexicon: deterministic whitelist only (no LLM/embeddings).
_LLM_EXPRESSIVE_PROMPT_VERSION = "v1"


def _fetch_titles_for_nm_ids(session: Session, *, project_id: int, nm_ids: list[int]) -> list[str]:
    if not nm_ids:
        return []
    rows = session.execute(
        text(
            """
            SELECT p.title
            FROM v_wb_product_source p
            WHERE p.project_id = :project_id
              AND p.nm_id IN :nm_ids
              AND p.title IS NOT NULL
            ORDER BY p.nm_id
            """
        ).bindparams(bindparam("nm_ids", expanding=True)),
        {"project_id": int(project_id), "nm_ids": [int(x) for x in nm_ids]},
    ).all()
    return [str(row[0]) for row in rows if row and row[0] is not None]


def _load_llm_expressive_from_cache(session: Session, *, project_id: int, category_id: int) -> CategoryExpressiveMeaning:
    """Load category expressive meaning from LLM cache (offline/precompute artifacts).

    Rules (iteration 19 integration):
    - functional meaning stays deterministic
    - expressive meaning is taken from LLM cache (if exists), otherwise empty
    - no LLM calls here
    """

    try:
        scope = fetch_category_review_scope(
            session,
            project_id=int(project_id),
            category_id=int(category_id),
            min_rating=4,
            limit=5000,
        )
        if not scope.review_snippets:
            return CategoryExpressiveMeaning(vibes=[], llm=None)

        titles = _fetch_titles_for_nm_ids(session, project_id=int(project_id), nm_ids=list(scope.nm_ids))
        category_name = scope.category_name or f"category_{int(category_id)}"

        built = build_category_expressive_input(
            category_name=category_name,
            reviews=scope.review_snippets,
            titles=titles,
            max_reviews=100,
        )
        if built.reviews_count <= 0:
            return CategoryExpressiveMeaning(vibes=[], llm=None)

        model = str(settings.OPENROUTER_CHAT_MODEL or "openai/gpt-4.1-mini")
        key = CategoryExpressiveCacheKey(
            project_id=int(project_id),
            category_id=int(category_id),
            model=model,
            prompt_version=_LLM_EXPRESSIVE_PROMPT_VERSION,
            input_hash=str(built.input_hash),
        )
        store = CategoryExpressiveStore()
        artifact = store.get(key=key)
        if artifact is None or not isinstance(artifact.parsed, dict):
            return CategoryExpressiveMeaning(vibes=[], llm=None)

        parsed = dict(artifact.parsed)
        vibes_raw = parsed.get("vibes") or []
        labels: list[str] = []
        if isinstance(vibes_raw, list):
            for item in vibes_raw:
                if isinstance(item, dict):
                    label = str(item.get("label") or "").strip()
                    if label:
                        labels.append(label)
                elif isinstance(item, str):
                    value = str(item).strip()
                    if value:
                        labels.append(value)

        return CategoryExpressiveMeaning(vibes=labels, llm=parsed).normalized()
    except Exception:
        # Any DB/schema/cache errors should not break functional meaning builder.
        return CategoryExpressiveMeaning(vibes=[], llm=None)


@dataclass(frozen=True)
class CategoryMeaningThresholds:
    """MVP deterministic thresholds for "repeating patterns" aggregation."""

    min_support_sku_count: int = 3
    min_support_share: float = 0.15
    small_category_max_sku_count: int = 19
    small_min_support_sku_count: int = 2
    small_min_support_share: float = 0.25
    top_k_product_types: int = 20
    top_k_use_cases: int = 20
    top_k_attributes: int = 40
    top_k_vibes: int = 20

    def resolve_min_support(self, total_sku_count: int) -> tuple[int, float]:
        if total_sku_count <= self.small_category_max_sku_count:
            return self.small_min_support_sku_count, self.small_min_support_share
        return self.min_support_sku_count, self.min_support_share


@dataclass(frozen=True)
class _SkuEvidence:
    nm_id: int
    title_text: str
    description_text: str
    attributes_text: str


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
            # MVP: common shape for characteristics items: {"name": "...", "value": [...]}
            # Only keep the "value" leafs to avoid polluting attributes with field names.
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


def _fetch_latest_sku_evidence(session: Session, *, project_id: int, category_id: int) -> list[_SkuEvidence]:
    rows = session.execute(
        text(
            """
            SELECT
                id,
                updated_at,
                nm_id,
                title,
                description,
                characteristics,
                sizes,
                colors,
                dimensions
            FROM v_wb_product_source
            WHERE project_id = :project_id
              AND subject_id = :category_id
            ORDER BY nm_id ASC, updated_at DESC NULLS LAST, id DESC
            """
        ),
        {"project_id": project_id, "category_id": category_id},
    ).mappings().all()

    latest_by_nm_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        nm_id = int(row.get("nm_id") or 0)
        if nm_id <= 0:
            continue
        if nm_id in latest_by_nm_id:
            continue
        latest_by_nm_id[nm_id] = dict(row)

    evidences: list[_SkuEvidence] = []
    for nm_id, row in latest_by_nm_id.items():
        evidences.append(
            _SkuEvidence(
                nm_id=nm_id,
                title_text=str(row.get("title") or "").strip(),
                description_text=str(row.get("description") or "").strip(),
                attributes_text=_build_attributes_text(row),
            )
        )
    return evidences


def _collect_presence_sets(
    evidences: Iterable[_SkuEvidence],
) -> tuple[dict[int, set[str]], dict[int, set[str]], dict[int, set[str]], dict[int, set[str]]]:
    product_types_by_sku: dict[int, set[str]] = {}
    use_cases_by_sku: dict[int, set[str]] = {}
    attributes_by_sku: dict[int, set[str]] = {}
    vibes_by_sku: dict[int, set[str]] = {}

    for evidence in evidences:
        title_tokens = _tokenize(evidence.title_text)
        description_tokens = _tokenize(evidence.description_text)
        attribute_tokens = _tokenize(evidence.attributes_text)

        # Product-type candidates: noun-like tokens from titles (MVP).
        product_type_candidates: set[str] = set()
        for idx, token in enumerate(title_tokens):
            if token in _STOP_TOKENS:
                continue
            if len(token) < 3:
                continue
            if idx > 0 and title_tokens[idx - 1] in {"для", "под"}:
                # Avoid leaking use-case objects (e.g. "супа") into product-type slot.
                continue
            if _is_number_like(token) or _is_latin_like(token):
                continue
            if _is_adjective_like(token):
                continue
            product_type_candidates.add(token)

        # Use-case candidates: "для X" / "под X" phrases from title/description (MVP).
        use_case_candidates: set[str] = set()
        combined_tokens = [*title_tokens, *description_tokens]
        for idx, token in enumerate(combined_tokens[:-1]):
            if token not in {"для", "под"}:
                continue
            next_token = combined_tokens[idx + 1]
            if not next_token or next_token in _STOP_TOKENS:
                continue
            if _is_number_like(next_token):
                continue
            use_case_candidates.add(f"{token} {next_token}")

        # Attribute candidates: normalized tokens from attributes (plus title/description fallback is out of MVP).
        attribute_candidates: set[str] = set()
        for token in attribute_tokens:
            if token in _STOP_TOKENS:
                continue
            if len(token) < 3:
                continue
            if _is_number_like(token):
                continue
            attribute_candidates.add(token)

        product_types_by_sku[evidence.nm_id] = product_type_candidates
        use_cases_by_sku[evidence.nm_id] = use_case_candidates
        attributes_by_sku[evidence.nm_id] = attribute_candidates
        vibes_by_sku[evidence.nm_id] = set()

    return product_types_by_sku, use_cases_by_sku, attributes_by_sku, vibes_by_sku


def _support_counts(values_by_sku: Mapping[int, set[str]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for _nm_id, values in values_by_sku.items():
        for value in values:
            counter[value] += 1
    return counter


def _select_repeating_patterns(
    *,
    values_by_sku: dict[int, set[str]],
    total_sku_count: int,
    thresholds: CategoryMeaningThresholds,
    top_k: int,
) -> list[str]:
    min_count, min_share = thresholds.resolve_min_support(total_sku_count)
    counts = _support_counts(values_by_sku)

    selected: list[tuple[int, str]] = []
    for value, count in counts.items():
        if count < min_count:
            continue
        share = (count / total_sku_count) if total_sku_count > 0 else 0.0
        if share < min_share:
            continue
        selected.append((int(count), str(value)))

    selected.sort(key=lambda item: (-item[0], item[1]))
    return [value for _count, value in selected[: max(0, int(top_k))]]


def build_category_meaning(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    thresholds: CategoryMeaningThresholds | None = None,
) -> CategoryMeaning:
    """Build CategoryMeaning per project × category (WB subject_id scope)."""

    resolved_thresholds = thresholds or CategoryMeaningThresholds()
    evidences = _fetch_latest_sku_evidence(session, project_id=project_id, category_id=category_id)
    total_sku_count = len(evidences)

    product_types_by_sku, use_cases_by_sku, attributes_by_sku, _vibes_by_sku = _collect_presence_sets(evidences)

    product_types = _select_repeating_patterns(
        values_by_sku=product_types_by_sku,
        total_sku_count=total_sku_count,
        thresholds=resolved_thresholds,
        top_k=resolved_thresholds.top_k_product_types,
    )
    use_cases = _select_repeating_patterns(
        values_by_sku=use_cases_by_sku,
        total_sku_count=total_sku_count,
        thresholds=resolved_thresholds,
        top_k=resolved_thresholds.top_k_use_cases,
    )
    attributes = _select_repeating_patterns(
        values_by_sku=attributes_by_sku,
        total_sku_count=total_sku_count,
        thresholds=resolved_thresholds,
        top_k=resolved_thresholds.top_k_attributes,
    )
    expressive = _load_llm_expressive_from_cache(session, project_id=int(project_id), category_id=int(category_id))
    return CategoryMeaning(
        project_id=int(project_id),
        category_id=int(category_id),
        functional=CategoryFunctionalMeaning(product_types=product_types, use_cases=use_cases, attributes=attributes),
        expressive=expressive,
    ).normalized()
