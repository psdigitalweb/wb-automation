"""Profile-driven facade for the meaning-aware query matcher."""

from __future__ import annotations

import math
import warnings
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.schemas.seo_query_meaning_matcher import (
    MEANING_AWARE_MATCHER_VERSION,
    MeaningAwareMatcherDiagnostics,
    MeaningAwareMatcherItem,
    MeaningAwareMatcherResponse,
)
from app.services.seo.category_profile import CategoryProfile, load_active_profile
from app.services.seo.providers.base import EmbeddingProvider
from app.services.seo.query_meaning_matcher._legacy import matcher as _legacy_matcher
from app.services.seo.query_meaning_matcher.embeddings import LocalPreviewEmbeddingProvider, cosine_similarity, ensure_meaning_embedding
from app.services.seo.query_meaning_matcher.profile_matcher import (
    _FeatureSet,
    _hard_conflicts as _profile_hard_conflicts,
    _product_type_score as _profile_product_type_score,
    _query_features as _profile_query_features,
    _sku_features as _profile_sku_features,
)
from app.services.seo.query_pipeline import normalize_query_text
from app.services.seo.meaning_atoms import get_atoms_payload, merge_sku_and_vision_atoms


MeaningAwareMatcherError = _legacy_matcher.MeaningAwareMatcherError
MissingQueryMeaningLibraryError = _legacy_matcher.MissingQueryMeaningLibraryError
MissingSkuMeaningAnnotationError = _legacy_matcher.MissingSkuMeaningAnnotationError
CategoryBootstrapBuildingError = _legacy_matcher.CategoryBootstrapBuildingError

_WEAK_OVERLAP_TOKENS = _legacy_matcher._WEAK_OVERLAP_TOKENS
_MATERIAL_CONSTRAINTS = _legacy_matcher._MATERIAL_CONSTRAINTS
_EXPRESSIVE_GROUPS = _legacy_matcher._EXPRESSIVE_GROUPS
_AUDIENCE_GROUPS = _legacy_matcher._AUDIENCE_GROUPS
_USER_BUCKET_LABELS = _legacy_matcher._USER_BUCKET_LABELS

_first_text = _legacy_matcher._first_text
_expand_expressive = _legacy_matcher._expand_expressive
_expand_audience = _legacy_matcher._expand_audience
_expand_visual_terms = _legacy_matcher._expand_visual_terms
_material_set = _legacy_matcher._material_set
_ranking_by_cluster = _legacy_matcher._ranking_by_cluster
_overlap_score = _legacy_matcher._overlap_score
_frequency_boost = _legacy_matcher._frequency_boost
_bucket_for = _legacy_matcher._bucket_for
_query_display = _legacy_matcher._query_display
_judgment_overrides_by_query = _legacy_matcher._judgment_overrides_by_query
_manual_bucket_override = _legacy_matcher._manual_bucket_override
_user_reasons = _legacy_matcher._user_reasons
_query_coverage_tags = _legacy_matcher._query_coverage_tags
_select_bucket_with_coverage = _legacy_matcher._select_bucket_with_coverage
_apply_atoms_gate = _legacy_matcher._apply_atoms_gate
_get_sku_annotation = _legacy_matcher._get_sku_annotation


def _warn_legacy_matcher_path() -> None:
    warnings.warn(
        "legacy query_meaning_matcher path is deprecated; use profile-driven matcher",
        DeprecationWarning,
        stacklevel=3,
    )


def _load_profile_or_none(session: Session, *, project_id: int, category_id: int) -> CategoryProfile | None:
    """Return the active profile when the table exists, else keep the legacy path.

    Step 6 still has to preserve the old matcher tests and ad hoc SQLite setups
    that do not create ``seo_category_profiles``. Those environments should
    continue to use the explicit legacy matcher path until Step 7/8 wires
    profile activation end to end.
    """

    try:
        return load_active_profile(session, project_id=project_id, category_id=category_id)
    except SQLAlchemyError as exc:
        if "seo_category_profiles" not in str(exc).lower():
            raise
        _warn_legacy_matcher_path()
        return None


def _sku_features(meaning: dict[str, Any], *, profile: CategoryProfile | None = None) -> _FeatureSet:
    if profile is None:
        _warn_legacy_matcher_path()
        return _legacy_matcher._sku_features(meaning)
    return _profile_sku_features(meaning, profile=profile)


