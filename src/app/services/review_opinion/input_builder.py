"""Build a privacy-minimized, deterministic review-opinion input."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.db import engine


MAX_REVIEWS_SENT = 300
MAX_FIELD_CHARS = 1200
_SPACE_RE = re.compile(r"\s+")
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?7|8)[\s()\-]*\d{3}[\s()\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}(?!\d)")


@dataclass(frozen=True)
class ReviewOpinionInput:
    project_id: int
    nm_id: int
    product_title: str
    reviews_total: int
    reviews_with_text: int
    reviews_sent: int
    input_hash: str
    payload: dict[str, Any]
    review_fields: dict[str, tuple[str, ...]]


def normalize_text(value: Any) -> str:
    normalized = _SPACE_RE.sub(" ", str(value or "")).strip()
    normalized = _EMAIL_RE.sub("[email удалён]", normalized)
    normalized = _PHONE_RE.sub("[телефон удалён]", normalized)
    return normalized[:MAX_FIELD_CHARS]


def _select_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(rows) <= limit:
        return rows

    by_rating: dict[int, list[dict[str, Any]]] = {rating: [] for rating in range(1, 6)}
    other: list[dict[str, Any]] = []
    for row in rows:
        rating = row.get("rating")
        if isinstance(rating, int) and rating in by_rating:
            by_rating[rating].append(row)
        else:
            other.append(row)

    selected: list[dict[str, Any]] = []
    per_rating = max(1, limit // 5)
    remaining: list[dict[str, Any]] = []
    for rating in range(1, 6):
        selected.extend(by_rating[rating][:per_rating])
        remaining.extend(by_rating[rating][per_rating:])
    remaining.extend(other)
    selected.extend(remaining[: max(0, limit - len(selected))])
    return sorted(selected[:limit], key=lambda item: (str(item.get("created_date") or ""), str(item["external_id"])))


def build_review_opinion_input(project_id: int, nm_id: int) -> ReviewOpinionInput:
    """Read only written reviews and build an anonymized stable payload."""

    product_sql = text(
        """
        SELECT title
        FROM products
        WHERE project_id = :project_id AND nm_id = :nm_id
        LIMIT 1
        """
    )
    counts_sql = text(
        """
        SELECT
            COUNT(*)::int AS reviews_total,
            COUNT(*) FILTER (
                WHERE NULLIF(BTRIM(CONCAT_WS(
                    ' ',
                    COALESCE(raw->>'text', ''),
                    COALESCE(raw->>'pros', ''),
                    COALESCE(raw->>'cons', '')
                )), '') IS NOT NULL
            )::int AS reviews_with_text
        FROM wb_feedback_snapshots
        WHERE project_id = :project_id AND nm_id = :nm_id
        """
    )
    reviews_sql = text(
        """
        SELECT
            external_id,
            created_date,
            product_valuation AS rating,
            raw->>'text' AS review_text,
            raw->>'pros' AS pros,
            raw->>'cons' AS cons
        FROM wb_feedback_snapshots
        WHERE project_id = :project_id
          AND nm_id = :nm_id
          AND NULLIF(BTRIM(CONCAT_WS(
                ' ',
                COALESCE(raw->>'text', ''),
                COALESCE(raw->>'pros', ''),
                COALESCE(raw->>'cons', '')
          )), '') IS NOT NULL
        ORDER BY created_date ASC NULLS LAST, external_id ASC
        """
    )
    params = {"project_id": int(project_id), "nm_id": int(nm_id)}
    with engine.connect() as conn:
        product_row = conn.execute(product_sql, params).mappings().first()
        if product_row is None:
            raise LookupError("product_not_found")
        counts = conn.execute(counts_sql, params).mappings().one()
        raw_rows = [dict(row) for row in conn.execute(reviews_sql, params).mappings().all()]

    normalized_rows: list[dict[str, Any]] = []
    seen_content: set[str] = set()
    for row in raw_rows:
        fields = {
            "text": normalize_text(row.get("review_text")),
            "pros": normalize_text(row.get("pros")),
            "cons": normalize_text(row.get("cons")),
        }
        content_key = json.dumps(fields, ensure_ascii=False, sort_keys=True)
        if content_key in seen_content:
            continue
        seen_content.add(content_key)
        normalized_rows.append(
            {
                "external_id": str(row["external_id"]),
                "created_date": (
                    row["created_date"].date().isoformat()
                    if getattr(row.get("created_date"), "date", None)
                    else str(row.get("created_date") or "")[:10] or None
                ),
                "rating": int(row["rating"]) if row.get("rating") is not None else None,
                **fields,
            }
        )

    selected = _select_rows(normalized_rows, MAX_REVIEWS_SENT)
    reviews: list[dict[str, Any]] = []
    review_fields: dict[str, tuple[str, ...]] = {}
    for index, row in enumerate(selected, start=1):
        review_id = f"r_{index:04d}"
        reviews.append(
            {
                "review_id": review_id,
                "rating": row["rating"],
                "created_date": row["created_date"],
                "text": row["text"] or None,
                "pros": row["pros"] or None,
                "cons": row["cons"] or None,
            }
        )
        review_fields[review_id] = tuple(
            value for value in (row["text"], row["pros"], row["cons"]) if value
        )

    payload = {
        "task": "extract_customer_opinion",
        "language": "ru",
        "product": {
            "nm_id": int(nm_id),
            "title": str(product_row.get("title") or ""),
        },
        "analysis_scope": {
            "type": "all_time",
            "reviews_total": int(counts["reviews_total"] or 0),
            "reviews_with_text": int(counts["reviews_with_text"] or 0),
            "reviews_sent": len(reviews),
        },
        "reviews": reviews,
    }
    input_hash = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ReviewOpinionInput(
        project_id=int(project_id),
        nm_id=int(nm_id),
        product_title=str(product_row.get("title") or ""),
        reviews_total=int(counts["reviews_total"] or 0),
        reviews_with_text=int(counts["reviews_with_text"] or 0),
        reviews_sent=len(reviews),
        input_hash=input_hash,
        payload=payload,
        review_fields=review_fields,
    )
