"""Matcher-run retention cleanup (Iteration 2, WS-G).

Keeps the ``seo_matcher_runs`` / ``seo_matcher_results`` trace tables from
growing unbounded in preview-heavy workloads while still preserving any run
that a non-preview downstream record (``SeoSkuQuerySet`` or
``SeoContentVersion``) still references.

Rule (from the Iteration 2 pre-kickoff D5 decision):

* Keep the newest 20 runs per ``(project_id, category_id, nm_id)`` OR any
  run started in the last 30 days, whichever is larger.
* Exclude any run whose ``id`` is referenced by:
    - ``SeoSkuQuerySet.matcher_run_id`` where ``status != 'draft'`` and
      ``approval_state != 'draft'`` and ``status != 'candidate' OR
      approval_state != 'preview'``. In practice that means confirmed
      legacy rows, candidates that have crossed at least
      ``preview -> candidate``, and approved rows.
    - ``SeoContentVersion.matcher_run_id`` where ``content_kind != 'preview'``
      and ``content_kind != 'llm_draft'`` (legacy preview).

This is intentionally simple — no archival, no partitioning, no pin system.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.models import (
    SeoContentVersion,
    SeoMatcherResult,
    SeoMatcherRun,
    SeoSkuQuerySet,
)


KEEP_NEWEST_PER_SKU = 20
KEEP_WINDOW_DAYS = 30

_PREVIEW_CONTENT_KINDS = {"preview", "llm_draft"}


@dataclass
class RetentionReport:
    scanned_runs: int
    kept_by_recency_count: int
    kept_by_reference_count: int
    deleted_run_ids: list[int]
    deleted_result_rows: int
    dry_run: bool


def _referenced_run_ids(session: Session) -> set[int]:
    """Return every matcher-run id that a non-preview downstream row pins."""

    referenced: set[int] = set()

    # Legacy confirmed query sets always pin their run.
    legacy_confirmed_rows = session.execute(
        select(SeoSkuQuerySet.matcher_run_id).where(
            SeoSkuQuerySet.matcher_run_id.is_not(None),
            SeoSkuQuerySet.status == "confirmed",
        )
    ).all()
    referenced.update(int(row[0]) for row in legacy_confirmed_rows if row[0] is not None)

    # Candidate query sets pin their run once they've crossed preview.
    candidate_rows = session.execute(
        select(SeoSkuQuerySet.matcher_run_id).where(
            SeoSkuQuerySet.matcher_run_id.is_not(None),
            SeoSkuQuerySet.status == "candidate",
            SeoSkuQuerySet.approval_state.in_(("candidate", "approved")),
        )
    ).all()
    referenced.update(int(row[0]) for row in candidate_rows if row[0] is not None)

    # Non-preview content versions pin their run.
    content_rows = session.execute(
        select(SeoContentVersion.matcher_run_id).where(
            SeoContentVersion.matcher_run_id.is_not(None),
            SeoContentVersion.content_kind.not_in(_PREVIEW_CONTENT_KINDS),
        )
    ).all()
    referenced.update(int(row[0]) for row in content_rows if row[0] is not None)

    return referenced


def cleanup_matcher_runs(
    session: Session,
    *,
    dry_run: bool = False,
    now: datetime | None = None,
    keep_newest: int = KEEP_NEWEST_PER_SKU,
    keep_days: int = KEEP_WINDOW_DAYS,
) -> RetentionReport:
    """Apply retention to ``seo_matcher_runs`` / ``seo_matcher_results``.

    The deletion runs in a single transaction; callers should wrap this in
    their own commit/rollback as usual. On ``dry_run=True`` no rows are
    deleted, but the report lists exactly what would have been removed.
    """

    now_utc = now or datetime.now(tz=timezone.utc)
    cutoff = now_utc - timedelta(days=int(keep_days))

    runs = list(
        session.scalars(
            select(SeoMatcherRun).order_by(
                SeoMatcherRun.project_id.asc(),
                SeoMatcherRun.category_id.asc(),
                SeoMatcherRun.nm_id.asc(),
                desc(SeoMatcherRun.started_at),
                desc(SeoMatcherRun.id),
            )
        ).all()
    )

    referenced = _referenced_run_ids(session)

    buckets: dict[tuple[int, int, int], list[SeoMatcherRun]] = {}
    for run in runs:
        key = (int(run.project_id), int(run.category_id), int(run.nm_id))
        buckets.setdefault(key, []).append(run)

    to_delete: list[int] = []
    kept_recency = 0
    kept_reference = 0
    scanned = 0

    for _key, ordered in buckets.items():
        for idx, run in enumerate(ordered):
            scanned += 1
            started = run.started_at
            if started is not None and started.tzinfo is None:
                # DB returned naive datetime — treat as UTC.
                started = started.replace(tzinfo=timezone.utc)
            within_window = started is not None and started >= cutoff
            within_count = idx < int(keep_newest)

            if within_window or within_count:
                kept_recency += 1
                continue
            if int(run.id) in referenced:
                kept_reference += 1
                continue
            to_delete.append(int(run.id))

    deleted_result_rows = 0
    if to_delete and not dry_run:
        result = session.execute(
            delete(SeoMatcherResult).where(SeoMatcherResult.run_id.in_(to_delete))
        )
        deleted_result_rows = int(result.rowcount or 0)
        session.execute(
            delete(SeoMatcherRun).where(SeoMatcherRun.id.in_(to_delete))
        )
        session.flush()

    return RetentionReport(
        scanned_runs=scanned,
        kept_by_recency_count=kept_recency,
        kept_by_reference_count=kept_reference,
        deleted_run_ids=list(to_delete),
        deleted_result_rows=deleted_result_rows,
        dry_run=bool(dry_run),
    )


__all__ = [
    "KEEP_NEWEST_PER_SKU",
    "KEEP_WINDOW_DAYS",
    "RetentionReport",
    "cleanup_matcher_runs",
]
