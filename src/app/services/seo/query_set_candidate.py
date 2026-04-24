"""Candidate-path query-set projection (Iteration 2, WS-C).

This module owns the *candidate* ``SeoSkuQuerySet`` row (``status='candidate'``).
It is distinct from the legacy ``draft`` / ``confirmed`` rows written by
``app.services.seo.products.run_query_selection`` / ``update_query_selection``.

Contract (see
``docs/seo-module/implementation-plan/05_backend_contract_changes.md`` §C):

* The source of truth for the candidate UI is the projected query set, not
  ``SeoMatcherResult``. The trace tables stay immutable.
* Legal ``approval_state`` transitions: ``draft -> preview -> candidate -> approved``
  and no reverse / skipping. The ``approved`` transition requires either an
  accepted ``seo_generation_human_review`` on the SKU OR an explicit operator
  override flag recorded by the caller.
* ``trust_state`` is set to ``validated`` only by the eval-driven flow via
  :func:`mark_query_set_validated` once
  ``SeoCategoryMatchingReadiness.eligibility_tier`` is not ``preview_only``.
  It is never written by the legacy selection path.
* ``category_profile_version`` mirrors the matcher run's
  ``category_profile_version`` so downstream generation can quote the exact
  profile version used for the candidate selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from app.models import (
    SeoCategoryMatchingReadiness,
    SeoMatcherResult,
    SeoMatcherRun,
    SeoSkuQuerySet,
    SeoSkuQuerySetItem,
)
from app.services.seo.query_pipeline import normalize_query_text


CANDIDATE_QUERYSET_STATUS = "candidate"

APPROVAL_STATE_DRAFT = "draft"
APPROVAL_STATE_PREVIEW = "preview"
APPROVAL_STATE_CANDIDATE = "candidate"
APPROVAL_STATE_APPROVED = "approved"

_APPROVAL_STATE_ORDER = {
    APPROVAL_STATE_DRAFT: 0,
    APPROVAL_STATE_PREVIEW: 1,
    APPROVAL_STATE_CANDIDATE: 2,
    APPROVAL_STATE_APPROVED: 3,
}

TRUST_STATE_UNVERIFIED = "unverified"
TRUST_STATE_VALIDATED = "validated"


class CandidateQuerySetError(Exception):
    """Base error for candidate query-set operations."""


@dataclass
class CandidateProjectionResult:
    query_set_id: int
    matcher_run_id: int
    items_written: int
    approval_state: str
    trust_state: str
    category_profile_version: str | None


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


def _matcher_results(session: Session, *, run_id: int) -> list[SeoMatcherResult]:
    return list(
        session.scalars(
            select(SeoMatcherResult).where(SeoMatcherResult.run_id == int(run_id))
        ).all()
    )


def _selection_state_for_bucket(bucket: str) -> str:
    return "auto_selected" if bucket in {"primary", "secondary"} else "excluded"


def _find_candidate_query_set(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
) -> SeoSkuQuerySet | None:
    return session.scalars(
        select(SeoSkuQuerySet).where(
            SeoSkuQuerySet.project_id == int(project_id),
            SeoSkuQuerySet.category_id == int(category_id),
            SeoSkuQuerySet.nm_id == int(nm_id),
            SeoSkuQuerySet.status == CANDIDATE_QUERYSET_STATUS,
        )
    ).first()


def project_matcher_run_into_query_set(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    matcher_run_id: int | None = None,
) -> CandidateProjectionResult:
    """Project a (candidate) ``SeoMatcherRun`` trace into ``SeoSkuQuerySet``.

    Creates/updates the ``status='candidate'`` row. Never touches the legacy
    ``draft`` or ``confirmed`` rows. ``approval_state`` starts at ``preview``
    on creation so the operator can inspect it without it counting as a
    selection; promote via :func:`transition_approval_state` from there.
    """

    if matcher_run_id is not None:
        run = session.scalars(
            select(SeoMatcherRun).where(
                SeoMatcherRun.id == int(matcher_run_id),
                SeoMatcherRun.project_id == int(project_id),
                SeoMatcherRun.category_id == int(category_id),
                SeoMatcherRun.nm_id == int(nm_id),
            )
        ).first()
    else:
        run = _latest_matcher_run(
            session,
            project_id=project_id,
            category_id=category_id,
            nm_id=nm_id,
        )
    if run is None:
        raise CandidateQuerySetError(
            f"No matcher_v2 run found for project={project_id} "
            f"category={category_id} nm_id={nm_id}"
        )

    profile_version: str | None = None
    metrics = getattr(run, "metrics", None) or {}
    if isinstance(metrics, dict):
        profile_version = metrics.get("category_profile_version") or None

    results = _matcher_results(session, run_id=int(run.id))

    query_set = _find_candidate_query_set(
        session,
        project_id=project_id,
        category_id=category_id,
        nm_id=nm_id,
    )
    initial_approval = APPROVAL_STATE_PREVIEW
    if query_set is None:
        query_set = SeoSkuQuerySet(
            project_id=int(project_id),
            category_id=int(category_id),
            nm_id=int(nm_id),
            status=CANDIDATE_QUERYSET_STATUS,
            approval_state=initial_approval,
            trust_state=TRUST_STATE_UNVERIFIED,
        )
        session.add(query_set)
        session.flush()

    # Keep whatever approval_state the operator has already reached. A
    # re-projection must not silently revert an explicit approval; it DOES
    # refresh the backing items so the operator sees the latest matcher
    # trace. If approval_state was ``approved`` and the underlying run
    # changes, we only downgrade trust_state back to ``unverified`` because
    # any prior eval verdict no longer applies to this new trace.
    if query_set.approval_state in (None, ""):
        query_set.approval_state = initial_approval
    if profile_version != getattr(query_set, "category_profile_version", None):
        query_set.trust_state = TRUST_STATE_UNVERIFIED

    query_set.matcher_version = str(getattr(run, "matcher_version", None) or "")
    query_set.atoms_version = str(getattr(run, "atoms_version", None) or "") or None
    query_set.matcher_run_id = int(run.id)
    query_set.category_profile_version = profile_version

    session.execute(
        delete(SeoSkuQuerySetItem).where(
            SeoSkuQuerySetItem.query_set_id == int(query_set.id)
        )
    )
    session.flush()

    items_written = 0
    for row in results:
        normalized = normalize_query_text(str(row.normalized_query_text or ""))
        if not normalized:
            continue
        bucket = str(row.bucket)
        reasons = list(row.reasons or [])
        session.add(
            SeoSkuQuerySetItem(
                query_set_id=int(query_set.id),
                normalized_query_text=normalized,
                display_query=str(row.query_display or row.normalized_query_text or ""),
                cluster_key=getattr(row, "cluster_key", None),
                bucket=bucket,
                score=Decimal(str(row.score or 0)),
                ranking_value_used=(
                    Decimal(str(row.ranking_value_used))
                    if getattr(row, "ranking_value_used", None) is not None
                    else None
                ),
                selection_state=_selection_state_for_bucket(bucket),
                reasons_payload={
                    "user_reasons": reasons,
                    "reasons": reasons,
                    "matched_atoms": list(row.matched_atoms or []),
                    "missing_atoms": list(row.missing_atoms or []),
                    "conflict_atoms": list(row.conflict_atoms or []),
                    "eligibility_verdict": getattr(row, "eligibility_verdict", None),
                },
            )
        )
        items_written += 1

    session.flush()

    return CandidateProjectionResult(
        query_set_id=int(query_set.id),
        matcher_run_id=int(run.id),
        items_written=items_written,
        approval_state=str(query_set.approval_state),
        trust_state=str(query_set.trust_state),
        category_profile_version=profile_version,
    )


def transition_approval_state(
    session: Session,
    *,
    query_set_id: int,
    new_state: str,
    operator_override: bool = False,
    has_accepted_human_review: bool = False,
) -> SeoSkuQuerySet:
    """Apply a server-side whitelisted approval-state transition.

    Legal transitions (strict forward-only):
    * ``draft -> preview``
    * ``preview -> candidate``
    * ``candidate -> approved``

    ``candidate`` additionally requires
    ``SeoCategoryMatchingReadiness.eligibility_tier != 'preview_only'`` for
    the SKU's category.

    ``approved`` additionally requires ``has_accepted_human_review`` OR
    ``operator_override``. Both of those are passed in by the caller (the
    promote endpoint / admin action), never inferred here, so this module
    stays a pure transition engine.
    """

    row = session.get(SeoSkuQuerySet, int(query_set_id))
    if row is None:
        raise CandidateQuerySetError(f"Query set {query_set_id} not found")

    current = str(row.approval_state or APPROVAL_STATE_DRAFT)
    target = str(new_state or "").strip().lower()

    if target not in _APPROVAL_STATE_ORDER:
        raise CandidateQuerySetError(f"Unknown approval_state: {new_state!r}")

    cur_order = _APPROVAL_STATE_ORDER.get(current, -1)
    tgt_order = _APPROVAL_STATE_ORDER[target]

    if tgt_order <= cur_order:
        raise CandidateQuerySetError(
            f"Illegal approval transition {current!r} -> {target!r}; "
            "backwards / sideways transitions are not allowed"
        )
    if tgt_order - cur_order != 1:
        raise CandidateQuerySetError(
            f"Illegal approval transition {current!r} -> {target!r}; "
            "must step one state at a time"
        )

    if target == APPROVAL_STATE_CANDIDATE:
        tier = _readiness_tier(
            session,
            project_id=int(row.project_id),
            category_id=int(row.category_id),
        )
        if tier == "preview_only":
            raise CandidateQuerySetError(
                "Cannot promote to 'candidate': category eligibility_tier is "
                "'preview_only'; run matcher eval first."
            )
    if target == APPROVAL_STATE_APPROVED:
        if not (has_accepted_human_review or operator_override):
            raise CandidateQuerySetError(
                "Cannot promote to 'approved' without an accepted human "
                "review or an operator override"
            )

    row.approval_state = target
    session.flush()
    return row


def mark_query_set_validated(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
) -> SeoSkuQuerySet | None:
    """Set ``trust_state='validated'`` on the candidate row when the category
    has cleared eval. Safe to call from eval flows; no-ops if the category is
    not evaluated yet.
    """

    tier = _readiness_tier(session, project_id=project_id, category_id=category_id)
    if tier == "preview_only":
        return None
    row = _find_candidate_query_set(
        session,
        project_id=project_id,
        category_id=category_id,
        nm_id=nm_id,
    )
    if row is None:
        return None
    row.trust_state = TRUST_STATE_VALIDATED
    session.flush()
    return row


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


__all__ = [
    "APPROVAL_STATE_APPROVED",
    "APPROVAL_STATE_CANDIDATE",
    "APPROVAL_STATE_DRAFT",
    "APPROVAL_STATE_PREVIEW",
    "CANDIDATE_QUERYSET_STATUS",
    "CandidateProjectionResult",
    "CandidateQuerySetError",
    "TRUST_STATE_UNVERIFIED",
    "TRUST_STATE_VALIDATED",
    "mark_query_set_validated",
    "project_matcher_run_into_query_set",
    "transition_approval_state",
]
