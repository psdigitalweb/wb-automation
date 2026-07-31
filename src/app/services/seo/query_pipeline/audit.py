"""Deterministic quality audit for pruning and query clustering."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import combinations
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SeoQueryAnnotation, SeoQueryCluster, SeoQueryClusterMembership
from app.services.seo.query_pipeline.clustering import PersistedQueryClusterView, build_cluster_views_for_rows
from app.services.seo.query_pipeline.diagnostics import _serialize_value
from app.services.seo.query_pipeline.pruning import (
    AnnotatedCanonicalQueryRow,
    annotate_canonical_rows,
    detect_single_token_lexical_noise,
    get_persisted_pruning_overlay,
)
from app.services.seo.query_pipeline.unified_dataset import _decimal_to_string, _presence_key, assemble_unified_query_dataset


_CLUSTER_SIZE_BUCKETS = (
    ("1", lambda size: size == 1),
    ("2", lambda size: size == 2),
    ("3-5", lambda size: 3 <= size <= 5),
    ("6-10", lambda size: 6 <= size <= 10),
    ("11-20", lambda size: 11 <= size <= 20),
    ("21+", lambda size: size >= 21),
)


@dataclass(frozen=True)
class AuditQueryExample:
    normalized_query_text: str
    display_query: str
    ranking_value_used: str
    query_type: str
    intent_type: str
    pruning_status: str
    pruning_reason_code: str
    source_presence_key: str
    preparation_flag_reasons: list[str] = field(default_factory=list)
    issue_reason: str | None = None


@dataclass(frozen=True)
class AuditClusterExample:
    cluster_key: str
    cluster_label_candidate: str
    top_query_text: str
    query_count: int
    head_query_count: int
    mid_query_count: int
    tail_query_count: int
    top_member_ranking_value_used: str
    member_samples: list[str] = field(default_factory=list)
    issue_reason: str | None = None


@dataclass(frozen=True)
class AuditClusterPairExample:
    cluster_key_a: str
    cluster_label_candidate_a: str
    query_count_a: int
    cluster_key_b: str
    cluster_label_candidate_b: str
    query_count_b: int
    similarity_score: str
    similarity_basis: str


@dataclass(frozen=True)
class LexicalTighteningMetrics:
    total_clusters: int
    singleton_clusters: int
    two_member_clusters: int
    biggest_cluster_size: int
    suspicious_keep_count: int


@dataclass(frozen=True)
class LexicalTighteningImprovedQueryCase:
    normalized_query_text: str
    ranking_value_used: str
    legacy_cluster_label_candidate: str
    legacy_cluster_query_count: int
    tightened_cluster_label_candidate: str
    tightened_cluster_query_count: int


@dataclass(frozen=True)
class LexicalTighteningAudit:
    legacy_metrics: LexicalTighteningMetrics
    tightened_metrics: LexicalTighteningMetrics
    legacy_top_biggest_clusters: list[AuditClusterExample] = field(default_factory=list)
    tightened_top_biggest_clusters: list[AuditClusterExample] = field(default_factory=list)
    legacy_top_near_duplicate_clusters: list[AuditClusterPairExample] = field(default_factory=list)
    tightened_top_near_duplicate_clusters: list[AuditClusterPairExample] = field(default_factory=list)
    improved_query_cases: list[LexicalTighteningImprovedQueryCase] = field(default_factory=list)


@dataclass(frozen=True)
class QueryPipelineAudit:
    counts_by_pruning_reason_code: dict[str, int] = field(default_factory=dict)
    query_distribution_by_intent_type: dict[str, int] = field(default_factory=dict)
    query_distribution_by_bucket: dict[str, int] = field(default_factory=dict)
    query_distribution_by_intent_and_bucket: dict[str, dict[str, int]] = field(default_factory=dict)
    kept_flag_counts: dict[str, int] = field(default_factory=dict)
    suspicious_kept_issue_counts: dict[str, int] = field(default_factory=dict)
    kept_with_navigation_flag_count: int = 0
    kept_with_informational_flag_count: int = 0
    kept_with_garbage_flag_count: int = 0
    top_suspicious_kept_queries: list[AuditQueryExample] = field(default_factory=list)
    top_review_queries: list[AuditQueryExample] = field(default_factory=list)
    cluster_size_distribution: dict[str, int] = field(default_factory=dict)
    two_member_cluster_count: int = 0
    top_biggest_clusters: list[AuditClusterExample] = field(default_factory=list)
    top_singleton_clusters_by_ranking: list[AuditClusterExample] = field(default_factory=list)
    top_small_high_ranking_clusters: list[AuditClusterExample] = field(default_factory=list)
    top_generic_label_clusters: list[AuditClusterExample] = field(default_factory=list)
    top_near_duplicate_clusters: list[AuditClusterPairExample] = field(default_factory=list)
    lexical_tightening: LexicalTighteningAudit | None = None

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)


@dataclass(frozen=True)
class _ClusterMemberAudit:
    normalized_query_text: str
    query_type: str
    ranking_value_used: Decimal
    intent_type: str
    membership_reason_code: str


@dataclass(frozen=True)
class _ClusterAudit:
    cluster_key: str
    cluster_label_candidate: str
    top_query_text: str
    query_count: int
    head_query_count: int
    mid_query_count: int
    tail_query_count: int
    base_signature: str
    members: list[_ClusterMemberAudit]

    @property
    def top_member_ranking(self) -> Decimal:
        if not self.members:
            return Decimal("0")
        return max(member.ranking_value_used for member in self.members)


def _tokenize(text_value: str) -> tuple[str, ...]:
    return tuple(sorted({token for token in str(text_value or "").split(" ") if token}))


def _append_limited(items: list[Any], item: Any, *, limit: int) -> None:
    if len(items) < limit:
        items.append(item)


def _query_example(row: AnnotatedCanonicalQueryRow, *, issue_reason: str | None = None) -> AuditQueryExample:
    return AuditQueryExample(
        normalized_query_text=row.normalized_query_text,
        display_query=row.display_query,
        ranking_value_used=_decimal_to_string(row.ranking_value_used),
        query_type=row.query_type,
        intent_type=row.intent_type,
        pruning_status=row.pruning_status,
        pruning_reason_code=row.pruning_reason_code,
        source_presence_key=_presence_key(row.source_presence),
        preparation_flag_reasons=list(row.preparation_flag_reasons),
        issue_reason=issue_reason,
    )


def _cluster_example(cluster: _ClusterAudit, *, issue_reason: str | None = None) -> AuditClusterExample:
    return AuditClusterExample(
        cluster_key=cluster.cluster_key,
        cluster_label_candidate=cluster.cluster_label_candidate,
        top_query_text=cluster.top_query_text,
        query_count=cluster.query_count,
        head_query_count=cluster.head_query_count,
        mid_query_count=cluster.mid_query_count,
        tail_query_count=cluster.tail_query_count,
        top_member_ranking_value_used=_decimal_to_string(cluster.top_member_ranking),
        member_samples=[member.normalized_query_text for member in cluster.members[:5]],
        issue_reason=issue_reason,
    )


def _suspicious_keep_reasons(
    row: AnnotatedCanonicalQueryRow,
    *,
    single_token_noise_reasons: dict[str, str],
) -> list[str]:
    reasons: list[str] = []
    tokens = [token for token in row.normalized_query_text.split(" ") if token]
    if row.is_navigation_candidate:
        reasons.append("navigation_marker_kept")
    if row.is_informational_candidate:
        reasons.append("informational_marker_kept")
    if row.is_garbage_candidate:
        reasons.append("garbage_like_kept")
    if len(tokens) == 1 and tokens[0] in single_token_noise_reasons:
        reasons.append(single_token_noise_reasons[tokens[0]])
    if row.ranking_value_used <= 0:
        reasons.append("zero_signal_keep")
    if len(row.normalized_query_text) <= 2:
        reasons.append("very_short_keep")
    return reasons


def _cluster_size_distribution(clusters: list[_ClusterAudit]) -> dict[str, int]:
    counts = {label: 0 for label, _ in _CLUSTER_SIZE_BUCKETS}
    for cluster in clusters:
        for label, predicate in _CLUSTER_SIZE_BUCKETS:
            if predicate(cluster.query_count):
                counts[label] += 1
                break
    return counts


def _load_clusters(session: Session, *, project_id: int, category_id: int) -> list[_ClusterAudit]:
    cluster_rows = session.scalars(
        select(SeoQueryCluster).where(
            SeoQueryCluster.project_id == project_id,
            SeoQueryCluster.category_id == category_id,
        )
    ).all()
    if not cluster_rows:
        return []

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

    members_by_cluster_id: dict[int, list[_ClusterMemberAudit]] = defaultdict(list)
    for cluster_id, normalized_query_text, query_type, ranking_value_used, membership_reason_code, intent_type in membership_rows:
        members_by_cluster_id[int(cluster_id)].append(
            _ClusterMemberAudit(
                normalized_query_text=str(normalized_query_text),
                query_type=str(query_type),
                ranking_value_used=Decimal(str(ranking_value_used or 0)),
                intent_type=str(intent_type or "unknown"),
                membership_reason_code=str(membership_reason_code),
            )
        )

    clusters: list[_ClusterAudit] = []
    for row in cluster_rows:
        meta = dict(row.meta or {})
        clusters.append(
            _ClusterAudit(
                cluster_key=str(row.cluster_key),
                cluster_label_candidate=str(row.label or row.top_query_text or row.cluster_key),
                top_query_text=str(row.top_query_text or ""),
                query_count=int(row.query_count or 0),
                head_query_count=int(row.head_query_count or 0),
                mid_query_count=int(row.mid_query_count or 0),
                tail_query_count=int(row.tail_query_count or 0),
                base_signature=str(meta.get("base_signature") or ""),
                members=members_by_cluster_id.get(int(row.id), []),
            )
        )
    return sorted(clusters, key=lambda item: (-item.query_count, item.cluster_key))


def _cluster_audit_from_views(cluster_views: list[PersistedQueryClusterView]) -> list[_ClusterAudit]:
    return [
        _ClusterAudit(
            cluster_key=cluster.cluster_key,
            cluster_label_candidate=cluster.cluster_label_candidate,
            top_query_text=cluster.top_query_text,
            query_count=cluster.query_count,
            head_query_count=cluster.head_query_count,
            mid_query_count=cluster.mid_query_count,
            tail_query_count=cluster.tail_query_count,
            base_signature="",
            members=[
                _ClusterMemberAudit(
                    normalized_query_text=member.normalized_query_text,
                    query_type=member.query_type,
                    ranking_value_used=Decimal(str(member.ranking_value_used)),
                    intent_type="unknown",
                    membership_reason_code=member.membership_reason_code,
                )
                for member in cluster.members
            ],
        )
        for cluster in cluster_views
    ]


def _generic_label_clusters(clusters: list[_ClusterAudit], *, limit: int) -> list[AuditClusterExample]:
    generic = [
        cluster
        for cluster in clusters
        if len(_tokenize(cluster.cluster_label_candidate)) <= 1
    ]
    generic.sort(key=lambda item: (-item.query_count, -item.top_member_ranking, item.cluster_label_candidate))
    return [_cluster_example(cluster, issue_reason="single_token_label_candidate") for cluster in generic[:limit]]


def _near_duplicate_cluster_pairs(clusters: list[_ClusterAudit], *, limit: int) -> list[AuditClusterPairExample]:
    cluster_lookup: dict[str, dict[str, Any]] = {}
    exact_label_groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
    parent_signature_groups: dict[tuple[str, ...], list[str]] = defaultdict(list)

    for cluster in clusters:
        signature_tokens = _tokenize(cluster.base_signature.replace("|", " ")) if cluster.base_signature else _tokenize(cluster.cluster_label_candidate)
        label_tokens = _tokenize(cluster.cluster_label_candidate)
        cluster_lookup[cluster.cluster_key] = {
            "cluster": cluster,
            "signature_tokens": signature_tokens,
            "label_tokens": label_tokens,
        }
        if label_tokens:
            exact_label_groups[label_tokens].append(cluster.cluster_key)
        if len(signature_tokens) >= 2:
            for index in range(len(signature_tokens)):
                parent_signature = signature_tokens[:index] + signature_tokens[index + 1 :]
                if parent_signature:
                    parent_signature_groups[parent_signature].append(cluster.cluster_key)

    candidate_pairs: dict[tuple[str, str], AuditClusterPairExample] = {}

    def register_pair(key_a: str, key_b: str, *, basis: str) -> None:
        pair_key = tuple(sorted((key_a, key_b)))
        if pair_key[0] == pair_key[1] or pair_key in candidate_pairs:
            return

        cluster_a = cluster_lookup[pair_key[0]]["cluster"]
        cluster_b = cluster_lookup[pair_key[1]]["cluster"]
        signature_a = set(cluster_lookup[pair_key[0]]["signature_tokens"])
        signature_b = set(cluster_lookup[pair_key[1]]["signature_tokens"])
        union = signature_a.union(signature_b)
        overlap_ratio = Decimal(len(signature_a.intersection(signature_b))) / Decimal(len(union) or 1)

        candidate_pairs[pair_key] = AuditClusterPairExample(
            cluster_key_a=cluster_a.cluster_key,
            cluster_label_candidate_a=cluster_a.cluster_label_candidate,
            query_count_a=cluster_a.query_count,
            cluster_key_b=cluster_b.cluster_key,
            cluster_label_candidate_b=cluster_b.cluster_label_candidate,
            query_count_b=cluster_b.query_count,
            similarity_score=_decimal_to_string(overlap_ratio),
            similarity_basis=basis,
        )

    for keys in exact_label_groups.values():
        if len(keys) < 2:
            continue
        ordered = sorted(
            keys,
            key=lambda item: (
                -cluster_lookup[item]["cluster"].query_count,
                -cluster_lookup[item]["cluster"].top_member_ranking,
                cluster_lookup[item]["cluster"].cluster_key,
            ),
        )
        for key_a, key_b in combinations(ordered[:6], 2):
            register_pair(key_a, key_b, basis="exact_label_signature")

    for keys in parent_signature_groups.values():
        if len(keys) < 2:
            continue
        ordered = sorted(
            set(keys),
            key=lambda item: (
                -cluster_lookup[item]["cluster"].query_count,
                -cluster_lookup[item]["cluster"].top_member_ranking,
                cluster_lookup[item]["cluster"].cluster_key,
            ),
        )
        for key_a, key_b in combinations(ordered[:6], 2):
            label_a = cluster_lookup[key_a]["cluster"].cluster_label_candidate
            label_b = cluster_lookup[key_b]["cluster"].cluster_label_candidate
            if label_a in label_b or label_b in label_a:
                register_pair(key_a, key_b, basis="label_containment")
                continue
            signature_a = set(cluster_lookup[key_a]["signature_tokens"])
            signature_b = set(cluster_lookup[key_b]["signature_tokens"])
            union = signature_a.union(signature_b)
            overlap_ratio = Decimal(len(signature_a.intersection(signature_b))) / Decimal(len(union) or 1)
            if overlap_ratio >= Decimal("0.5"):
                register_pair(key_a, key_b, basis="signature_overlap_parent")

    pairs = sorted(
        candidate_pairs.values(),
        key=lambda item: (
            -Decimal(item.similarity_score),
            -(item.query_count_a + item.query_count_b),
            item.cluster_label_candidate_a,
            item.cluster_label_candidate_b,
        ),
    )
    return pairs[:limit]


def _suspicious_keep_counter(rows: list[AnnotatedCanonicalQueryRow]) -> tuple[Counter[str], list[AuditQueryExample]]:
    suspicious_reasons = detect_single_token_lexical_noise(rows)
    issue_counts = Counter()
    examples: list[AuditQueryExample] = []
    for row in sorted(rows, key=lambda item: (-item.ranking_value_used, item.normalized_query_text)):
        if not row.is_kept_for_pipeline:
            continue
        reasons = _suspicious_keep_reasons(row, single_token_noise_reasons=suspicious_reasons)
        if not reasons:
            continue
        for reason in reasons:
            issue_counts[reason] += 1
        _append_limited(examples, _query_example(row, issue_reason=reasons[0]), limit=20)
    return issue_counts, examples


def _tightening_metrics(
    rows: list[AnnotatedCanonicalQueryRow],
    clusters: list[_ClusterAudit],
) -> LexicalTighteningMetrics:
    suspicious_issue_counts, _ = _suspicious_keep_counter(rows)
    return LexicalTighteningMetrics(
        total_clusters=len(clusters),
        singleton_clusters=sum(1 for cluster in clusters if cluster.query_count == 1),
        two_member_clusters=sum(1 for cluster in clusters if cluster.query_count == 2),
        biggest_cluster_size=max((cluster.query_count for cluster in clusters), default=0),
        suspicious_keep_count=sum(suspicious_issue_counts.values()),
    )


def _improved_query_cases(
    legacy_rows: list[AnnotatedCanonicalQueryRow],
    legacy_clusters: list[_ClusterAudit],
    tightened_rows: list[AnnotatedCanonicalQueryRow],
    tightened_clusters: list[_ClusterAudit],
    *,
    limit: int,
) -> list[LexicalTighteningImprovedQueryCase]:
    legacy_cluster_by_query = {
        member.normalized_query_text: cluster
        for cluster in legacy_clusters
        for member in cluster.members
    }
    tightened_cluster_by_query = {
        member.normalized_query_text: cluster
        for cluster in tightened_clusters
        for member in cluster.members
    }
    ranking_by_query = {
        row.normalized_query_text: Decimal(str(row.ranking_value_used))
        for row in legacy_rows + tightened_rows
    }
    cases: list[LexicalTighteningImprovedQueryCase] = []
    for query_text, legacy_cluster in legacy_cluster_by_query.items():
        tightened_cluster = tightened_cluster_by_query.get(query_text)
        if tightened_cluster is None:
            continue
        reduction = legacy_cluster.query_count - tightened_cluster.query_count
        if reduction <= 0 or legacy_cluster.cluster_label_candidate == tightened_cluster.cluster_label_candidate:
            continue
        cases.append(
            LexicalTighteningImprovedQueryCase(
                normalized_query_text=query_text,
                ranking_value_used=_decimal_to_string(ranking_by_query.get(query_text, Decimal("0"))),
                legacy_cluster_label_candidate=legacy_cluster.cluster_label_candidate,
                legacy_cluster_query_count=legacy_cluster.query_count,
                tightened_cluster_label_candidate=tightened_cluster.cluster_label_candidate,
                tightened_cluster_query_count=tightened_cluster.query_count,
            )
        )
    return sorted(
        cases,
        key=lambda item: (
            -(item.legacy_cluster_query_count - item.tightened_cluster_query_count),
            -Decimal(item.ranking_value_used),
            item.normalized_query_text,
        ),
    )[:limit]


def run_query_pipeline_audit(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    overlay_rows: list[AnnotatedCanonicalQueryRow] | None = None,
    limit: int = 20,
) -> QueryPipelineAudit:
    overlay_rows = overlay_rows or get_persisted_pruning_overlay(session, project_id=project_id, category_id=category_id)
    single_token_noise_reasons = detect_single_token_lexical_noise(overlay_rows)
    counts_by_pruning_reason_code = Counter(row.pruning_reason_code for row in overlay_rows)
    query_distribution_by_intent_type = Counter(row.intent_type for row in overlay_rows)
    query_distribution_by_bucket = Counter(row.query_type for row in overlay_rows)
    intent_bucket_matrix: dict[str, dict[str, int]] = defaultdict(lambda: {"head": 0, "mid": 0, "tail": 0})

    kept_flag_counts = Counter()
    suspicious_kept_issue_counts = Counter()
    suspicious_kept_queries: list[AuditQueryExample] = []
    review_queries: list[AuditQueryExample] = []
    kept_navigation = 0
    kept_informational = 0
    kept_garbage = 0

    sorted_rows = sorted(
        overlay_rows,
        key=lambda row: (-row.ranking_value_used, row.normalized_query_text),
    )

    for row in sorted_rows:
        intent_bucket_matrix[row.intent_type][row.query_type] += 1
        if row.pruning_status == "review":
            _append_limited(review_queries, _query_example(row), limit=limit)
        if not row.is_kept_for_pipeline:
            continue

        for reason in row.preparation_flag_reasons:
            kept_flag_counts[reason] += 1
        if row.is_navigation_candidate:
            kept_navigation += 1
        if row.is_informational_candidate:
            kept_informational += 1
        if row.is_garbage_candidate:
            kept_garbage += 1

        suspicious_reasons = _suspicious_keep_reasons(
            row,
            single_token_noise_reasons=single_token_noise_reasons,
        )
        if suspicious_reasons:
            for reason in suspicious_reasons:
                suspicious_kept_issue_counts[reason] += 1
            _append_limited(
                suspicious_kept_queries,
                _query_example(row, issue_reason=suspicious_reasons[0]),
                limit=limit,
            )

    clusters = _load_clusters(session, project_id=project_id, category_id=category_id)
    biggest_clusters = [_cluster_example(cluster) for cluster in clusters[:limit]]

    singletons = [cluster for cluster in clusters if cluster.query_count == 1]
    singletons.sort(key=lambda item: (-item.top_member_ranking, item.cluster_key))
    singleton_clusters = [_cluster_example(cluster, issue_reason="singleton_cluster") for cluster in singletons[:limit]]

    small_high_ranking = [cluster for cluster in clusters if cluster.query_count <= 2]
    small_high_ranking.sort(key=lambda item: (-item.top_member_ranking, item.query_count, item.cluster_key))
    small_high_ranking_clusters = [
        _cluster_example(cluster, issue_reason="small_cluster_high_signal")
        for cluster in small_high_ranking[:limit]
    ]

    unified_dataset = assemble_unified_query_dataset(
        session,
        project_id=project_id,
        category_id=category_id,
        top_limit=limit,
        samples_limit=limit,
    )
    legacy_overlay_rows = annotate_canonical_rows(unified_dataset.canonical_queries, rule_version="legacy")
    legacy_kept_rows = [row for row in legacy_overlay_rows if row.is_kept_for_pipeline]
    legacy_cluster_views = build_cluster_views_for_rows(
        project_id=project_id,
        category_id=category_id,
        rows=legacy_kept_rows,
        heuristic_version="legacy",
    )
    legacy_clusters = _cluster_audit_from_views(legacy_cluster_views)

    return QueryPipelineAudit(
        counts_by_pruning_reason_code=dict(sorted(counts_by_pruning_reason_code.items())),
        query_distribution_by_intent_type=dict(sorted(query_distribution_by_intent_type.items())),
        query_distribution_by_bucket=dict(sorted(query_distribution_by_bucket.items())),
        query_distribution_by_intent_and_bucket={key: value for key, value in sorted(intent_bucket_matrix.items())},
        kept_flag_counts=dict(sorted(kept_flag_counts.items())),
        suspicious_kept_issue_counts=dict(sorted(suspicious_kept_issue_counts.items())),
        kept_with_navigation_flag_count=kept_navigation,
        kept_with_informational_flag_count=kept_informational,
        kept_with_garbage_flag_count=kept_garbage,
        top_suspicious_kept_queries=suspicious_kept_queries,
        top_review_queries=review_queries,
        cluster_size_distribution=_cluster_size_distribution(clusters),
        two_member_cluster_count=sum(1 for cluster in clusters if cluster.query_count == 2),
        top_biggest_clusters=biggest_clusters,
        top_singleton_clusters_by_ranking=singleton_clusters,
        top_small_high_ranking_clusters=small_high_ranking_clusters,
        top_generic_label_clusters=_generic_label_clusters(clusters, limit=limit),
        top_near_duplicate_clusters=_near_duplicate_cluster_pairs(clusters, limit=limit),
        lexical_tightening=LexicalTighteningAudit(
            legacy_metrics=_tightening_metrics(legacy_overlay_rows, legacy_clusters),
            tightened_metrics=_tightening_metrics(overlay_rows, clusters),
            legacy_top_biggest_clusters=[_cluster_example(cluster) for cluster in legacy_clusters[:limit]],
            tightened_top_biggest_clusters=biggest_clusters,
            legacy_top_near_duplicate_clusters=_near_duplicate_cluster_pairs(legacy_clusters, limit=limit),
            tightened_top_near_duplicate_clusters=_near_duplicate_cluster_pairs(clusters, limit=limit),
            improved_query_cases=_improved_query_cases(
                legacy_overlay_rows,
                legacy_clusters,
                overlay_rows,
                clusters,
                limit=limit,
            ),
        ),
    )
