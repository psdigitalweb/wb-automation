"""Tests for WS-G matcher-run retention.

Verifies:
* Newest N per SKU are kept.
* Runs inside the rolling window are kept.
* Runs referenced by non-preview ``SeoSkuQuerySet`` / ``SeoContentVersion``
  are kept even if older than both rules.
* Older unreferenced runs are deleted along with their ``SeoMatcherResult``
  rows.
* ``dry_run`` mode lists deletions without executing them.

The tests use an in-memory SQLite DB via the project's standard ``Base``
metadata so the contract is exercised end-to-end rather than mocked.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.models import (
    Base,
    SeoContentVersion,
    SeoMatcherResult,
    SeoMatcherRun,
    SeoSkuQuerySet,
)
from app.services.seo.matcher_retention import cleanup_matcher_runs


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    yield Session
    engine.dispose()


def _make_run(
    session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    started_at: datetime,
) -> SeoMatcherRun:
    run = SeoMatcherRun(
        project_id=project_id,
        category_id=category_id,
        nm_id=nm_id,
        matcher_version="v2",
        policy_version="p1",
        category_profile_version="812_v1",
        readiness_snapshot={},
        metrics={},
        started_at=started_at,
    )
    session.add(run)
    session.flush()
    session.add(
        SeoMatcherResult(
            run_id=int(run.id),
            query_display="q",
            normalized_query_text="q",
            bucket="primary",
            eligibility_verdict="ok",
            score=1,
            score_components={},
            matched_atoms=[],
            missing_atoms=[],
            conflict_atoms=[],
            reasons=[],
        )
    )
    session.flush()
    return run


def test_keeps_newest_n(session_factory) -> None:
    Session = session_factory
    session = Session()
    now = datetime.now(tz=timezone.utc)
    for idx in range(25):
        # All runs are > 30 days old so only the newest-N rule keeps them.
        _make_run(
            session,
            project_id=1,
            category_id=812,
            nm_id=100,
            started_at=now - timedelta(days=60 + idx),
        )
    report = cleanup_matcher_runs(session, keep_newest=20, keep_days=30)
    session.commit()
    remaining = session.scalars(select(SeoMatcherRun)).all()
    assert len(remaining) == 20
    assert report.scanned_runs == 25
    assert len(report.deleted_run_ids) == 5


def test_keeps_rolling_window(session_factory) -> None:
    Session = session_factory
    session = Session()
    now = datetime.now(tz=timezone.utc)
    for idx in range(10):
        _make_run(
            session,
            project_id=1,
            category_id=812,
            nm_id=100,
            started_at=now - timedelta(days=idx * 2),
        )
    # keep_newest=2 forces rows outside that count to rely on the window.
    report = cleanup_matcher_runs(session, keep_newest=2, keep_days=30)
    session.commit()
    remaining = session.scalars(select(SeoMatcherRun)).all()
    # Newest 10 are all within 30 days, so they must all be kept.
    assert len(remaining) == 10
    assert not report.deleted_run_ids


def test_keeps_referenced_runs(session_factory) -> None:
    Session = session_factory
    session = Session()
    now = datetime.now(tz=timezone.utc)
    # Create an old run and link a confirmed query-set row to it.
    pinned = _make_run(
        session,
        project_id=1,
        category_id=812,
        nm_id=100,
        started_at=now - timedelta(days=365),
    )
    session.add(
        SeoSkuQuerySet(
            project_id=1,
            category_id=812,
            nm_id=100,
            status="confirmed",
            matcher_run_id=int(pinned.id),
            approval_state="draft",
            trust_state="unverified",
        )
    )
    # Another old run NOT referenced — should be deleted.
    junk = _make_run(
        session,
        project_id=1,
        category_id=812,
        nm_id=100,
        started_at=now - timedelta(days=365),
    )
    # Fill up the quota above so neither of these survives on recency.
    for _ in range(25):
        _make_run(
            session,
            project_id=1,
            category_id=812,
            nm_id=101,
            started_at=now - timedelta(days=365),
        )

    report = cleanup_matcher_runs(session, keep_newest=5, keep_days=7)
    session.commit()

    surviving_ids = {int(r.id) for r in session.scalars(select(SeoMatcherRun)).all()}
    assert int(pinned.id) in surviving_ids
    assert int(junk.id) not in surviving_ids
    assert int(junk.id) in report.deleted_run_ids
    assert report.kept_by_reference_count >= 1


def test_non_preview_content_version_pins_run(session_factory) -> None:
    Session = session_factory
    session = Session()
    now = datetime.now(tz=timezone.utc)
    pinned = _make_run(
        session,
        project_id=1,
        category_id=812,
        nm_id=100,
        started_at=now - timedelta(days=365),
    )
    session.add(
        SeoContentVersion(
            project_id=1,
            category_id=812,
            nm_id=100,
            matcher_run_id=int(pinned.id),
            content_kind="candidate",
            status="needs_review",
        )
    )
    # Preview content does NOT pin.
    unpinned = _make_run(
        session,
        project_id=1,
        category_id=812,
        nm_id=100,
        started_at=now - timedelta(days=365),
    )
    session.add(
        SeoContentVersion(
            project_id=1,
            category_id=812,
            nm_id=100,
            matcher_run_id=int(unpinned.id),
            content_kind="preview",
            status="needs_review",
        )
    )
    session.flush()

    report = cleanup_matcher_runs(session, keep_newest=0, keep_days=7)
    session.commit()
    surviving = {int(r.id) for r in session.scalars(select(SeoMatcherRun)).all()}
    assert int(pinned.id) in surviving
    assert int(unpinned.id) not in surviving
    assert int(unpinned.id) in report.deleted_run_ids


def test_dry_run_lists_but_does_not_delete(session_factory) -> None:
    Session = session_factory
    session = Session()
    now = datetime.now(tz=timezone.utc)
    for _ in range(25):
        _make_run(
            session,
            project_id=1,
            category_id=812,
            nm_id=100,
            started_at=now - timedelta(days=120),
        )
    report = cleanup_matcher_runs(session, keep_newest=5, keep_days=7, dry_run=True)
    session.commit()
    assert report.dry_run is True
    assert len(report.deleted_run_ids) == 20
    remaining = session.scalars(select(SeoMatcherRun)).all()
    assert len(remaining) == 25


def test_deletes_result_rows_with_runs(session_factory) -> None:
    Session = session_factory
    session = Session()
    now = datetime.now(tz=timezone.utc)
    for idx in range(22):
        _make_run(
            session,
            project_id=1,
            category_id=812,
            nm_id=100,
            started_at=now - timedelta(days=120 + idx),
        )
    report = cleanup_matcher_runs(session, keep_newest=20, keep_days=7)
    session.commit()
    remaining_results = session.scalars(select(SeoMatcherResult)).all()
    assert len(remaining_results) == 20
    assert report.deleted_result_rows == 2