def _query_features(row: Any, *, profile: CategoryProfile | None = None) -> _FeatureSet:
    if profile is None:
        _warn_legacy_matcher_path()
        return _legacy_matcher._query_features(row)
    return _profile_query_features(row, profile=profile)


def _hard_conflicts(
    sku: _FeatureSet,
    query: _FeatureSet,
    *,
    profile: CategoryProfile | None = None,
) -> list[str]:
    if profile is None:
        _warn_legacy_matcher_path()
        return _legacy_matcher._hard_conflicts(sku, query)
    return _profile_hard_conflicts(sku, query, profile=profile)


def _product_type_score(
    sku: _FeatureSet,
    query: _FeatureSet,
    *,
    profile: CategoryProfile | None = None,
) -> tuple[float, list[str]]:
    if profile is None:
        _warn_legacy_matcher_path()
        return _legacy_matcher._product_type_score(sku, query)
    return _profile_product_type_score(sku, query, profile=profile)


def run_legacy_meaning_aware_matcher(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    limit: int = 120,
    include_rejected: bool = True,
    embedding_provider: EmbeddingProvider | None = None,
) -> MeaningAwareMatcherResponse:
    """Explicit legacy fallback path used while matcher_v2 is not yet profile-wired."""

    _warn_legacy_matcher_path()
    return _legacy_matcher.run_meaning_aware_matcher(
        session,
        project_id=project_id,
        category_id=category_id,
        nm_id=nm_id,
        limit=limit,
        include_rejected=include_rejected,
        embedding_provider=embedding_provider,
    )


