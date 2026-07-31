"""Tests for WS-D content-version promotion gates.

Covers:
* ``preview -> candidate`` requires an accepted human review and
  ``eligibility_tier in {evaluated, approved}``.
* ``candidate -> approved`` requires a *second* accepted human review and
  ``eligibility_tier == approved``.
* ``approved -> published`` is refused (production generation OFF in
  Iteration 2).
* Transitions are strictly forward-only and single-step.
* Legacy ``llm_draft`` content is treated as ``preview`` for transition
  purposes.
"""

from __future__ import annotations

import pytest

from app.services.seo.generation.promotion import (
    CONTENT_KIND_APPROVED,
    CONTENT_KIND_CANDIDATE,
    CONTENT_KIND_LEGACY_LLM_DRAFT,
    CONTENT_KIND_PREVIEW,
    CONTENT_KIND_PUBLISHED,
    GenerationPromotionError,
    promote_content_version,
)


class _FakeContent:
    def __init__(self, *, content_kind: str, project_id: int = 1, category_id: int = 812) -> None:
        self.id = 42
        self.content_kind = content_kind
        self.project_id = project_id
        self.category_id = category_id


class _FakeReview:
    def __init__(self, review_id: int) -> None:
        self.id = review_id


class _Scalars:
    def __init__(self, rows):
        self._rows = list(rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(
        self,
        *,
        content: _FakeContent,
        tier: str,
        accepted_reviews: list[_FakeReview] | None = None,
    ) -> None:
        self._content = content
        self._tier = tier
        self._reviews = list(accepted_reviews or [])
        self.flushes = 0

    def get(self, model, oid):  # noqa: ARG002
        return self._content

    def scalars(self, stmt):
        # The harness makes two distinct queries: readiness + accepted reviews.
        # We use the compiled text shape to tell them apart in a brittle-but-
        # sufficient way for tests.
        sql = str(stmt)
        if "seo_category_matching_readiness" in sql:
            class _R:
                def __init__(self, tier): self.eligibility_tier = tier
            return _Scalars([_R(self._tier)])
        if "seo_generation_human_review" in sql:
            return _Scalars(self._reviews)
        return _Scalars([])

    def flush(self):
        self.flushes += 1


def test_preview_to_candidate_requires_review() -> None:
    content = _FakeContent(content_kind=CONTENT_KIND_PREVIEW)
    session = _FakeSession(content=content, tier="evaluated", accepted_reviews=[])
    with pytest.raises(GenerationPromotionError):
        promote_content_version(
            session,  # type: ignore[arg-type]
            content_version_id=42,
            target_kind=CONTENT_KIND_CANDIDATE,
        )


def test_preview_to_candidate_requires_evaluated_tier() -> None:
    content = _FakeContent(content_kind=CONTENT_KIND_PREVIEW)
    session = _FakeSession(
        content=content, tier="preview_only", accepted_reviews=[_FakeReview(1)]
    )
    with pytest.raises(GenerationPromotionError):
        promote_content_version(
            session,  # type: ignore[arg-type]
            content_version_id=42,
            target_kind=CONTENT_KIND_CANDIDATE,
        )


def test_preview_to_candidate_ok() -> None:
    content = _FakeContent(content_kind=CONTENT_KIND_PREVIEW)
    session = _FakeSession(
        content=content, tier="evaluated", accepted_reviews=[_FakeReview(7)]
    )
    result = promote_content_version(
        session,  # type: ignore[arg-type]
        content_version_id=42,
        target_kind=CONTENT_KIND_CANDIDATE,
    )
    assert result.new_content_kind == CONTENT_KIND_CANDIDATE
    assert result.human_review_id == 7


def test_legacy_llm_draft_treated_as_preview() -> None:
    content = _FakeContent(content_kind=CONTENT_KIND_LEGACY_LLM_DRAFT)
    session = _FakeSession(
        content=content, tier="evaluated", accepted_reviews=[_FakeReview(3)]
    )
    result = promote_content_version(
        session,  # type: ignore[arg-type]
        content_version_id=42,
        target_kind=CONTENT_KIND_CANDIDATE,
    )
    assert result.new_content_kind == CONTENT_KIND_CANDIDATE


def test_candidate_to_approved_requires_tier_approved() -> None:
    content = _FakeContent(content_kind=CONTENT_KIND_CANDIDATE)
    session = _FakeSession(
        content=content,
        tier="evaluated",
        accepted_reviews=[_FakeReview(1), _FakeReview(2)],
    )
    with pytest.raises(GenerationPromotionError):
        promote_content_version(
            session,  # type: ignore[arg-type]
            content_version_id=42,
            target_kind=CONTENT_KIND_APPROVED,
        )


def test_candidate_to_approved_requires_two_accepted_reviews() -> None:
    content = _FakeContent(content_kind=CONTENT_KIND_CANDIDATE)
    session = _FakeSession(
        content=content, tier="approved", accepted_reviews=[_FakeReview(1)]
    )
    with pytest.raises(GenerationPromotionError):
        promote_content_version(
            session,  # type: ignore[arg-type]
            content_version_id=42,
            target_kind=CONTENT_KIND_APPROVED,
        )


def test_candidate_to_approved_ok() -> None:
    content = _FakeContent(content_kind=CONTENT_KIND_CANDIDATE)
    session = _FakeSession(
        content=content,
        tier="approved",
        accepted_reviews=[_FakeReview(2), _FakeReview(1)],
    )
    result = promote_content_version(
        session,  # type: ignore[arg-type]
        content_version_id=42,
        target_kind=CONTENT_KIND_APPROVED,
    )
    assert result.new_content_kind == CONTENT_KIND_APPROVED


def test_approved_to_published_refused() -> None:
    content = _FakeContent(content_kind=CONTENT_KIND_APPROVED)
    session = _FakeSession(content=content, tier="approved", accepted_reviews=[])
    with pytest.raises(GenerationPromotionError) as excinfo:
        promote_content_version(
            session,  # type: ignore[arg-type]
            content_version_id=42,
            target_kind=CONTENT_KIND_PUBLISHED,
        )
    assert "published" in str(excinfo.value).lower()


def test_skip_transition_rejected() -> None:
    content = _FakeContent(content_kind=CONTENT_KIND_PREVIEW)
    session = _FakeSession(content=content, tier="approved", accepted_reviews=[])
    with pytest.raises(GenerationPromotionError):
        promote_content_version(
            session,  # type: ignore[arg-type]
            content_version_id=42,
            target_kind=CONTENT_KIND_APPROVED,
        )


def test_unknown_target_rejected() -> None:
    content = _FakeContent(content_kind=CONTENT_KIND_PREVIEW)
    session = _FakeSession(content=content, tier="approved", accepted_reviews=[])
    with pytest.raises(GenerationPromotionError):
        promote_content_version(
            session,  # type: ignore[arg-type]
            content_version_id=42,
            target_kind="archived",
        )
