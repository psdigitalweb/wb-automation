"""Read-only access layer for WB reviews used in category expressive extraction.

Source of truth for review storage (current runtime):
- table: wb_feedback_snapshots
- rating column: product_valuation
- review text lives in JSON raw: text/pros/cons
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.seo.expressive_llm.models import CategoryReviewScope, ReviewSnippet


def _clean_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _loads_raw_maybe(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except Exception:
            return None
        return data if isinstance(data, dict) else None
    return None


def _combine_review_text(raw: Any) -> str | None:
    data = _loads_raw_maybe(raw)
    if not isinstance(data, dict):
        return None
    parts = [
        _clean_optional_text(data.get("text")),
        _clean_optional_text(data.get("pros")),
        _clean_optional_text(data.get("cons")),
    ]
    combined = "\n".join(part for part in parts if part)
    combined = combined.strip()
    return combined or None


def fetch_category_review_scope(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    min_rating: int = 4,
    limit: int = 2000,
) -> CategoryReviewScope:
    """Fetch raw review snippets for a category (rating-filtered, read-only).

    Notes:
    - No dedup/truncation here (belongs to Task 19.02 input builder).
    - Rows with empty combined text are dropped.
    """

    if limit <= 0:
        raise ValueError("limit must be > 0")

    params = {
        "project_id": int(project_id),
        "category_id": int(category_id),
        "min_rating": int(min_rating),
        "limit": int(limit),
    }

    # Best-effort category name (may be NULL if subject_name is missing / not populated).
    name_sql = text(
        """
        SELECT MAX(p.subject_name) AS category_name
        FROM products p
        WHERE p.project_id = :project_id
          AND p.subject_id = :category_id
        """
    )
    try:
        category_name = session.execute(name_sql, params).scalar()
    except Exception:
        category_name = None
    category_name = str(category_name).strip() if category_name else None

    reviews_sql = text(
        """
        SELECT
            fs.nm_id,
            fs.product_valuation AS rating,
            fs.created_date AS created_date,
            fs.raw AS raw
        FROM wb_feedback_snapshots fs
        JOIN products p
          ON p.project_id = fs.project_id
         AND p.nm_id = fs.nm_id
        WHERE fs.project_id = :project_id
          AND p.subject_id = :category_id
          AND fs.product_valuation IS NOT NULL
          AND fs.product_valuation >= :min_rating
        ORDER BY fs.created_date DESC NULLS LAST, fs.id DESC
        LIMIT :limit
        """
    )

    rows = session.execute(reviews_sql, params).mappings().all()

    snippets: list[ReviewSnippet] = []
    nm_ids_seen: set[int] = set()
    nm_ids: list[int] = []
    dropped_empty_text = 0
    for row in rows:
        nm_id = int(row.get("nm_id") or 0)
        if nm_id <= 0:
            continue
        rating = int(row.get("rating") or 0)
        combined = _combine_review_text(row.get("raw"))
        if not combined:
            dropped_empty_text += 1
            continue

        created_raw = row.get("created_date")
        created_at: datetime | None = None
        if isinstance(created_raw, datetime):
            created_at = created_raw
        elif isinstance(created_raw, str):
            value = created_raw.strip()
            if value:
                try:
                    created_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
                except Exception:
                    created_at = None

        snippets.append(
            ReviewSnippet(
                project_id=int(project_id),
                nm_id=nm_id,
                rating=rating,
                text=combined,
                created_at=created_at,
            )
        )
        if nm_id not in nm_ids_seen:
            nm_ids_seen.add(nm_id)
            nm_ids.append(nm_id)

    return CategoryReviewScope(
        project_id=int(project_id),
        category_id=int(category_id),
        category_name=category_name,
        review_snippets=snippets,
        nm_ids=nm_ids,
        fetched_rows=len(rows),
        dropped_empty_text=int(dropped_empty_text),
    )