def run_meaning_aware_matcher(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    nm_id: int,
    limit: int = 120,
    include_rejected: bool = True,
    embedding_provider: EmbeddingProvider | None = None,
    profile: CategoryProfile | None = None,
) -> MeaningAwareMatcherResponse:
    """Run the meaning-aware matcher with profile-driven logic when a profile exists."""

    active_profile = profile or _load_profile_or_none(session, project_id=project_id, category_id=category_id)
    if active_profile is None:
        return run_legacy_meaning_aware_matcher(
            session,
            project_id=project_id,
            category_id=category_id,
            nm_id=nm_id,
            limit=limit,
            include_rejected=include_rejected,
            embedding_provider=embedding_provider,
        )

    resolved_embedding_provider = embedding_provider or LocalPreviewEmbeddingProvider()
    sku_annotation = _get_sku_annotation(session, project_id=project_id, category_id=category_id, nm_id=nm_id)
    from app.services.seo.category_bootstrap import get_readiness_row

    readiness = get_readiness_row(session, project_id=project_id, category_id=category_id)
    readiness_status = str(readiness.status) if readiness is not None else "not_started"
    if readiness_status == "building":
        raise CategoryBootstrapBuildingError("Category bootstrap is still running. Refresh readiness status before matching.")
    query_rows = session.scalars(
        _legacy_matcher.select(_legacy_matcher.SeoQueryMeaning).where(
            _legacy_matcher.SeoQueryMeaning.project_id == int(project_id),
            _legacy_matcher.SeoQueryMeaning.category_id == int(category_id),
            _legacy_matcher.SeoQueryMeaning.status == "ready",
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
    sku_features = _sku_features(sku_meaning, profile=active_profile)
    sku_atoms_payload = get_atoms_payload(
        session,
        project_id=project_id,
        category_id=category_id,
        entity_type="sku_meaning",
        entity_id=int(sku_annotation.id),
        nm_id=nm_id,
    )
    vision_atoms_payload = get_atoms_payload(
        session,
        project_id=project_id,
        category_id=category_id,
        entity_type="sku_vision",
        entity_id=int(sku_annotation.id),
        nm_id=nm_id,
    )
    sku_atoms = merge_sku_and_vision_atoms(sku_atoms_payload, vision_atoms_payload)
    atoms_gate_enabled = sku_atoms is not None
    judgment_by_query, judgment_by_cluster_key = _judgment_overrides_by_query(
        session,
        annotation_id=int(sku_annotation.id),
    )
    sku_embedding = ensure_meaning_embedding(
        session,
        project_id=project_id,
        category_id=category_id,
        entity_type="sku_meaning",
        entity_id=int(sku_annotation.id),
        canonical_text=sku_features.canonical_text,
        provider=resolved_embedding_provider,
    )
    ranking_by_cluster = _ranking_by_cluster(
        session,
        project_id=project_id,
        category_id=category_id,
        cluster_ids=[int(row.cluster_id) for row in query_rows if row.cluster_id is not None],
    )

    items: list[MeaningAwareMatcherItem] = []
    embedding_model: str | None = str(sku_embedding.model)
    for row in query_rows:
        query_display = _query_display(row)
        query_features = _query_features(row, profile=active_profile)
        query_embedding = ensure_meaning_embedding(
            session,
            project_id=project_id,
            category_id=category_id,
            entity_type="query_meaning",
            entity_id=int(row.id),
            canonical_text=str(row.canonical_text or ""),
            provider=resolved_embedding_provider,
        )
        embedding_model = str(query_embedding.model or embedding_model)
        raw_similarity = cosine_similarity(sku_embedding.embedding or [], query_embedding.embedding or [])
        semantic_similarity = round(max(0.0, min(1.0, (raw_similarity + 1.0) / 2.0)), 4)

        conflicts = _hard_conflicts(sku_features, query_features, profile=active_profile)
        reasons: list[str] = []
        matched: list[str] = []
        product_score, product_reasons = _product_type_score(sku_features, query_features, profile=active_profile)
        reasons.extend(product_reasons)
        expressive_score, expressive_overlap, expressive_reasons = _overlap_score(
            "expressive",
            sku_features.expressive_terms,
            query_features.expressive_terms,
            0.22,
        )
        use_case_score, use_case_overlap, use_case_reasons = _overlap_score(
            "use_case",
            sku_features.use_case_terms,
            query_features.use_case_terms,
            0.14,
        )
        attribute_score, attribute_overlap, attribute_reasons = _overlap_score(
            "attribute",
            sku_features.attribute_terms,
            query_features.attribute_terms,
            0.08,
        )
        audience_score, audience_overlap, audience_reasons = _overlap_score(
            "audience",
            sku_features.audience_terms,
            query_features.audience_terms,
            0.12,
        )
        occasion_score, occasion_overlap, occasion_reasons = _overlap_score(
            "occasion",
            sku_features.occasion_terms,
            query_features.occasion_terms,
            0.05,
        )
        reasons.extend(expressive_reasons + use_case_reasons + attribute_reasons + audience_reasons + occasion_reasons)
        matched.extend(expressive_overlap + use_case_overlap + attribute_overlap + audience_overlap + occasion_overlap)

        genericness = str(row.genericness or "specific")
        specificity_bonus = 0.08 if genericness == "specific" else 0.0
        genericness_penalty = 0.18 if genericness == "generic" else (0.09 if genericness == "broad" else 0.0)
        conflict_penalty = 0.55 if conflicts else 0.0
        ranking_value = ranking_by_cluster.get(int(row.cluster_id)) if row.cluster_id is not None else None
        frequency = _frequency_boost(ranking_value, allow=not conflicts and genericness == "specific")
        score = (
            0.34 * semantic_similarity
            + product_score
            + expressive_score
            + use_case_score
            + attribute_score
            + audience_score
            + occasion_score
            + specificity_bonus
            + frequency
            - genericness_penalty
            - conflict_penalty
        )
        score = round(max(0.0, min(1.0, score)), 4)
        if conflicts:
            reasons.extend(conflicts)
        else:
            reasons.append("no hard constraints")
        if frequency:
            reasons.append("frequency boosts already relevant candidate")
        if genericness in {"generic", "broad"}:
            reasons.append(f"downgraded by genericness: {genericness}")

        bucket = _bucket_for(
            score=score,
            genericness=genericness,
            conflicts=conflicts,
            semantic_similarity=semantic_similarity,
            expressive_overlap=expressive_overlap,
            audience_overlap=audience_overlap,
            occasion_overlap=occasion_overlap,
            use_case_overlap=use_case_overlap,
            attribute_overlap=attribute_overlap,
        )
        judgment = judgment_by_cluster_key.get(str(row.cluster_key)) or judgment_by_query.get(normalize_query_text(query_display))
        manual_bucket, manual_reasons, manual_conflicts = _manual_bucket_override(row, judgment)
        if manual_reasons:
            reasons.extend(manual_reasons)
        if manual_conflicts:
            conflicts.extend(manual_conflicts)
            score = min(score, 0.01)
        if manual_bucket is not None:
            bucket = manual_bucket

        query_atoms_payload = get_atoms_payload(
            session,
            project_id=project_id,
            category_id=category_id,
            entity_type="query_meaning",
            entity_id=int(row.id),
        )
        bucket, score, matched_atoms, missing_atoms, conflict_atoms, debug_reasons = _apply_atoms_gate(
            bucket=bucket,
            score=score,
            row=row,
            query_display=query_display,
            ranking_value=ranking_value,
            sku_atoms=sku_atoms,
            query_atoms_payload=query_atoms_payload,
        )
        if conflict_atoms:
            conflicts.extend(conflict_atoms)
        reasons.extend(debug_reasons)
        if bucket == "rejected" and not include_rejected:
            continue
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
                matched_meanings=sorted(set(matched)),
                conflicts=conflicts,
                reasons=reasons,
                user_bucket_label=_USER_BUCKET_LABELS.get(bucket, bucket),
                user_reasons=_user_reasons(
                    bucket=bucket,
                    matched_atoms=matched_atoms,
                    missing_atoms=missing_atoms,
                    conflict_atoms=conflict_atoms,
                    fallback_reasons=reasons,
                ),
                matched_atoms=matched_atoms,
                missing_atoms=missing_atoms,
                conflict_atoms=conflict_atoms,
                debug_reasons=reasons,
            )
        )

    per_bucket_limit = max(10, min(100, math.ceil(max(1, int(limit)) / 4)))
    items.sort(key=lambda item: (-item.score, -(item.ranking_value_used or 0), item.query))
    buckets = {
        "primary": _select_bucket_with_coverage([item for item in items if item.bucket == "primary"], per_bucket_limit),
        "secondary": _select_bucket_with_coverage([item for item in items if item.bucket == "secondary"], per_bucket_limit),
        "broad": [item for item in items if item.bucket == "broad"][:per_bucket_limit],
        "rejected": [item for item in items if item.bucket == "rejected"][:per_bucket_limit],
    }
    return MeaningAwareMatcherResponse(
        project_id=int(project_id),
        category_id=int(category_id),
        nm_id=int(nm_id),
        sku_annotation_id=int(sku_annotation.id),
        sku_annotation_status=str(sku_annotation.status or "draft"),
        buckets=buckets,  # type: ignore[arg-type]
        diagnostics=MeaningAwareMatcherDiagnostics(
            matcher_version=MEANING_AWARE_MATCHER_VERSION,
            query_meanings_total=len(query_rows),
            scored_total=len(items),
            missing_library=False,
            embedding_model=embedding_model,
            atoms_version=_legacy_matcher.ATOMS_MATCHER_V1_VERSION,
            atoms_gate_enabled=atoms_gate_enabled,
            notes=[
                "frequency never creates relevance by itself",
                "atoms gate protects Primary from hard semantic conflicts" if atoms_gate_enabled else "atoms gate skipped: analyze SKU to create SKU atoms",
                f"category readiness: {readiness_status}",
                *(
                    ["category uses deterministic fallback axes; rerun bootstrap with LLM for better quality"]
                    if readiness_status == "ready_with_fallback"
                    else []
                ),
            ],
        ),
    )


__all__ = [
    "CategoryBootstrapBuildingError",
    "MeaningAwareMatcherError",
    "MissingQueryMeaningLibraryError",
    "MissingSkuMeaningAnnotationError",
    "_AUDIENCE_GROUPS",
    "_EXPRESSIVE_GROUPS",
    "_FeatureSet",
    "_MATERIAL_CONSTRAINTS",
    "_USER_BUCKET_LABELS",
    "_apply_atoms_gate",
    "_bucket_for",
    "_frequency_boost",
    "_hard_conflicts",
    "_judgment_overrides_by_query",
    "_manual_bucket_override",
    "_overlap_score",
    "_product_type_score",
    "_query_display",
    "_query_features",
    "_ranking_by_cluster",
    "_select_bucket_with_coverage",
    "_sku_features",
    "_user_reasons",
    "run_legacy_meaning_aware_matcher",
    "run_meaning_aware_matcher",
]
