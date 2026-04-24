"""Persistence for matcher_v2.

Writes a single :class:`SeoMatcherRun` row and N :class:`SeoMatcherResult`
rows per invocation. Runs and results are immutable: re-running the candidate
matcher creates fresh rows. Iteration 2 introduces a compare/selection layer
that points at these rows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy.orm import Session

from app.models import SeoMatcherResult, SeoMatcherRun
from app.schemas.seo_query_meaning_matcher import MeaningAwareMatcherItem
from app.services.seo.quality import QualityMode


def create_matcher_run(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    matcher_version: str,
    policy_version: str,
    category_profile_version: str,
    sku_atoms_id: int | None,
    vision_atoms_id: int | None,
    query_atoms_version: str | None,
    embedding_model: str | None,
    readiness_snapshot: Mapping[str, Any],
) -> SeoMatcherRun:
    """Insert a started matcher run row. Caller fills metrics/completed_at later."""

    row = SeoMatcherRun(
        project_id=int(project_id),
        category_id=int(category_id),
        nm_id=int(nm_id),
        matcher_version=str(matcher_version),
        policy_version=str(policy_version),
        category_profile_version=str(category_profile_version),
        sku_atoms_id=int(sku_atoms_id) if sku_atoms_id is not None else None,
        vision_atoms_id=int(vision_atoms_id) if vision_atoms_id is not None else None,
        query_atoms_version=query_atoms_version,
        embedding_model=embedding_model,
        readiness_snapshot=dict(readiness_snapshot),
        metrics={},
    )
    session.add(row)
    session.flush()
    return row


def finalize_matcher_run(
    session: Session,
    run: SeoMatcherRun,
    *,
    metrics: Mapping[str, Any],
    quality_mode: QualityMode | str,
    degraded_reasons: Sequence[Mapping[str, Any]] | None,
    error: Mapping[str, Any] | None = None,
) -> SeoMatcherRun:
    """Mark a matcher run complete and attach quality-mode metadata."""

    run.metrics = dict(metrics)
    run.quality_mode = quality_mode.value if isinstance(quality_mode, QualityMode) else str(quality_mode)
    run.degraded_reasons = [dict(reason) for reason in (degraded_reasons or [])] or None
    run.completed_at = datetime.now(timezone.utc)
    run.error = dict(error) if error else None
    session.flush()
    return run


def persist_matcher_results(
    session: Session,
    run: SeoMatcherRun,
    items: Sequence[MeaningAwareMatcherItem],
    *,
    eligibility_by_meaning_id: Mapping[int, str],
    components_by_meaning_id: Mapping[int, Mapping[str, float]],
) -> list[SeoMatcherResult]:
    """Bulk-insert matcher result rows for a single run.

    ``items`` must already include *all* candidate queries (including rejected
    ones) with their final buckets. Components and eligibility verdicts come
    from earlier stages via the accompanying maps.
    """

    rows: list[SeoMatcherResult] = []
    for item in items:
        qm_id = int(item.query_meaning_id) if item.query_meaning_id is not None else None
        components = {}
        if qm_id is not None:
            components = dict(components_by_meaning_id.get(qm_id, {}))
        verdict = "eligible"
        if qm_id is not None:
            verdict = str(eligibility_by_meaning_id.get(qm_id, "eligible"))

        row = SeoMatcherResult(
            run_id=int(run.id),
            cluster_key=str(item.cluster_key) if item.cluster_key else None,
            query_meaning_id=qm_id,
            query_display=str(item.query),
            normalized_query_text=str(item.query),
            bucket=str(item.bucket),
            eligibility_verdict=verdict,
            score=float(item.score),
            score_components=components,
            matched_atoms=list(item.matched_atoms or []),
            missing_atoms=list(item.missing_atoms or []),
            conflict_atoms=list(item.conflict_atoms or []),
            reasons=list(item.debug_reasons or item.reasons or []),
            ranking_value_used=(
                float(item.ranking_value_used)
                if item.ranking_value_used is not None
                else None
            ),
            semantic_similarity=(
                float(item.semantic_similarity)
                if item.semantic_similarity is not None
                else None
            ),
        )
        session.add(row)
        rows.append(row)
    session.flush()
    return rows


__all__ = [
    "create_matcher_run",
    "finalize_matcher_run",
    "persist_matcher_results",
]
