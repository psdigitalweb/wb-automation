"""Category expressive LLM input builder (reviews primary, titles secondary)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

from app.services.seo.expressive_llm.models import ReviewSnippet
from app.services.seo.expressive_llm.text_normalization import dedupe_keep_order, trim, truncate


@dataclass(frozen=True)
class CategoryExpressiveInput:
    payload: dict
    evidence_text: str
    input_hash: str

    reviews_count: int
    titles_count: int


def _sha256_json(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _reviews_to_texts(reviews: Iterable[ReviewSnippet] | Iterable[str]) -> list[str]:
    texts: list[str] = []
    for item in reviews:
        if isinstance(item, ReviewSnippet):
            texts.append(str(item.text or ""))
        else:
            texts.append(str(item or ""))
    return texts


def build_category_expressive_input(
    *,
    category_name: str,
    reviews: Iterable[ReviewSnippet] | Iterable[str],
    titles: Iterable[str] | None = None,
    max_reviews: int = 100,
    max_review_chars: int = 220,
    max_title_chars: int = 120,
) -> CategoryExpressiveInput:
    """Build a deterministic input payload for category expressive extraction.

    Notes:
    - Reviews are the primary source; they are also the only evidence surface for exact-span validation (MVP).
    - Titles are secondary support and do not participate in evidence exact-match.
    """

    if max_reviews <= 0:
        raise ValueError("max_reviews must be > 0")

    cat = trim(category_name)
    review_texts = [truncate(trim(t), max_chars=max_review_chars) for t in _reviews_to_texts(reviews)]
    review_texts = [t for t in review_texts if t]
    review_texts = dedupe_keep_order(review_texts)
    review_texts = review_texts[: int(max_reviews)]

    title_texts: list[str] = []
    if titles is not None:
        title_texts = [truncate(trim(t), max_chars=max_title_chars) for t in titles]
        title_texts = [t for t in title_texts if t]
        title_texts = dedupe_keep_order(title_texts)

    payload: dict = {"category_name": cat, "reviews": review_texts}
    if title_texts:
        payload["titles"] = title_texts

    evidence_text = "\n".join(review_texts)
    return CategoryExpressiveInput(
        payload=payload,
        evidence_text=evidence_text,
        input_hash=_sha256_json(payload),
        reviews_count=len(review_texts),
        titles_count=len(title_texts),
    )

