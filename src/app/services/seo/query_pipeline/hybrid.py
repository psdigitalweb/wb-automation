"""Deterministic hybrid query annotation over the persisted pruning + clustering state."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SeoQueryAnnotation, SeoQueryAnnotationVersion, SeoQueryCluster, SeoQueryClusterMembership
from app.services.seo.query_pipeline.clustering import (
    _ClusteringHeuristicsContext,
    _build_clustering_context,
    _normalize_token_for_cluster,
    _strong_tokens,
    _tokenize,
    get_query_clusters,
    run_query_clustering,
)
from app.services.seo.query_pipeline.diagnostics import (
    HybridClusterPreview,
    HybridQueryPreview,
    QueryHybridAnnotationDiagnostics,
    _serialize_value,
)
from app.services.seo.query_pipeline.pruning import (
    AnnotatedCanonicalQueryRow,
    _annotation_payload,
    _load_existing_annotations,
    _semantic_snapshot,
    get_clean_query_set,
    get_persisted_pruning_overlay,
)
from app.services.seo.query_pipeline.unified_dataset import _decimal_to_string


_PROVENANCE_KEYS = ("individual", "cluster", "rejected", "fallback")
_HYBRID_REASON_UNKNOWN = "unknown_rejected_inheritance"
_RELAXED_INHERITANCE_REASONS = {
    "compatible_plural_variant",
    "compatible_attribute_extension",
    "same_family_high_overlap",
}


@dataclass(frozen=True)
class HybridAnnotatedQueryRow(AnnotatedCanonicalQueryRow):
    """Pruning row enriched with a separate hybrid-annotation projection."""

    base_query_type: str = "tail"
    base_intent_type: str = "unknown"
    base_annotation_reason_code: str = "migrated_pending"
    provenance: str = "rejected"
    source_anchor_query: str | None = None
    source_cluster_key: str | None = None
    inheritance_reason_code: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)


@dataclass(frozen=True)
class QueryHybridAnnotationResult:
    """Hybrid projection rows plus readable diagnostics."""

    project_id: int
    category_id: int
    annotated_queries: list[HybridAnnotatedQueryRow]
    diagnostics: QueryHybridAnnotationDiagnostics
    annotations_upserted: int = 0
    versions_created: int = 0


@dataclass(frozen=True)
class _HybridClusterMember:
    normalized_query_text: str
    query_type: str
    ranking_value_used: Decimal
    membership_reason_code: str
    base_intent_type: str


@dataclass(frozen=True)
class _HybridCluster:
    cluster_key: str
    cluster_label_candidate: str
    top_query_text: str
    query_count: int
    manual_review_required: bool
    members: list[_HybridClusterMember]


@dataclass(frozen=True)
class _AnchorSelection:
    normalized_query_text: str
    provenance: str


def _sorted_rows(rows: list[AnnotatedCanonicalQueryRow]) -> list[AnnotatedCanonicalQueryRow]:
    return sorted(
        rows,
        key=lambda row: (
            -Decimal(str(row.ranking_value_used)),
            row.normalized_query_text,
        ),
    )


def _token_count(normalized_query_text: str) -> int:
    return len([token for token in str(normalized_query_text or "").split(" ") if token])


def _strong_tokens_for_text(text_value: str, *, context: _ClusteringHeuristicsContext) -> tuple[str, ...]:
    canonical_tokens = tuple(
        sorted(
            {
                _normalize_token_for_cluster(token, token_family_map=context.token_family_map)
                for token in _tokenize(text_value)
            }
        )
    )
    return _strong_tokens(canonical_tokens, weak_tokens=context.weak_tokens)


def _canonical_tokens_for_text(text_value: str, *, context: _ClusteringHeuristicsContext) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                _normalize_token_for_cluster(token, token_family_map=context.token_family_map)
                for token in _tokenize(text_value)
            }
        )
    )


def _is_broad_cluster(cluster: _HybridCluster, *, context: _ClusteringHeuristicsContext) -> bool:
    if cluster.manual_review_required:
        return True
    if cluster.query_count <= 3:
        return False
    label_basis = cluster.cluster_label_candidate or cluster.top_query_text
    return len(_strong_tokens_for_text(label_basis, context=context)) <= 1


def _token_overlap_ratio(left_tokens: set[str], right_tokens: set[str]) -> Decimal:
    if not left_tokens or not right_tokens:
        return Decimal("0")
    overlap_count = len(left_tokens.intersection(right_tokens))
    return Decimal(overlap_count) / Decimal(min(len(left_tokens), len(right_tokens)) or 1)


def _is_clean_member_for_anchor(
    member_text: str,
    *,
    anchor_strong_token_set: set[str],
    context: _ClusteringHeuristicsContext,
) -> bool:
    member_strong_tokens = set(_strong_tokens_for_text(member_text, context=context))
    if not member_strong_tokens:
        return False
    if anchor_strong_token_set == member_strong_tokens:
        return True
    if anchor_strong_token_set.issubset(member_strong_tokens):
        return len(member_strong_tokens.difference(anchor_strong_token_set)) <= 2
    if member_strong_tokens.issubset(anchor_strong_token_set):
        return len(anchor_strong_token_set.difference(member_strong_tokens)) <= 1
    return (
        _token_overlap_ratio(anchor_strong_token_set, member_strong_tokens) >= Decimal("0.75")
        and len(anchor_strong_token_set.symmetric_difference(member_strong_tokens)) <= 1
    )


def _relaxed_cluster_size_limit(
    cluster: _HybridCluster,
    *,
    anchor: AnnotatedCanonicalQueryRow,
    context: _ClusteringHeuristicsContext,
) -> int:
    if _is_broad_cluster(cluster, context=context):
        return 6

    anchor_strong_token_set = set(_strong_tokens_for_text(anchor.normalized_query_text, context=context))
    if len(anchor_strong_token_set) < 2:
        return 6

    comparable_members = 0
    clean_members = 0
    for member in cluster.members:
        if member.normalized_query_text == anchor.normalized_query_text:
            continue
        comparable_members += 1
        if _is_clean_member_for_anchor(
            member.normalized_query_text,
            anchor_strong_token_set=anchor_strong_token_set,
            context=context,
        ):
            clean_members += 1

    if comparable_members == 0:
        return 6

    cleanliness_ratio = Decimal(clean_members) / Decimal(comparable_members)
    if cleanliness_ratio >= Decimal("0.7"):
        return 10
    if cleanliness_ratio >= Decimal("0.55"):
        return 8
    return 6


def _select_anchor(cluster: _HybridCluster) -> _AnchorSelection | None:
    head_members = [member for member in cluster.members if member.query_type == "head"]
    if head_members:
        ordered = sorted(
            head_members,
            key=lambda member: (-member.ranking_value_used, member.normalized_query_text),
        )
        return _AnchorSelection(
            normalized_query_text=ordered[0].normalized_query_text,
            provenance="individual",
        )

    if cluster.query_count <= 3 and cluster.members:
        ordered = sorted(
            cluster.members,
            key=lambda member: (-member.ranking_value_used, member.normalized_query_text),
        )
        return _AnchorSelection(
            normalized_query_text=ordered[0].normalized_query_text,
            provenance="fallback",
        )

    return None


def safe_to_inherit(
    query: AnnotatedCanonicalQueryRow,
    anchor: AnnotatedCanonicalQueryRow,
    cluster: _HybridCluster,
    *,
    context: _ClusteringHeuristicsContext | None = None,
) -> tuple[bool, str]:
    """Return whether a cluster member can inherit the selected anchor annotation."""

    effective_context = context or _build_clustering_context([anchor, query])

    if query.normalized_query_text == anchor.normalized_query_text:
        return False, "anchor_row_never_inherits"
    if _is_broad_cluster(cluster, context=effective_context):
        return False, "broad_cluster_flag"
    if cluster.query_count > _relaxed_cluster_size_limit(
        cluster,
        anchor=anchor,
        context=effective_context,
    ):
        return False, "cluster_too_large"
    if _token_count(query.normalized_query_text) <= 1:
        return False, "single_token_generic"
    if query.intent_type not in {"unknown", anchor.intent_type}:
        return False, "intent_conflict"

    anchor_canonical_tokens = _canonical_tokens_for_text(anchor.normalized_query_text, context=effective_context)
    query_canonical_tokens = _canonical_tokens_for_text(query.normalized_query_text, context=effective_context)
    anchor_strong_tokens = _strong_tokens_for_text(anchor.normalized_query_text, context=effective_context)
    query_strong_tokens = _strong_tokens_for_text(query.normalized_query_text, context=effective_context)
    if not anchor_strong_tokens or not query_strong_tokens:
        return False, "missing_lexical_core"

    anchor_token_set = set(anchor_strong_tokens)
    query_token_set = set(query_strong_tokens)
    if not anchor_token_set.intersection(query_token_set):
        return False, "strong_token_conflict"

    if query.query_type == "head":
        if anchor_token_set != query_token_set:
            return False, "head_strong_core_mismatch"

        anchor_canonical_set = set(anchor_canonical_tokens)
        query_canonical_set = set(query_canonical_tokens)
        canonical_overlap = anchor_canonical_set.intersection(query_canonical_set)
        anchor_overlap_ratio = Decimal(len(canonical_overlap)) / Decimal(len(anchor_canonical_set) or 1)
        query_overlap_ratio = Decimal(len(canonical_overlap)) / Decimal(len(query_canonical_set) or 1)
        if min(anchor_overlap_ratio, query_overlap_ratio) < Decimal("0.5"):
            return False, "head_token_overlap_weak"
        if anchor_canonical_set == query_canonical_set:
            return True, "compatible_plural_variant"
        return True, "head_anchor_inheritance"

    anchor_canonical_set = set(anchor_canonical_tokens)
    query_canonical_set = set(query_canonical_tokens)
    if anchor_token_set == query_token_set:
        if anchor_canonical_set == query_canonical_set:
            return True, "compatible_plural_variant"
        return True, "same_family_high_overlap"

    if anchor_token_set.issubset(query_token_set):
        extra_tokens = query_token_set.difference(anchor_token_set)
        if len(extra_tokens) <= 2:
            return True, "compatible_attribute_extension"
        return True, "anchor_inheritance"

    if query_token_set.issubset(anchor_token_set):
        anchor_only_tokens = anchor_token_set.difference(query_token_set)
        if len(anchor_only_tokens) <= 1:
            return True, "same_family_high_overlap"
        return False, "lexical_core_mismatch"

    if (
        _token_overlap_ratio(anchor_token_set, query_token_set) >= Decimal("0.75")
        and len(anchor_token_set.symmetric_difference(query_token_set)) <= 1
        and (
            anchor_canonical_set.issubset(query_canonical_set)
            or query_canonical_set.issubset(anchor_canonical_set)
            or _token_overlap_ratio(anchor_canonical_set, query_canonical_set) >= Decimal("0.75")
        )
    ):
        return True, "same_family_high_overlap"

    return False, "lexical_core_mismatch"


def _hybrid_row(
    row: AnnotatedCanonicalQueryRow,
    *,
    provenance: str,
    intent_type: str,
    query_type: str,
    annotation_reason_code: str,
    inheritance_reason_code: str,
    source_cluster_key: str | None,
    source_anchor_query: str | None,
) -> HybridAnnotatedQueryRow:
    return HybridAnnotatedQueryRow(
        **{
            **row.__dict__,
            "base_query_type": row.query_type,
            "base_intent_type": row.intent_type,
            "base_annotation_reason_code": row.annotation_reason_code,
            "query_type": query_type,
            "intent_type": intent_type,
            "annotation_reason_code": annotation_reason_code,
            "provenance": provenance,
            "source_anchor_query": source_anchor_query,
            "source_cluster_key": source_cluster_key,
            "inheritance_reason_code": inheritance_reason_code,
        }
    )


def _preview_query(row: HybridAnnotatedQueryRow) -> HybridQueryPreview:
    return HybridQueryPreview(
        normalized_query_text=row.normalized_query_text,
        display_query=row.display_query,
        ranking_value_used=_decimal_to_string(row.ranking_value_used),
        bucket=row.query_type,
        cluster_key=row.source_cluster_key,
        provenance=row.provenance,
        source_anchor_query=row.source_anchor_query,
        intent_type=row.intent_type,
        inheritance_reason_code=row.inheritance_reason_code,
    )


def _preview_cluster(
    *,
    cluster: _HybridCluster,
    rejected_count: int,
    anchor_query: str | None,
    issue_reason: str,
) -> HybridClusterPreview:
    query_count = max(int(cluster.query_count or 0), len(cluster.members))
    reject_rate = Decimal(rejected_count) / Decimal(query_count or 1)
    return HybridClusterPreview(
        cluster_key=cluster.cluster_key,
        cluster_label_candidate=cluster.cluster_label_candidate,
        query_count=query_count,
        rejected_count=rejected_count,
        reject_rate=_decimal_to_string(reject_rate),
        anchor_query=anchor_query,
        issue_reason=issue_reason,
    )


def _hybrid_payload(row: HybridAnnotatedQueryRow) -> dict[str, Any]:
    return {
        "provenance": row.provenance,
        "source_anchor_query": row.source_anchor_query,
        "source_cluster_key": row.source_cluster_key,
        "inheritance_reason_code": row.inheritance_reason_code,
        "intent_type": row.intent_type,
        "query_type": row.query_type,
        "annotation_reason_code": row.annotation_reason_code,
    }


def _base_annotation_row(row: HybridAnnotatedQueryRow) -> AnnotatedCanonicalQueryRow:
    payload = dict(row.__dict__)
    for field_name in (
        "base_query_type",
        "base_intent_type",
        "base_annotation_reason_code",
        "provenance",
        "source_anchor_query",
        "source_cluster_key",
        "inheritance_reason_code",
    ):
        payload.pop(field_name, None)
    payload["query_type"] = row.base_query_type
    payload["intent_type"] = row.base_intent_type
    payload["annotation_reason_code"] = row.base_annotation_reason_code
    return AnnotatedCanonicalQueryRow(**payload)


def _hybrid_rationale(row: HybridAnnotatedQueryRow) -> str:
    return (
        f"hybrid={row.provenance}:{row.inheritance_reason_code}; "
        f"query_type={row.query_type}; "
        f"intent={row.intent_type}; "
        f"anchor={row.source_anchor_query or '-'}"
    )


def _persist_hybrid_annotations(
    session: Session,
    *,
    hybrid_rows: list[HybridAnnotatedQueryRow],
) -> tuple[int, int]:
    if not hybrid_rows:
        return 0, 0

    project_id = hybrid_rows[0].project_id
    category_id = hybrid_rows[0].category_id
    annotations_by_key, latest_payload_by_annotation_id = _load_existing_annotations(
        session,
        project_id=project_id,
        category_id=category_id,
    )

    annotations_upserted = 0
    versions_created = 0

    for row in hybrid_rows:
        annotation = annotations_by_key.get(row.normalized_query_text)
        if annotation is None:
            raise ValueError(
                f"Hybrid annotation requires a persisted base annotation for query '{row.normalized_query_text}'"
            )

        latest_payload = dict(latest_payload_by_annotation_id.get(int(annotation.id), {}))
        if not latest_payload:
            base_row = _base_annotation_row(row)
            latest_payload = _annotation_payload(base_row)
            latest_payload["semantic_snapshot"] = _semantic_snapshot(base_row)

        next_payload = dict(latest_payload)
        next_payload["hybrid_annotation"] = _hybrid_payload(row)

        current_changed = False
        latest_version_number = int(annotation.latest_version_number or 0)
        if next_payload != latest_payload:
            persisted_version_number = latest_version_number + 1
            session.add(
                SeoQueryAnnotationVersion(
                    project_id=row.project_id,
                    category_id=row.category_id,
                    annotation_id=annotation.id,
                    version_number=persisted_version_number,
                    annotation_payload=next_payload,
                    rationale=_hybrid_rationale(row),
                )
            )
            annotation.latest_version_number = persisted_version_number
            latest_payload_by_annotation_id[int(annotation.id)] = next_payload
            versions_created += 1
            current_changed = True

        next_meta = dict(annotation.meta or {})
        next_meta["hybrid_annotation"] = _hybrid_payload(row)
        if next_meta != dict(annotation.meta or {}):
            annotation.meta = next_meta
            current_changed = True

        if current_changed:
            annotations_upserted += 1

    session.flush()
    return annotations_upserted, versions_created


def _load_clusters(
    session: Session,
    *,
    project_id: int,
    category_id: int,
) -> tuple[list[_HybridCluster], dict[str, str]]:
    cluster_rows = session.scalars(
        select(SeoQueryCluster).where(
            SeoQueryCluster.project_id == project_id,
            SeoQueryCluster.category_id == category_id,
        )
    ).all()
    if not cluster_rows:
        return [], {}

    cluster_ids = [int(row.id) for row in cluster_rows]
    membership_rows = session.execute(
        select(
            SeoQueryClusterMembership.cluster_id,
            SeoQueryClusterMembership.normalized_query_text,
            SeoQueryClusterMembership.query_type,
            SeoQueryClusterMembership.ranking_value_used,
            SeoQueryClusterMembership.membership_reason_code,
            SeoQueryAnnotation.intent_type,
        )
        .join(SeoQueryAnnotation, SeoQueryAnnotation.id == SeoQueryClusterMembership.annotation_id)
        .where(
            SeoQueryClusterMembership.project_id == project_id,
            SeoQueryClusterMembership.category_id == category_id,
            SeoQueryClusterMembership.cluster_id.in_(cluster_ids),
        )
        .order_by(
            SeoQueryClusterMembership.cluster_id.asc(),
            SeoQueryClusterMembership.ranking_value_used.desc(),
            SeoQueryClusterMembership.normalized_query_text.asc(),
        )
    ).all()

    members_by_cluster_id: dict[int, list[_HybridClusterMember]] = defaultdict(list)
    cluster_key_by_query: dict[str, str] = {}
    for cluster_id, normalized_query_text, query_type, ranking_value_used, membership_reason_code, intent_type in membership_rows:
        normalized_query = str(normalized_query_text)
        members_by_cluster_id[int(cluster_id)].append(
            _HybridClusterMember(
                normalized_query_text=normalized_query,
                query_type=str(query_type),
                ranking_value_used=Decimal(str(ranking_value_used or 0)),
                membership_reason_code=str(membership_reason_code),
                base_intent_type=str(intent_type or "unknown"),
            )
        )
        cluster_key_by_query[normalized_query] = ""

    clusters: list[_HybridCluster] = []
    for cluster_row in cluster_rows:
        cluster_id = int(cluster_row.id)
        cluster_key = str(cluster_row.cluster_key)
        for member in members_by_cluster_id.get(cluster_id, []):
            cluster_key_by_query[member.normalized_query_text] = cluster_key

        clusters.append(
            _HybridCluster(
                cluster_key=cluster_key,
                cluster_label_candidate=str(cluster_row.label or cluster_row.top_query_text or cluster_row.cluster_key),
                top_query_text=str(cluster_row.top_query_text or ""),
                query_count=max(int(cluster_row.query_count or 0), len(members_by_cluster_id.get(cluster_id, []))),
                manual_review_required=bool(cluster_row.manual_review_required),
                members=members_by_cluster_id.get(cluster_id, []),
            )
        )

    clusters.sort(key=lambda cluster: (-cluster.query_count, cluster.cluster_key))
    return clusters, cluster_key_by_query


def _build_hybrid_rows(
    *,
    overlay_rows: list[AnnotatedCanonicalQueryRow],
    clusters: list[_HybridCluster],
    cluster_key_by_query: dict[str, str],
    context: _ClusteringHeuristicsContext,
) -> list[HybridAnnotatedQueryRow]:
    rows_by_query = {row.normalized_query_text: row for row in overlay_rows}
    results: dict[str, HybridAnnotatedQueryRow] = {}

    for row in overlay_rows:
        if not row.is_kept_for_pipeline:
            results[row.normalized_query_text] = _hybrid_row(
                row,
                provenance="rejected",
                intent_type="unknown",
                query_type=row.query_type,
                annotation_reason_code=_HYBRID_REASON_UNKNOWN,
                inheritance_reason_code="not_pipeline_candidate",
                source_cluster_key=None,
                source_anchor_query=None,
            )

    for cluster in clusters:
        anchor_selection = _select_anchor(cluster)
        if anchor_selection is None:
            for member in cluster.members:
                row = rows_by_query.get(member.normalized_query_text)
                if row is None:
                    continue
                results[row.normalized_query_text] = _hybrid_row(
                    row,
                    provenance="rejected",
                    intent_type="unknown",
                    query_type=row.query_type,
                    annotation_reason_code=_HYBRID_REASON_UNKNOWN,
                    inheritance_reason_code="no_anchor",
                    source_cluster_key=cluster.cluster_key,
                    source_anchor_query=None,
                )
            continue

        anchor_row = rows_by_query.get(anchor_selection.normalized_query_text)
        if anchor_row is None:
            continue

        results[anchor_row.normalized_query_text] = _hybrid_row(
            anchor_row,
            provenance=anchor_selection.provenance,
            intent_type=anchor_row.intent_type,
            query_type=anchor_row.query_type,
            annotation_reason_code=anchor_row.annotation_reason_code,
            inheritance_reason_code="individual_anchor" if anchor_selection.provenance == "individual" else "fallback_anchor",
            source_cluster_key=cluster.cluster_key,
            source_anchor_query=None,
        )

        for member in cluster.members:
            if member.normalized_query_text == anchor_row.normalized_query_text:
                continue
            row = rows_by_query.get(member.normalized_query_text)
            if row is None:
                continue
            member_row = AnnotatedCanonicalQueryRow(
                **{
                    **row.__dict__,
                    "query_type": member.query_type,
                }
            )

            can_inherit, reason_code = safe_to_inherit(
                member_row,
                anchor_row,
                cluster,
                context=context,
            )
            if can_inherit:
                results[row.normalized_query_text] = _hybrid_row(
                    row,
                    provenance="cluster",
                    intent_type=anchor_row.intent_type,
                    query_type=anchor_row.query_type,
                    annotation_reason_code=anchor_row.annotation_reason_code,
                    inheritance_reason_code=reason_code,
                    source_cluster_key=cluster.cluster_key,
                    source_anchor_query=anchor_row.normalized_query_text,
                )
                continue

            results[row.normalized_query_text] = _hybrid_row(
                row,
                provenance="rejected",
                intent_type="unknown",
                query_type=member_row.query_type,
                annotation_reason_code=_HYBRID_REASON_UNKNOWN,
                inheritance_reason_code=reason_code,
                source_cluster_key=cluster.cluster_key,
                source_anchor_query=anchor_row.normalized_query_text,
            )

    for row in overlay_rows:
        if row.normalized_query_text in results:
            continue
        results[row.normalized_query_text] = _hybrid_row(
            row,
            provenance="rejected",
            intent_type="unknown",
            query_type=row.query_type,
            annotation_reason_code=_HYBRID_REASON_UNKNOWN,
            inheritance_reason_code="missing_cluster_membership" if row.is_kept_for_pipeline else "not_pipeline_candidate",
            source_cluster_key=cluster_key_by_query.get(row.normalized_query_text),
            source_anchor_query=None,
        )

    return sorted(
        results.values(),
        key=lambda row: (-Decimal(str(row.ranking_value_used)), row.normalized_query_text),
    )


def _build_diagnostics(
    *,
    project_id: int,
    category_id: int,
    hybrid_rows: list[HybridAnnotatedQueryRow],
    clusters: list[_HybridCluster],
    samples_limit: int,
) -> QueryHybridAnnotationDiagnostics:
    counts_by_provenance = {key: 0 for key in _PROVENANCE_KEYS}
    counts_by_reason_code: dict[str, int] = defaultdict(int)
    sample_inherited_queries: list[HybridQueryPreview] = []
    sample_rejected_queries: list[HybridQueryPreview] = []
    sample_inherited_head_member_queries: list[HybridQueryPreview] = []
    sample_rejected_head_member_queries: list[HybridQueryPreview] = []
    top_inherited_relaxed_cases: list[HybridQueryPreview] = []
    top_still_rejected_similar_cases: list[HybridQueryPreview] = []
    rejected_count_by_cluster: dict[str, int] = defaultdict(int)
    anchor_query_by_cluster: dict[str, str] = {}
    inherited_head_member_count = 0
    rejected_head_member_count = 0

    for row in hybrid_rows:
        counts_by_provenance[row.provenance] = counts_by_provenance.get(row.provenance, 0) + 1
        counts_by_reason_code[row.inheritance_reason_code] += 1
        if row.provenance == "cluster" and len(sample_inherited_queries) < samples_limit:
            sample_inherited_queries.append(_preview_query(row))
        if row.provenance == "rejected" and len(sample_rejected_queries) < samples_limit:
            sample_rejected_queries.append(_preview_query(row))
        if row.provenance == "cluster" and row.inheritance_reason_code in _RELAXED_INHERITANCE_REASONS and len(top_inherited_relaxed_cases) < samples_limit:
            top_inherited_relaxed_cases.append(_preview_query(row))
        if (
            row.provenance == "rejected"
            and row.source_anchor_query
            and row.inheritance_reason_code not in {"not_pipeline_candidate", "no_anchor"}
            and len(top_still_rejected_similar_cases) < samples_limit
        ):
            top_still_rejected_similar_cases.append(_preview_query(row))
        if row.provenance == "rejected" and row.source_cluster_key:
            rejected_count_by_cluster[row.source_cluster_key] += 1
        if row.provenance in {"individual", "fallback"} and row.source_cluster_key:
            anchor_query_by_cluster[row.source_cluster_key] = row.normalized_query_text
        if row.base_query_type == "head" and row.provenance == "cluster":
            inherited_head_member_count += 1
            if len(sample_inherited_head_member_queries) < samples_limit:
                sample_inherited_head_member_queries.append(_preview_query(row))
        if row.base_query_type == "head" and row.provenance == "rejected":
            rejected_head_member_count += 1
            if len(sample_rejected_head_member_queries) < samples_limit:
                sample_rejected_head_member_queries.append(_preview_query(row))

    clusters_without_anchor: list[HybridClusterPreview] = []
    clusters_with_high_reject_rate: list[HybridClusterPreview] = []
    for cluster in clusters:
        rejected_count = rejected_count_by_cluster.get(cluster.cluster_key, 0)
        anchor_query = anchor_query_by_cluster.get(cluster.cluster_key)
        if anchor_query is None:
            clusters_without_anchor.append(
                _preview_cluster(
                    cluster=cluster,
                    rejected_count=rejected_count,
                    anchor_query=None,
                    issue_reason="no_anchor",
                )
            )

        reject_rate = Decimal(rejected_count) / Decimal(max(cluster.query_count, 1))
        if reject_rate >= Decimal("0.5"):
            clusters_with_high_reject_rate.append(
                _preview_cluster(
                    cluster=cluster,
                    rejected_count=rejected_count,
                    anchor_query=anchor_query,
                    issue_reason="high_reject_rate",
                )
            )

    clusters_without_anchor.sort(key=lambda item: (-item.query_count, item.cluster_key))
    clusters_with_high_reject_rate.sort(
        key=lambda item: (
            -Decimal(item.reject_rate),
            -item.query_count,
            item.cluster_key,
        )
    )

    return QueryHybridAnnotationDiagnostics(
        project_id=project_id,
        category_id=category_id,
        total_queries_processed=len(hybrid_rows),
        individual_count=counts_by_provenance.get("individual", 0),
        cluster_derived_count=counts_by_provenance.get("cluster", 0),
        rejected_count=counts_by_provenance.get("rejected", 0),
        fallback_count=counts_by_provenance.get("fallback", 0),
        anchor_count=counts_by_provenance.get("individual", 0) + counts_by_provenance.get("fallback", 0),
        inherited_head_member_count=inherited_head_member_count,
        rejected_head_member_count=rejected_head_member_count,
        counts_by_provenance=counts_by_provenance,
        counts_by_inheritance_reason_code=dict(sorted(counts_by_reason_code.items(), key=lambda item: (-item[1], item[0]))),
        sample_inherited_queries=sample_inherited_queries,
        sample_rejected_queries=sample_rejected_queries,
        sample_inherited_head_member_queries=sample_inherited_head_member_queries,
        sample_rejected_head_member_queries=sample_rejected_head_member_queries,
        top_inherited_relaxed_cases=top_inherited_relaxed_cases,
        top_still_rejected_similar_cases=top_still_rejected_similar_cases,
        clusters_without_anchor=clusters_without_anchor[:samples_limit],
        clusters_with_high_reject_rate=clusters_with_high_reject_rate[:samples_limit],
    )


def get_persisted_hybrid_projection(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    refresh_if_missing: bool = False,
    samples_limit: int = 20,
) -> list[HybridAnnotatedQueryRow]:
    """Load persisted hybrid projection from annotation metadata."""

    overlay_rows = _sorted_rows(get_persisted_pruning_overlay(session, project_id=project_id, category_id=category_id))
    if not overlay_rows:
        return []

    annotations_by_key, _latest_payload_by_annotation_id = _load_existing_annotations(
        session,
        project_id=project_id,
        category_id=category_id,
    )
    missing_queries: list[str] = []
    persisted_rows: list[HybridAnnotatedQueryRow] = []

    for base_row in overlay_rows:
        annotation = annotations_by_key.get(base_row.normalized_query_text)
        hybrid_payload = dict((annotation.meta or {}).get("hybrid_annotation") or {}) if annotation is not None else {}
        if not hybrid_payload:
            missing_queries.append(base_row.normalized_query_text)
            continue

        persisted_rows.append(
            _hybrid_row(
                base_row,
                provenance=str(hybrid_payload.get("provenance") or "rejected"),
                intent_type=str(hybrid_payload.get("intent_type") or base_row.intent_type),
                query_type=str(hybrid_payload.get("query_type") or base_row.query_type),
                annotation_reason_code=str(
                    hybrid_payload.get("annotation_reason_code") or base_row.annotation_reason_code
                ),
                inheritance_reason_code=str(hybrid_payload.get("inheritance_reason_code") or "unknown"),
                source_cluster_key=(
                    str(hybrid_payload["source_cluster_key"])
                    if hybrid_payload.get("source_cluster_key") is not None
                    else None
                ),
                source_anchor_query=(
                    str(hybrid_payload["source_anchor_query"])
                    if hybrid_payload.get("source_anchor_query") is not None
                    else None
                ),
            )
        )

    if missing_queries and refresh_if_missing:
        run_query_hybrid_annotation(
            session,
            project_id=project_id,
            category_id=category_id,
            samples_limit=max(1, int(samples_limit)),
            persist=True,
        )
        return get_persisted_hybrid_projection(
            session,
            project_id=project_id,
            category_id=category_id,
            refresh_if_missing=False,
            samples_limit=samples_limit,
        )

    return persisted_rows


def run_query_hybrid_annotation(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    top_limit: int = 20,
    samples_limit: int = 20,
    persist: bool = True,
) -> QueryHybridAnnotationResult:
    """Run deterministic hybrid query annotation for one project/category scope."""

    del top_limit  # Hybrid diagnostics use ranking order and sample limits only.

    if persist:
        run_query_clustering(
            session,
            project_id=project_id,
            category_id=category_id,
            persist=True,
            top_limit=max(1, int(samples_limit)),
            samples_limit=max(1, int(samples_limit)),
        )

    overlay_rows = get_persisted_pruning_overlay(session, project_id=project_id, category_id=category_id)
    clean_rows = get_clean_query_set(session, project_id=project_id, category_id=category_id)
    context = _build_clustering_context(clean_rows) if clean_rows else _build_clustering_context([])
    clusters, cluster_key_by_query = _load_clusters(
        session,
        project_id=project_id,
        category_id=category_id,
    )

    hybrid_rows = _build_hybrid_rows(
        overlay_rows=_sorted_rows(overlay_rows),
        clusters=clusters,
        cluster_key_by_query=cluster_key_by_query,
        context=context,
    )
    diagnostics = _build_diagnostics(
        project_id=project_id,
        category_id=category_id,
        hybrid_rows=hybrid_rows,
        clusters=clusters,
        samples_limit=max(1, int(samples_limit)),
    )

    annotations_upserted = 0
    versions_created = 0
    if persist:
        annotations_upserted, versions_created = _persist_hybrid_annotations(
            session,
            hybrid_rows=hybrid_rows,
        )
        diagnostics = QueryHybridAnnotationDiagnostics(
            **{
                **diagnostics.__dict__,
                "annotations_upserted": annotations_upserted,
                "versions_created": versions_created,
            }
        )

    return QueryHybridAnnotationResult(
        project_id=project_id,
        category_id=category_id,
        annotated_queries=hybrid_rows,
        diagnostics=diagnostics,
        annotations_upserted=annotations_upserted,
        versions_created=versions_created,
    )
