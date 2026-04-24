"""Matcher_v2 entry point — iteration 1 candidate path.

Orchestrates the four-stage pipeline (``eligibility`` -> ``soft_score`` ->
``bucket_cap`` -> ``demand_ordering``), writes a :class:`SeoMatcherRun` +
:class:`SeoMatcherResult` trace, infers the run's ``quality_mode`` and
returns a :class:`MatcherV2RunResult` with the ready-to-serve response.

This is a copy+refactor. The scoring/bucketing helpers are imported from
``services.seo.query_meaning_matcher.matcher`` unchanged so the candidate
path does not drift from current-path semantics. The additive parts are:

1. **Eligibility-first ordering** — hard conflicts and manual rejects are
   evaluated before soft scoring. For the current behavior this is a no-op
   in the produced response (they still land in ``rejected``), but the stage
   split lets the persistence layer attach a stable ``eligibility_verdict``
   column to every result row.
2. **Replayable trace** — every call persists the inputs, component scores,
   matched / missing / conflict atoms, and reasons into ``seo_matcher_runs``
   and ``seo_matcher_results``.
3. **Quality mode** — the run's ``quality_mode`` is derived from the
   embedding provider ceiling, readiness status, and atoms availability via
   :func:`infer_quality_mode`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import (
    SeoCategoryMatchingReadiness,
    SeoMatcherResult,
    SeoMatcherRun,
    SeoMeaningAtom,
    SeoQueryMeaning,
    SeoSkuMeaningAnnotation,
)
from app.schemas.seo_query_meaning_matcher import (
    MEANING_AWARE_MATCHER_VERSION,
    MeaningAwareMatcherDiagnostics,
    MeaningAwareMatcherItem,
    MeaningAwareMatcherResponse,
)
from app.services.seo.atoms.v1.matcher_v1 import ATOMS_MATCHER_V1_VERSION
from app.services.seo.category_profile import CategoryProfile, load_active_profile
from app.services.seo.matcher_v2.persistence import (
    create_matcher_run,
    finalize_matcher_run,
    persist_matcher_results,
)
from app.services.seo.matcher_v2.stages.bucket_cap import decide_bucket
from app.services.seo.matcher_v2.stages.demand_ordering import partition_buckets, sort_items
from app.services.seo.matcher_v2.stages.eligibility import EligibilityVerdict, evaluate_eligibility, query_display_for
from app.services.seo.matcher_v2.stages.soft_score import compute_soft_score
from app.services.seo.meaning_atoms import get_atoms_payload, merge_sku_and_vision_atoms
from app.services.seo.providers.base import EmbeddingProvider
from app.services.seo.quality import (
    REASON_READINESS_NOT_READY,
    REASON_UPSTREAM_MODE,
    QualityMode,
    QualityState,
    coerce_mode,
    infer_quality_mode,
    make_reason,
)
from app.services.seo.query_meaning_matcher.embeddings import (
    LocalPreviewEmbeddingProvider,
    cosine_similarity,
    ensure_meaning_embedding,
)
from app.services.seo.query_meaning_matcher.matcher import (
    CategoryBootstrapBuildingError,
    MissingQueryMeaningLibraryError,
    MissingSkuMeaningAnnotationError,
    _USER_BUCKET_LABELS,
    _judgment_overrides_by_query,
    _query_features,
    _ranking_by_cluster,
    _sku_features,
    _user_reasons,
)
from app.services.seo.query_pipeline import normalize_query_text


MATCHER_V2_VERSION = f"{MEANING_AWARE_MATCHER_VERSION}+v2_candidate"
MATCHER_V2_POLICY_VERSION = "matcher_v2_policy_iter1"


class MatcherV2Error(Exception):
    """Base error for the candidate matcher."""


@dataclass
class MatcherV2RunResult:
    """Bundle returned to routers / callers after a successful candidate run."""

    run_id: int
    response: MeaningAwareMatcherResponse
    run_row: SeoMatcherRun
    result_rows: list[SeoMatcherResult]


def _latest_atoms_row_id(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    entity_type: str,
    entity_id: int | None,
    nm_id: int | None,
) -> int | None:
    stmt = select(SeoMeaningAtom).where(
        SeoMeaningAtom.project_id == int(project_id),
        SeoMeaningAtom.category_id == int(category_id),
        SeoMeaningAtom.entity_type == entity_type,
        SeoMeaningAtom.status == "ready",
    )
    if entity_id is not None:
        stmt = stmt.where(SeoMeaningAtom.entity_id == int(entity_id))
    if nm_id is not None:
        stmt = stmt.where(SeoMeaningAtom.nm_id == int(nm_id))
    row = session.scalars(stmt.order_by(desc(SeoMeaningAtom.updated_at), desc(SeoMeaningAtom.id))).first()
    return int(row.id) if row is not None else None


def _get_readiness(
    session: Session, *, project_id: int, category_id: int
) -> SeoCategoryMatchingReadiness | None:
    return session.scalars(
        select(SeoCategoryMatchingReadiness).where(
            SeoCategoryMatchingReadiness.project_id == int(project_id),
            SeoCategoryMatchingReadiness.category_id == int(category_id),
        )
    ).first()


def _get_sku_annotation(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
) -> SeoSkuMeaningAnnotation:
    row = session.scalars(
        select(SeoSkuMeaningAnnotation)
        .where(
            SeoSkuMeaningAnnotation.project_id == int(project_id),
            SeoSkuMeaningAnnotation.category_id == int(category_id),
            SeoSkuMeaningAnnotation.nm_id == int(nm_id),
        )
        .order_by(SeoSkuMeaningAnnotation.updated_at.desc())
    ).first()
    if row is None:
        raise MissingSkuMeaningAnnotationError("Save SKU Meaning annotation before running matcher preview")
    return row


def run_matcher_v2(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    limit: int = 120,
    include_rejected: bool = True,
    embedding_provider: EmbeddingProvider | None = None,
) -> MatcherV2RunResult:
    """Run the candidate matcher, persist a trace, and return the full bundle.

    Raises :class:`MissingSkuMeaningAnnotationError`,
    :class:`MissingQueryMeaningLibraryError`, or
    :class:`CategoryBootstrapBuildingError` with the same semantics as the
    current matcher; the router translates those to HTTP 4xx/409.
    """

    provider = embedding_provider or LocalPreviewEmbeddingProvider()
    provider_max_mode = coerce_mode(getattr(provider, "max_mode", None), default=QualityMode.FULL)

    # Iteration 2 (WS-C): consume the versioned category profile when one is
    # active. When no profile is seeded for the category yet, the matcher
    # falls back to the legacy in-code dictionaries that were the seed source
    # in the first place — preserving current-path behavior on uncovered
    # categories. The profile's version string is recorded on every
    # ``SeoMatcherRun`` so the eval / compare / promote layers can quote it.
    category_profile: CategoryProfile | None = load_active_profile(
        session, project_id=project_id, category_id=category_id
    )
    category_profile_version = (
        category_profile.version if category_profile is not None else "default_iter1"
    )

    sku_annotation = _get_sku_annotation(
        session, project_id=project_id, category_id=category_id, nm_id=nm_id
    )
    readiness = _get_readiness(session, project_id=project_id, category_id=category_id)
    readiness_status = str(readiness.status) if readiness is not None else "not_started"
    if readiness_status == "building":
        raise CategoryBootstrapBuildingError(
            "Category bootstrap is still running. Refresh readiness status before matching."
        )

    query_rows: list[SeoQueryMeaning] = session.scalars(
        select(SeoQueryMeaning).where(
            SeoQueryMeaning.project_id == int(project_id),
            SeoQueryMeaning.category_id == int(category_id),
            SeoQueryMeaning.status == "ready",
        )
    ).all()
    if not query_rows:
        if readiness_status in {"not_started", "failed"}:
            detail = "Query Meaning Library is empty for this category. Run category bootstrap first."
            if readiness is not None and readiness.last_error:
                detail = f"{detail} Last bootstrap error: {readiness.last_error}"
            raise MissingQueryMeaningLibraryError(detail)
        raise MissingQueryMeaningLibraryError(
            "Query Meaning Library is empty for this category. Build/refresh query meanings first."
        )

    sku_meaning = dict(sku_annotation.meaning_payload or {})
    sku_features = _sku_features(sku_meaning)

    sku_atoms_row_id = _latest_atoms_row_id(
        session,
        project_id=project_id,
        category_id=category_id,
        entity_type="sku_meaning",
        entity_id=int(sku_annotation.id),
        nm_id=int(nm_id),
    )
    vision_atoms_row_id = _latest_atoms_row_id(
        session,
        project_id=project_id,
        category_id=category_id,
        entity_type="sku_vision",
        entity_id=int(sku_annotation.id),
        nm_id=int(nm_id),
    )
    sku_atoms_payload = get_atoms_payload(
        session,
        project_id=project_id,
        category_id=category_id,
        entity_type="sku_meaning",
        entity_id=int(sku_annotation.id),
        nm_id=int(nm_id),
    )
    vision_atoms_payload = get_atoms_payload(
        session,
        project_id=project_id,
        category_id=category_id,
        entity_type="sku_vision",
        entity_id=int(sku_annotation.id),
        nm_id=int(nm_id),
    )
    sku_atoms = merge_sku_and_vision_atoms(sku_atoms_payload, vision_atoms_payload)
    atoms_gate_enabled = sku_atoms is not None

    judgment_by_query, judgment_by_cluster_key = _judgment_overrides_by_query(
        session, annotation_id=int(sku_annotation.id)
    )
    sku_embedding = ensure_meaning_embedding(
        session,
        project_id=project_id,
        category_id=category_id,
        entity_type="sku_meaning",
        entity_id=int(sku_annotation.id),
        canonical_text=sku_features.canonical_text,
        provider=provider,
    )
    ranking_by_cluster = _ranking_by_cluster(
        session,
        project_id=project_id,
        category_id=category_id,
        cluster_ids=[int(row.cluster_id) for row in query_rows if row.cluster_id is not None],
    )

    readiness_snapshot = {
        "status": readiness_status,
        "readiness_id": int(readiness.id) if readiness is not None else None,
        "queries_count": int(readiness.queries_count) if readiness is not None else 0,
        "query_meanings_count": int(readiness.query_meanings_count) if readiness is not None else 0,
        "query_atoms_count": int(readiness.query_atoms_count) if readiness is not None else 0,
        "embeddings_count": int(readiness.embeddings_count) if readiness is not None else 0,
    }

    run_row = create_matcher_run(
        session,
        project_id=project_id,
        category_id=category_id,
        nm_id=nm_id,
        matcher_version=MATCHER_V2_VERSION,
        policy_version=MATCHER_V2_POLICY_VERSION,
        category_profile_version=category_profile_version,
        sku_atoms_id=sku_atoms_row_id,
        vision_atoms_id=vision_atoms_row_id,
        query_atoms_version=ATOMS_MATCHER_V1_VERSION,
        embedding_model=str(sku_embedding.model),
        readiness_snapshot=readiness_snapshot,
    )

    items: list[MeaningAwareMatcherItem] = []
    eligibility_by_meaning_id: dict[int, str] = {}
    components_by_meaning_id: dict[int, Mapping[str, float]] = {}
    embedding_model: str | None = str(sku_embedding.model)

    for row in query_rows:
        query_display = query_display_for(row)
        query_features = _query_features(row)
        query_embedding = ensure_meaning_embedding(
            session,
            project_id=project_id,
            category_id=category_id,
            entity_type="query_meaning",
            entity_id=int(row.id),
            canonical_text=str(row.canonical_text or ""),
            provider=provider,
        )
        embedding_model = str(query_embedding.model or embedding_model)
        raw_similarity = cosine_similarity(sku_embedding.embedding or [], query_embedding.embedding or [])
        semantic_similarity = round(max(0.0, min(1.0, (raw_similarity + 1.0) / 2.0)), 4)

        judgment = judgment_by_cluster_key.get(str(row.cluster_key)) or judgment_by_query.get(
            normalize_query_text(query_display)
        )
        eligibility = evaluate_eligibility(
            sku_features=sku_features,
            query_features=query_features,
            query_row=row,
            judgment=judgment,
            category_profile=category_profile,
        )
        eligibility_by_meaning_id[int(row.id)] = eligibility.verdict

        conflicts = list(eligibility.conflicts)
        genericness = str(row.genericness or "specific")
        ranking_value = (
            ranking_by_cluster.get(int(row.cluster_id)) if row.cluster_id is not None else None
        )

        if eligibility.verdict in {"manual_rejected", "manual_broad", "hard_conflict"}:
            # Pre-filter path: skip soft scoring, route directly to the forced
            # bucket. Behavior matches current matcher for these verdicts.
            bucket = eligibility.bucket_hint or "rejected"
            score = 0.0 if bucket == "rejected" else 0.3
            reasons = list(eligibility.reasons) + conflicts
            components_by_meaning_id[int(row.id)] = {
                "semantic_similarity": round(semantic_similarity, 4),
                "pre_filtered": 1.0,
            }
            items.append(
                MeaningAwareMatcherItem(
                    query=query_display,
                    cluster_id=int(row.cluster_id) if row.cluster_id is not None else None,
                    cluster_key=str(row.cluster_key),
                    query_meaning_id=int(row.id),
                    bucket=bucket,  # type: ignore[arg-type]
                    score=score,
                    semantic_similarity=semantic_similarity,
                    ranking_value_used=ranking_value,
                    genericness=genericness,  # type: ignore[arg-type]
                    matched_meanings=[],
                    conflicts=conflicts,
                    reasons=reasons,
                    user_bucket_label=_USER_BUCKET_LABELS.get(bucket, bucket),
                    user_reasons=_user_reasons(
                        bucket=bucket,
                        matched_atoms=[],
                        missing_atoms=[],
                        conflict_atoms=conflicts,
                        fallback_reasons=reasons,
                    ),
                    matched_atoms=[],
                    missing_atoms=[],
                    conflict_atoms=conflicts,
                    debug_reasons=reasons,
                )
            )
            continue

        soft = compute_soft_score(
            sku_features=sku_features,
            query_features=query_features,
            semantic_similarity=semantic_similarity,
            genericness=genericness,
            ranking_value=ranking_value,
            has_conflicts=False,
            category_profile=category_profile,
        )
        reasons = list(soft.reasons)
        reasons.append("no hard constraints")
        if eligibility.reasons:
            reasons.extend(eligibility.reasons)

        query_atoms_payload = get_atoms_payload(
            session,
            project_id=project_id,
            category_id=category_id,
            entity_type="query_meaning",
            entity_id=int(row.id),
        )
        decision = decide_bucket(
            score=soft.score,
            genericness=genericness,
            conflicts=[],
            semantic_similarity=semantic_similarity,
            expressive_overlap=soft.expressive_overlap,
            audience_overlap=soft.audience_overlap,
            occasion_overlap=soft.occasion_overlap,
            use_case_overlap=soft.use_case_overlap,
            attribute_overlap=soft.attribute_overlap,
            row=row,
            query_display=query_display,
            ranking_value=ranking_value,
            sku_atoms=sku_atoms,
            query_atoms_payload=query_atoms_payload,
            category_profile=category_profile,
        )
        reasons.extend(decision.reasons)

        if decision.bucket == "rejected" and not include_rejected:
            components_by_meaning_id[int(row.id)] = dict(soft.components)
            continue

        components_by_meaning_id[int(row.id)] = dict(soft.components)
        items.append(
            MeaningAwareMatcherItem(
                query=query_display,
                cluster_id=int(row.cluster_id) if row.cluster_id is not None else None,
                cluster_key=str(row.cluster_key),
                query_meaning_id=int(row.id),
                bucket=decision.bucket,  # type: ignore[arg-type]
                score=decision.score,
                semantic_similarity=semantic_similarity,
                ranking_value_used=ranking_value,
                genericness=genericness,  # type: ignore[arg-type]
                matched_meanings=sorted(set(soft.matched_terms)),
                conflicts=list(decision.conflict_atoms),
                reasons=reasons,
                user_bucket_label=_USER_BUCKET_LABELS.get(decision.bucket, decision.bucket),
                user_reasons=_user_reasons(
                    bucket=decision.bucket,
                    matched_atoms=decision.matched_atoms,
                    missing_atoms=decision.missing_atoms,
                    conflict_atoms=decision.conflict_atoms,
                    fallback_reasons=reasons,
                ),
                matched_atoms=list(decision.matched_atoms),
                missing_atoms=list(decision.missing_atoms),
                conflict_atoms=list(decision.conflict_atoms),
                debug_reasons=reasons,
            )
        )

    items = sort_items(items)
    buckets = partition_buckets(items, limit=limit)

    # Quality-mode inference
    evidence_signals: dict[str, bool] = {
        "readiness_ready": readiness_status in {"ready", "ready_for_matching", "ready_with_fallback"},
    }
    extra_reasons = []
    if readiness_status == "ready_with_fallback":
        extra_reasons.append(
            make_reason(
                "readiness_fallback",
                {"readiness_status": readiness_status},
            )
        )
    state = QualityState(
        embedding_provider_max_mode=provider_max_mode,
        evidence_signals=evidence_signals,
        extra_reasons=extra_reasons,
    )
    quality_mode, degraded_reasons = infer_quality_mode(state)

    metrics = {
        "query_meanings_total": len(query_rows),
        "scored_total": len(items),
        "buckets": {name: len(rows) for name, rows in buckets.items()},
        "eligibility_breakdown": _verdict_counts(eligibility_by_meaning_id),
        "atoms_gate_enabled": atoms_gate_enabled,
        # Iteration 2 (WS-C): record the active category profile so eval /
        # compare layers can correlate runs with the exact profile version.
        "category_profile_version": category_profile_version,
        "category_profile_id": category_profile.profile_id if category_profile is not None else None,
        "category_profile_active": category_profile is not None,
    }
    finalize_matcher_run(
        session,
        run_row,
        metrics=metrics,
        quality_mode=quality_mode,
        degraded_reasons=degraded_reasons,
    )
    result_rows = persist_matcher_results(
        session,
        run_row,
        items,
        eligibility_by_meaning_id=eligibility_by_meaning_id,
        components_by_meaning_id=components_by_meaning_id,
    )

    response = MeaningAwareMatcherResponse(
        project_id=int(project_id),
        category_id=int(category_id),
        nm_id=int(nm_id),
        sku_annotation_id=int(sku_annotation.id),
        sku_annotation_status=str(sku_annotation.status or "draft"),
        buckets=buckets,  # type: ignore[arg-type]
        diagnostics=MeaningAwareMatcherDiagnostics(
            matcher_version=MATCHER_V2_VERSION,
            query_meanings_total=len(query_rows),
            scored_total=len(items),
            missing_library=False,
            embedding_model=embedding_model,
            atoms_version=ATOMS_MATCHER_V1_VERSION,
            atoms_gate_enabled=atoms_gate_enabled,
            notes=[
                "matcher_v2 candidate path (iteration 1)",
                f"run_id: {run_row.id}",
                f"quality_mode: {quality_mode.value}",
                f"category readiness: {readiness_status}",
            ],
        ),
    )

    return MatcherV2RunResult(
        run_id=int(run_row.id),
        response=response,
        run_row=run_row,
        result_rows=result_rows,
    )


def _verdict_counts(mapping: Mapping[int, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for verdict in mapping.values():
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts


__all__ = [
    "MATCHER_V2_POLICY_VERSION",
    "MATCHER_V2_VERSION",
    "MatcherV2Error",
    "MatcherV2RunResult",
    "run_matcher_v2",
]
