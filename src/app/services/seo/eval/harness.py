"""Eval harness — Iteration 2 (WS-E).

Runs the candidate matcher against the seeded ``SeoEvalLabel`` rows for a
category, computes accuracy / precision / recall / bad-primary / hard-conflict
metrics, persists a ``SeoEvalRun`` trace, and updates
``SeoCategoryMatchingReadiness.eligibility_tier`` through the single-writer
helper :func:`update_eligibility_tier`.

Contract invariants (see
``docs/seo-module/implementation-plan/05_backend_contract_changes.md``):

* The eval harness is the ONLY writer of ``eligibility_tier``. No router /
  service outside this module may update that column. The single-writer
  check is asserted via
  ``tests/seo/test_seo_eval_harness.py::test_eligibility_tier_single_writer``.
* Promotion from ``evaluated`` to ``approved`` is NOT automatic in iteration
  2 — it requires explicit operator intent captured elsewhere (e.g. a
  promote endpoint with human review). The harness may DOWNGRADE an
  existing ``approved`` tier if a later eval fails thresholds, but it will
  never upgrade straight to ``approved``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import (
    SeoCategoryMatchingReadiness,
    SeoEvalLabel,
    SeoEvalRun,
    SeoMatcherResult,
    SeoMatcherRun,
)
from app.services.seo.query_pipeline import normalize_query_text


ELIGIBILITY_TIER_PREVIEW_ONLY = "preview_only"
ELIGIBILITY_TIER_EVALUATED = "evaluated"
ELIGIBILITY_TIER_APPROVED = "approved"


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


EVAL_THRESHOLDS = {
    "accuracy_min": _env_float("SEO_EVAL_ACCURACY_MIN", 0.85),
    "bad_primary_rate_max": _env_float("SEO_EVAL_BAD_PRIMARY_RATE_MAX", 0.05),
    "hard_conflict_primary_count_max": _env_float(
        "SEO_EVAL_HARD_CONFLICT_PRIMARY_MAX", 0.0
    ),
}


class EvalHarnessError(Exception):
    """Base error raised by the eval harness."""


@dataclass
class MatcherEvalResult:
    """Result bundle returned by :func:`run_matcher_eval`."""

    run_id: int
    verdict: str
    metrics: dict[str, float]
    thresholds: dict[str, float]
    matcher_run_ids: list[int]
    nm_ids: list[int]
    labels_used: int
    labels_missing: int


def _latest_matcher_run(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
) -> SeoMatcherRun | None:
    return session.scalars(
        select(SeoMatcherRun)
        .where(
            SeoMatcherRun.project_id == int(project_id),
            SeoMatcherRun.category_id == int(category_id),
            SeoMatcherRun.nm_id == int(nm_id),
        )
        .order_by(desc(SeoMatcherRun.started_at), desc(SeoMatcherRun.id))
    ).first()


def _results_for_run(session: Session, *, run_id: int) -> list[SeoMatcherResult]:
    return list(
        session.scalars(
            select(SeoMatcherResult).where(SeoMatcherResult.run_id == int(run_id))
        ).all()
    )


def _collect_matcher_runs(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_ids: Sequence[int] | None,
    matcher_run_ids: Sequence[int] | None,
) -> list[SeoMatcherRun]:
    """Resolve the caller's request into a concrete list of matcher runs.

    Preference order:
    1. Explicit ``matcher_run_ids`` (the caller is replaying a known set).
    2. Latest run per ``nm_id`` in ``nm_ids``.
    3. Latest run per distinct ``nm_id`` found in the labels (iteration-2 cap).
    """

    if matcher_run_ids:
        rows = session.scalars(
            select(SeoMatcherRun).where(
                SeoMatcherRun.project_id == int(project_id),
                SeoMatcherRun.category_id == int(category_id),
                SeoMatcherRun.id.in_([int(run_id) for run_id in matcher_run_ids]),
            )
        ).all()
        return list(rows)

    if nm_ids:
        runs: list[SeoMatcherRun] = []
        for nm_id in nm_ids:
            run = _latest_matcher_run(
                session, project_id=project_id, category_id=category_id, nm_id=int(nm_id)
            )
            if run is not None:
                runs.append(run)
        return runs

    return []


def _load_labels(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    label_set_id: int,
    nm_ids: Sequence[int] | None,
) -> list[SeoEvalLabel]:
    stmt = select(SeoEvalLabel).where(
        SeoEvalLabel.project_id == int(project_id),
        SeoEvalLabel.category_id == int(category_id),
        SeoEvalLabel.label_set_id == int(label_set_id),
    )
    if nm_ids:
        # SKU-scoped eval: include labels that target the SKU OR are global.
        stmt = stmt.where(
            (SeoEvalLabel.nm_id.in_([int(nm_id) for nm_id in nm_ids]))
            | (SeoEvalLabel.nm_id.is_(None))
        )
    return list(session.scalars(stmt).all())


def _compute_metrics(
    *,
    labels: Iterable[SeoEvalLabel],
    results_by_nm: Mapping[int, list[SeoMatcherResult]],
) -> tuple[dict[str, float], int, int]:
    """Return ``(metrics, labels_used, labels_missing)``.

    A label is considered "used" when a matcher result can be found for the
    exact normalized query inside the SKU's run. Labels without a matching
    matcher result are reported via ``labels_missing``.
    """

    # counters
    total_used = 0
    total_missing = 0
    correct = 0
    primary_true_positive = 0
    primary_predicted = 0
    primary_expected = 0
    bad_primary = 0  # predicted=primary but expected in {rejected}
    hard_conflict_primary = 0  # predicted=primary but matcher flagged conflict

    by_bucket: dict[str, int] = {}

    for label in labels:
        expected = str(label.expected_bucket or "").strip()
        if not expected:
            continue
        normalized = normalize_query_text(str(label.query_text_normalized or ""))
        if not normalized:
            total_missing += 1
            continue

        candidate_results: list[SeoMatcherResult] = []
        if label.nm_id is not None:
            candidate_results = results_by_nm.get(int(label.nm_id), [])
        else:
            # Global label — compare against every SKU-run we have.
            for rows in results_by_nm.values():
                candidate_results.extend(rows)

        match = next(
            (
                row
                for row in candidate_results
                if normalize_query_text(str(row.normalized_query_text or "")) == normalized
            ),
            None,
        )
        if match is None:
            total_missing += 1
            continue

        total_used += 1
        predicted = str(match.bucket)
        by_bucket[predicted] = by_bucket.get(predicted, 0) + 1

        if predicted == expected:
            correct += 1

        if expected == "primary":
            primary_expected += 1
        if predicted == "primary":
            primary_predicted += 1
            if expected == "primary":
                primary_true_positive += 1
            if expected == "rejected":
                bad_primary += 1
            if list(match.conflict_atoms or []):
                hard_conflict_primary += 1

    accuracy = (correct / total_used) if total_used else 0.0
    primary_precision = (
        primary_true_positive / primary_predicted if primary_predicted else 1.0
    )
    primary_recall = (
        primary_true_positive / primary_expected if primary_expected else 1.0
    )
    bad_primary_rate = (bad_primary / primary_predicted) if primary_predicted else 0.0

    metrics = {
        "labels_scored": float(total_used),
        "labels_missing": float(total_missing),
        "accuracy": round(accuracy, 4),
        "primary_precision": round(primary_precision, 4),
        "primary_recall": round(primary_recall, 4),
        "bad_primary_rate": round(bad_primary_rate, 4),
        "hard_conflict_primary_count": float(hard_conflict_primary),
        "primary_predicted": float(primary_predicted),
        "primary_expected": float(primary_expected),
        "buckets": dict(by_bucket),  # type: ignore[dict-item]
    }
    return metrics, total_used, total_missing


def _verdict_from_metrics(metrics: Mapping[str, float]) -> str:
    accuracy = float(metrics.get("accuracy", 0.0))
    bad_primary_rate = float(metrics.get("bad_primary_rate", 1.0))
    hard_conflict = float(metrics.get("hard_conflict_primary_count", 0.0))
    if (
        accuracy >= EVAL_THRESHOLDS["accuracy_min"]
        and bad_primary_rate <= EVAL_THRESHOLDS["bad_primary_rate_max"]
        and hard_conflict <= EVAL_THRESHOLDS["hard_conflict_primary_count_max"]
    ):
        return ELIGIBILITY_TIER_EVALUATED
    return ELIGIBILITY_TIER_PREVIEW_ONLY


def update_eligibility_tier(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    tier: str,
    _caller: str = "run_matcher_eval",
) -> None:
    """Single-writer helper for ``SeoCategoryMatchingReadiness.eligibility_tier``.

    This function is intentionally private to the eval package: every call
    site outside ``app.services.seo.eval`` constitutes a contract violation
    and is blocked by
    ``tests/seo/test_seo_eval_harness.py::test_eligibility_tier_single_writer``.
    """

    if _caller != "run_matcher_eval":
        raise EvalHarnessError(
            "eligibility_tier is written only by run_matcher_eval; "
            "found unauthorized caller: " + str(_caller)
        )

    readiness = session.scalars(
        select(SeoCategoryMatchingReadiness).where(
            SeoCategoryMatchingReadiness.project_id == int(project_id),
            SeoCategoryMatchingReadiness.category_id == int(category_id),
        )
    ).first()
    if readiness is None:
        # Create a row so the tier is recorded even before bootstrap ran.
        readiness = SeoCategoryMatchingReadiness(
            project_id=int(project_id),
            category_id=int(category_id),
            status="not_started",
            eligibility_tier=str(tier),
        )
        session.add(readiness)
        session.flush()
        return
    readiness.eligibility_tier = str(tier)
    session.flush()


def run_matcher_eval(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    label_set_id: int = 1,
    nm_ids: Sequence[int] | None = None,
    matcher_run_ids: Sequence[int] | None = None,
    created_by: str | None = None,
    notes: str | None = None,
) -> MatcherEvalResult:
    """Run matcher eval for the given ``(project_id, category_id)``.

    Writes one ``SeoEvalRun`` and calls :func:`update_eligibility_tier`
    exactly once. Does not mutate any matcher / generation state.
    """

    runs = _collect_matcher_runs(
        session,
        project_id=project_id,
        category_id=category_id,
        nm_ids=nm_ids,
        matcher_run_ids=matcher_run_ids,
    )

    results_by_nm: dict[int, list[SeoMatcherResult]] = {}
    resolved_run_ids: list[int] = []
    resolved_nm_ids: list[int] = []
    for run in runs:
        rows = _results_for_run(session, run_id=int(run.id))
        results_by_nm.setdefault(int(run.nm_id), []).extend(rows)
        resolved_run_ids.append(int(run.id))
        if int(run.nm_id) not in resolved_nm_ids:
            resolved_nm_ids.append(int(run.nm_id))

    nm_scope = list(resolved_nm_ids) if resolved_nm_ids else list(nm_ids or [])
    labels = _load_labels(
        session,
        project_id=project_id,
        category_id=category_id,
        label_set_id=label_set_id,
        nm_ids=nm_scope if nm_scope else None,
    )

    metrics, used, missing = _compute_metrics(
        labels=labels,
        results_by_nm=results_by_nm,
    )
    verdict = _verdict_from_metrics(metrics) if used > 0 else ELIGIBILITY_TIER_PREVIEW_ONLY

    eval_run = SeoEvalRun(
        project_id=int(project_id),
        category_id=int(category_id),
        label_set_id=int(label_set_id),
        metrics=dict(metrics),
        thresholds=dict(EVAL_THRESHOLDS),
        verdict=str(verdict),
        matcher_run_ids=list(resolved_run_ids),
        nm_ids=list(resolved_nm_ids),
        notes=notes,
        created_by=created_by,
    )
    session.add(eval_run)
    session.flush()

    update_eligibility_tier(
        session,
        project_id=project_id,
        category_id=category_id,
        tier=str(verdict),
    )

    return MatcherEvalResult(
        run_id=int(eval_run.id),
        verdict=str(verdict),
        metrics=dict(metrics),
        thresholds=dict(EVAL_THRESHOLDS),
        matcher_run_ids=list(resolved_run_ids),
        nm_ids=list(resolved_nm_ids),
        labels_used=int(used),
        labels_missing=int(missing),
    )


__all__ = [
    "ELIGIBILITY_TIER_APPROVED",
    "ELIGIBILITY_TIER_EVALUATED",
    "ELIGIBILITY_TIER_PREVIEW_ONLY",
    "EVAL_THRESHOLDS",
    "EvalHarnessError",
    "MatcherEvalResult",
    "run_matcher_eval",
    "update_eligibility_tier",
]
