"""Content-version lifecycle promotion (Iteration 2, WS-D).

This module owns the server-enforced state machine for
``SeoContentVersion.content_kind``. External callers must go through
:func:`promote_content_version`; direct writes to ``content_kind`` from
anywhere else than the generation service's initial insert are forbidden.

Contract:

* Transitions are forward-only and single-step:
    ``preview -> candidate -> approved -> published``
  (``published`` is unreachable in Iteration 2 — production generation stays
  OFF — and always returns a 409 from the router.)
* ``preview -> candidate`` requires
    - ``SeoCategoryMatchingReadiness.eligibility_tier in {'evaluated', 'approved'}``
    - a ``SeoGenerationHumanReview`` with ``verdict='accept'`` for the content
      version.
* ``candidate -> approved`` requires
    - ``SeoCategoryMatchingReadiness.eligibility_tier == 'approved'``
    - a *second* ``SeoGenerationHumanReview`` with ``verdict='accept'``
      created after the previous promotion (the promote endpoint rejects the
      case where only the earlier review exists).
* ``approved -> published`` is refused with reason ``production_generation_off``.
* Human review records are append-only. The promote flow never mutates them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import (
    SeoCategoryMatchingReadiness,
    SeoContentVersion,
    SeoGenerationHumanReview,
)


CONTENT_KIND_PREVIEW = "preview"
CONTENT_KIND_CANDIDATE = "candidate"
CONTENT_KIND_APPROVED = "approved"
CONTENT_KIND_PUBLISHED = "published"
# Iteration 1 legacy rows carry this label; treated as ``preview`` for
# transition purposes until Iteration 3 drops the legacy value.
CONTENT_KIND_LEGACY_LLM_DRAFT = "llm_draft"

_CONTENT_KIND_ORDER = {
    CONTENT_KIND_PREVIEW: 0,
    CONTENT_KIND_CANDIDATE: 1,
    CONTENT_KIND_APPROVED: 2,
    CONTENT_KIND_PUBLISHED: 3,
}

HUMAN_REVIEW_VERDICT_ACCEPT = "accept"
HUMAN_REVIEW_VERDICT_REJECT = "reject"
HUMAN_REVIEW_VERDICT_NEEDS_CHANGES = "needs_changes"


class GenerationPromotionError(Exception):
    """Base error for WS-D promotion failures."""


@dataclass
class PromotionResult:
    content_version_id: int
    previous_content_kind: str
    new_content_kind: str
    eligibility_tier: str
    human_review_id: int | None


def _normalize_kind(raw: str | None) -> str:
    value = str(raw or "").strip().lower()
    if value == CONTENT_KIND_LEGACY_LLM_DRAFT:
        return CONTENT_KIND_PREVIEW
    return value


def _readiness_tier(session: Session, *, project_id: int, category_id: int) -> str:
    readiness = session.scalars(
        select(SeoCategoryMatchingReadiness).where(
            SeoCategoryMatchingReadiness.project_id == int(project_id),
            SeoCategoryMatchingReadiness.category_id == int(category_id),
        )
    ).first()
    if readiness is None:
        return "preview_only"
    return str(readiness.eligibility_tier or "preview_only")


def _latest_accepted_reviews(
    session: Session, *, content_version_id: int
) -> list[SeoGenerationHumanReview]:
    rows = session.scalars(
        select(SeoGenerationHumanReview)
        .where(
            SeoGenerationHumanReview.content_version_id == int(content_version_id),
            SeoGenerationHumanReview.verdict == HUMAN_REVIEW_VERDICT_ACCEPT,
        )
        .order_by(
            desc(SeoGenerationHumanReview.created_at),
            desc(SeoGenerationHumanReview.id),
        )
    ).all()
    return list(rows)


def record_human_review(
    session: Session,
    *,
    content_version_id: int,
    reviewer: str | None,
    verdict: str,
    rubric: dict | None = None,
    notes: str | None = None,
) -> SeoGenerationHumanReview:
    """Append a ``SeoGenerationHumanReview`` row. Called by the promote flow."""

    verdict_norm = str(verdict or "").strip().lower()
    if verdict_norm not in {
        HUMAN_REVIEW_VERDICT_ACCEPT,
        HUMAN_REVIEW_VERDICT_REJECT,
        HUMAN_REVIEW_VERDICT_NEEDS_CHANGES,
    }:
        raise GenerationPromotionError(
            f"Unknown human review verdict: {verdict!r}; "
            "must be accept | reject | needs_changes"
        )
    content = session.get(SeoContentVersion, int(content_version_id))
    if content is None:
        raise GenerationPromotionError(
            f"Content version {content_version_id} not found"
        )
    row = SeoGenerationHumanReview(
        content_version_id=int(content_version_id),
        reviewer=reviewer,
        rubric=dict(rubric or {}),
        verdict=verdict_norm,
        notes=notes,
    )
    session.add(row)
    session.flush()
    return row


def _validate_preview_to_candidate(
    *, tier: str, accepted_reviews: Iterable[SeoGenerationHumanReview]
) -> SeoGenerationHumanReview:
    if tier not in {"evaluated", "approved"}:
        raise GenerationPromotionError(
            "Cannot promote preview -> candidate: category eligibility_tier is "
            f"{tier!r}; run matcher eval first."
        )
    reviews = list(accepted_reviews)
    if not reviews:
        raise GenerationPromotionError(
            "Cannot promote preview -> candidate: no accepted human review "
            "recorded for this content version."
        )
    return reviews[0]


def _validate_candidate_to_approved(
    *, tier: str, accepted_reviews: Iterable[SeoGenerationHumanReview]
) -> SeoGenerationHumanReview:
    if tier != "approved":
        raise GenerationPromotionError(
            "Cannot promote candidate -> approved: category eligibility_tier "
            f"must be 'approved'; got {tier!r}."
        )
    reviews = list(accepted_reviews)
    if len(reviews) < 2:
        raise GenerationPromotionError(
            "Cannot promote candidate -> approved: a second accepted human "
            "review is required after the preview -> candidate promotion."
        )
    return reviews[0]


def promote_content_version(
    session: Session,
    *,
    content_version_id: int,
    target_kind: str,
) -> PromotionResult:
    """Promote a ``SeoContentVersion`` through the WS-D lifecycle.

    The promote endpoint is the *only* caller of this function outside tests.
    """

    content = session.get(SeoContentVersion, int(content_version_id))
    if content is None:
        raise GenerationPromotionError(
            f"Content version {content_version_id} not found"
        )

    current = _normalize_kind(content.content_kind)
    target = _normalize_kind(target_kind)

    if target == CONTENT_KIND_PUBLISHED:
        # Iteration 2 pre-kickoff D4: production generation OFF, no publish
        # flow. The endpoint surfaces this as 409 so the UI can render a
        # clear reason.
        raise GenerationPromotionError(
            "Promotion to 'published' is refused: production generation is "
            "disabled for Iteration 2 (SEO_GENERATION_PREVIEW_ENABLED=off in "
            "production)."
        )

    if target not in _CONTENT_KIND_ORDER:
        raise GenerationPromotionError(
            f"Unknown target content_kind: {target_kind!r}"
        )

    cur_order = _CONTENT_KIND_ORDER.get(current, -1)
    tgt_order = _CONTENT_KIND_ORDER[target]
    if tgt_order - cur_order != 1:
        raise GenerationPromotionError(
            f"Illegal content_kind transition {current!r} -> {target!r}; "
            "only single-step forward promotions are allowed "
            "(preview -> candidate -> approved)."
        )

    tier = _readiness_tier(
        session,
        project_id=int(content.project_id),
        category_id=int(content.category_id),
    )
    accepted = _latest_accepted_reviews(
        session, content_version_id=int(content_version_id)
    )

    review_used: SeoGenerationHumanReview | None = None
    if target == CONTENT_KIND_CANDIDATE:
        review_used = _validate_preview_to_candidate(tier=tier, accepted_reviews=accepted)
    elif target == CONTENT_KIND_APPROVED:
        review_used = _validate_candidate_to_approved(tier=tier, accepted_reviews=accepted)

    previous = str(content.content_kind or "")
    content.content_kind = target
    session.flush()

    return PromotionResult(
        content_version_id=int(content.id),
        previous_content_kind=previous,
        new_content_kind=target,
        eligibility_tier=tier,
        human_review_id=int(review_used.id) if review_used is not None else None,
    )


__all__ = [
    "CONTENT_KIND_APPROVED",
    "CONTENT_KIND_CANDIDATE",
    "CONTENT_KIND_LEGACY_LLM_DRAFT",
    "CONTENT_KIND_PREVIEW",
    "CONTENT_KIND_PUBLISHED",
    "GenerationPromotionError",
    "HUMAN_REVIEW_VERDICT_ACCEPT",
    "HUMAN_REVIEW_VERDICT_NEEDS_CHANGES",
    "HUMAN_REVIEW_VERDICT_REJECT",
    "PromotionResult",
    "promote_content_version",
    "record_human_review",
]
