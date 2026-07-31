"""Data models for the LLM-backed expressive layer (offline/precompute)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ReviewSnippet:
    project_id: int
    nm_id: int
    rating: int
    text: str
    created_at: datetime | None = None


@dataclass(frozen=True)
class CategoryReviewScope:
    project_id: int
    category_id: int
    category_name: str | None

    review_snippets: list[ReviewSnippet] = field(default_factory=list)
    nm_ids: list[int] = field(default_factory=list)

    # Best-effort counters for debugging/visibility.
    fetched_rows: int = 0
    dropped_empty_text: int = 0

