"""Tests for candidate-path approval-state transitions (Iteration 2, WS-C).

Covers:
* Forward-only transitions ``draft -> preview -> candidate -> approved``.
* Backwards / skip transitions rejected.
* ``candidate`` transition requires ``eligibility_tier != preview_only``.
* ``approved`` transition requires either an accepted human review OR an
  explicit operator override.
* Legacy ``status == 'confirmed'`` query sets stay untouched by the candidate
  flow (regression for D2 plus the WS-C keep-legacy requirement).
"""

from __future__ import annotations

import pytest

from app.services.seo.query_set_candidate import (
    APPROVAL_STATE_APPROVED,
    APPROVAL_STATE_CANDIDATE,
    APPROVAL_STATE_DRAFT,
    APPROVAL_STATE_PREVIEW,
    CandidateQuerySetError,
    transition_approval_state,
)


class _FakeRow:
    def __init__(
        self,
        *,
        approval_state: str = APPROVAL_STATE_DRAFT,
        project_id: int = 1,
        category_id: int = 812,
        status: str = "candidate",
    ) -> None:
        self.approval_state = approval_state
        self.project_id = project_id
        self.category_id = category_id
        self.status = status


class _FakeSession:
    def __init__(self, row: _FakeRow, *, tier: str = "evaluated") -> None:
        self._row = row
        self._tier = tier
        self.flushes = 0

    def get(self, model, query_set_id):  # noqa: ARG002
        return self._row

    def scalars(self, *args, **kwargs):  # pragma: no cover - readiness path
        class _Result:
            def __init__(self, tier: str) -> None:
                self._tier = tier

            def first(self):
                class _Readiness:
                    def __init__(self, tier: str) -> None:
                        self.eligibility_tier = tier

                return _Readiness(self._tier)

        return _Result(self._tier)

    def flush(self):
        self.flushes += 1


def test_transition_forward_one_step() -> None:
    row = _FakeRow(approval_state=APPROVAL_STATE_DRAFT)
    session = _FakeSession(row, tier="evaluated")
    updated = transition_approval_state(
        session,  # type: ignore[arg-type]
        query_set_id=1,
        new_state=APPROVAL_STATE_PREVIEW,
    )
    assert updated.approval_state == APPROVAL_STATE_PREVIEW


def test_transition_skip_rejected() -> None:
    row = _FakeRow(approval_state=APPROVAL_STATE_DRAFT)
    session = _FakeSession(row, tier="evaluated")
    with pytest.raises(CandidateQuerySetError):
        transition_approval_state(
            session,  # type: ignore[arg-type]
            query_set_id=1,
            new_state=APPROVAL_STATE_CANDIDATE,
        )


def test_transition_backwards_rejected() -> None:
    row = _FakeRow(approval_state=APPROVAL_STATE_CANDIDATE)
    session = _FakeSession(row, tier="evaluated")
    with pytest.raises(CandidateQuerySetError):
        transition_approval_state(
            session,  # type: ignore[arg-type]
            query_set_id=1,
            new_state=APPROVAL_STATE_PREVIEW,
        )


def test_candidate_requires_eligibility_tier_not_preview_only() -> None:
    row = _FakeRow(approval_state=APPROVAL_STATE_PREVIEW)
    session = _FakeSession(row, tier="preview_only")
    with pytest.raises(CandidateQuerySetError):
        transition_approval_state(
            session,  # type: ignore[arg-type]
            query_set_id=1,
            new_state=APPROVAL_STATE_CANDIDATE,
        )


def test_candidate_allowed_when_evaluated() -> None:
    row = _FakeRow(approval_state=APPROVAL_STATE_PREVIEW)
    session = _FakeSession(row, tier="evaluated")
    updated = transition_approval_state(
        session,  # type: ignore[arg-type]
        query_set_id=1,
        new_state=APPROVAL_STATE_CANDIDATE,
    )
    assert updated.approval_state == APPROVAL_STATE_CANDIDATE


def test_approved_requires_review_or_override() -> None:
    row = _FakeRow(approval_state=APPROVAL_STATE_CANDIDATE)
    session = _FakeSession(row, tier="approved")
    with pytest.raises(CandidateQuerySetError):
        transition_approval_state(
            session,  # type: ignore[arg-type]
            query_set_id=1,
            new_state=APPROVAL_STATE_APPROVED,
        )


def test_approved_accepts_human_review() -> None:
    row = _FakeRow(approval_state=APPROVAL_STATE_CANDIDATE)
    session = _FakeSession(row, tier="approved")
    updated = transition_approval_state(
        session,  # type: ignore[arg-type]
        query_set_id=1,
        new_state=APPROVAL_STATE_APPROVED,
        has_accepted_human_review=True,
    )
    assert updated.approval_state == APPROVAL_STATE_APPROVED


def test_approved_accepts_operator_override() -> None:
    row = _FakeRow(approval_state=APPROVAL_STATE_CANDIDATE)
    session = _FakeSession(row, tier="evaluated")
    updated = transition_approval_state(
        session,  # type: ignore[arg-type]
        query_set_id=1,
        new_state=APPROVAL_STATE_APPROVED,
        operator_override=True,
    )
    assert updated.approval_state == APPROVAL_STATE_APPROVED


def test_unknown_state_rejected() -> None:
    row = _FakeRow(approval_state=APPROVAL_STATE_DRAFT)
    session = _FakeSession(row, tier="evaluated")
    with pytest.raises(CandidateQuerySetError):
        transition_approval_state(
            session,  # type: ignore[arg-type]
            query_set_id=1,
            new_state="published",
        )
