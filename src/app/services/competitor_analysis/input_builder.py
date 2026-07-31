"""Build deterministic, privacy-minimized competitor analysis input."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text

from app.db import engine
from .normalization import normalize_text


CHUNK_SIZE = 60


@dataclass(frozen=True)
class CompetitorAnalysisInput:
    target_id: int
    project_id: int
    nm_id: int
    title: str
    category_name: str | None
    source_last_collected_at: datetime | None
    input_hash: str
    reviews: list[dict[str, Any]]
    review_fields: dict[str, tuple[str, ...]]
    estimated_cost_usd: float

    @property
    def chunks(self) -> list[list[dict[str, Any]]]:
        return [
            self.reviews[index : index + CHUNK_SIZE]
            for index in range(0, len(self.reviews), CHUNK_SIZE)
        ]


def estimate_analysis_cost(*, reviews_count: int, text_chars: int) -> float:
    chunks = max(1, math.ceil(max(0, reviews_count) / CHUNK_SIZE))
    estimate = 0.035 + max(0, text_chars) * 0.0000015 + chunks * 0.0015
    return round(min(0.15, max(0.04, estimate)), 4)


def build_competitor_analysis_input(
    project_id: int,
    nm_id: int,
) -> CompetitorAnalysisInput:
    target_sql = text(
        """
        SELECT id, project_id, nm_id, title, category_name, last_collected_at
        FROM wb_competitor_review_targets
        WHERE project_id = :project_id AND nm_id = :nm_id
        """
    )
    reviews_sql = text(
        """
        SELECT external_id, rating, review_created_at, text, pros, cons
        FROM wb_competitor_reviews
        WHERE target_id = :target_id
        ORDER BY review_created_at ASC NULLS LAST, external_id ASC
        """
    )
    with engine.connect() as conn:
        target = conn.execute(
            target_sql,
            {"project_id": int(project_id), "nm_id": int(nm_id)},
        ).mappings().first()
        if target is None:
            raise LookupError("competitor_target_not_found")
        rows = conn.execute(
            reviews_sql,
            {"target_id": int(target["id"])},
        ).mappings().all()

    reviews: list[dict[str, Any]] = []
    review_fields: dict[str, tuple[str, ...]] = {}
    seen_content: set[str] = set()
    text_chars = 0
    for row in rows:
        fields = {
            "text": normalize_text(row.get("text")),
            "pros": normalize_text(row.get("pros")),
            "cons": normalize_text(row.get("cons")),
        }
        if not any(fields.values()):
            continue
        content_key = json.dumps(fields, ensure_ascii=False, sort_keys=True)
        if content_key in seen_content:
            continue
        seen_content.add(content_key)
        review_id = f"r_{len(reviews) + 1:04d}"
        review = {
            "review_id": review_id,
            "rating": int(row["rating"]) if row.get("rating") is not None else None,
            "created_date": (
                row["review_created_at"].date().isoformat()
                if row.get("review_created_at") is not None
                else None
            ),
            **{key: value or None for key, value in fields.items()},
        }
        reviews.append(review)
        review_fields[review_id] = tuple(value for value in fields.values() if value)
        text_chars += sum(len(value) for value in fields.values())

    hash_payload = {
        "nm_id": int(nm_id),
        "title": str(target.get("title") or ""),
        "category_name": target.get("category_name"),
        "reviews": reviews,
    }
    input_hash = hashlib.sha256(
        json.dumps(
            hash_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return CompetitorAnalysisInput(
        target_id=int(target["id"]),
        project_id=int(project_id),
        nm_id=int(nm_id),
        title=str(target.get("title") or ""),
        category_name=target.get("category_name"),
        source_last_collected_at=target.get("last_collected_at"),
        input_hash=input_hash,
        reviews=reviews,
        review_fields=review_fields,
        estimated_cost_usd=estimate_analysis_cost(
            reviews_count=len(reviews),
            text_chars=text_chars,
        ),
    )
