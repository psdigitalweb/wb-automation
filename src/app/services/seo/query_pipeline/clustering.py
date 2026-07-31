"""Deterministic lexical query clustering over the clean query set."""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import combinations
from typing import Any, Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import SeoQueryCluster, SeoQueryClusterMembership
from app.services.seo.query_pipeline.diagnostics import (
    QueryClusterMemberPreview,
    QueryClusterPreview,
    QueryClusteringDiagnostics,
    _serialize_value,
)
from app.services.seo.query_pipeline.pruning import (
    AnnotatedCanonicalQueryRow,
    get_clean_query_set,
    run_query_pruning_and_basic_annotation,
)
from app.services.seo.query_pipeline.unified_dataset import _decimal_to_string


_QUERY_TYPE_KEYS = ("head", "mid", "tail")
_CLUSTER_SIZE_BUCKETS = (
    ("1", lambda size: size == 1),
    ("2", lambda size: size == 2),
    ("3-5", lambda size: 3 <= size <= 5),
    ("6-10", lambda size: 6 <= size <= 10),
    ("11-20", lambda size: 11 <= size <= 20),
    ("21-50", lambda size: 21 <= size <= 50),
    ("51+", lambda size: size >= 51),
)
_WEAK_CONNECTOR_TOKENS = {
    "для",
    "с",
    "со",
    "под",
    "над",
    "на",
    "в",
    "во",
    "и",
    "или",
    "к",
    "ко",
    "из",
    "от",
    "до",
    "у",
    "без",
    "по",
}


@dataclass(frozen=True)
class PersistedQueryClusterView:
    """Readable current-state cluster view with members."""

    project_id: int
    category_id: int
    cluster_id: int
    cluster_key: str
    cluster_label_candidate: str
    top_query_text: str
    query_count: int
    head_query_count: int
    mid_query_count: int
    tail_query_count: int
    members: list[QueryClusterMemberPreview] = field(default_factory=list)
    bucket_filter_used: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)


@dataclass(frozen=True)
class QueryClusteringResult:
    """Clustered current scope plus diagnostics."""

    project_id: int
    category_id: int
    bucket: str | None
    input_queries: list[AnnotatedCanonicalQueryRow]
    clusters: list[PersistedQueryClusterView]
    diagnostics: QueryClusteringDiagnostics


@dataclass(frozen=True)
class _ClusterableQuery:
    row: AnnotatedCanonicalQueryRow
    normalized_query_text: str
    display_query: str
    query_type: str
    ranking_value_used: Decimal
    exact_signature: str
    canonical_signature: str
    tokens: tuple[str, ...]
    canonical_tokens: tuple[str, ...]
    strong_tokens: tuple[str, ...]

    @property
    def token_count(self) -> int:
        return len(self.canonical_tokens)


@dataclass
class _ClusterCandidate:
    seed_signature: str
    members: list[_ClusterableQuery] = field(default_factory=list)
    membership_reason_by_query: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _ClusteringHeuristicsContext:
    token_family_map: dict[str, str]
    weak_tokens: set[str]


def _tokenize(text_value: str) -> tuple[str, ...]:
    return tuple(sorted({token for token in str(text_value or "").split(" ") if token}))


def _signature(tokens: Iterable[str]) -> str:
    return "|".join(sorted({token for token in tokens}))


def _common_prefix_length(left: str, right: str) -> int:
    prefix = 0
    for left_char, right_char in zip(left, right):
        if left_char != right_char:
            break
        prefix += 1
    return prefix


def _looks_like_inflection_variant(left: str, right: str) -> bool:
    if left == right or not left.isalpha() or not right.isalpha():
        return False
    prefix_length = _common_prefix_length(left, right)
    if prefix_length < 5:
        return False
    return max(len(left) - prefix_length, len(right) - prefix_length) <= 4


def _build_clustering_context(rows: Iterable[AnnotatedCanonicalQueryRow]) -> _ClusteringHeuristicsContext:
    token_counts = Counter(token for row in rows for token in _tokenize(row.normalized_query_text))
    ordered_tokens = sorted(token_counts.items(), key=lambda item: (-item[1], item[0]))

    token_family_map: dict[str, str] = {}
    family_leaders: list[str] = []
    for token, count in ordered_tokens:
        if count < 2 or len(token) < 6 or not token.isalpha():
            continue
        leader = next((candidate for candidate in family_leaders if _looks_like_inflection_variant(token, candidate)), None)
        if leader is None:
            family_leaders.append(token)
            token_family_map[token] = token
            continue
        token_family_map[token] = leader

    canonical_token_counts = Counter()
    total_rows = 0
    for row in rows:
        total_rows += 1
        canonical_tokens = {_normalize_token_for_cluster(token, token_family_map=token_family_map) for token in _tokenize(row.normalized_query_text)}
        for token in canonical_tokens:
            canonical_token_counts[token] += 1

    weak_tokens = set(_WEAK_CONNECTOR_TOKENS)
    for token, count in canonical_token_counts.items():
        if total_rows > 0 and count >= 50 and (Decimal(count) / Decimal(total_rows)) >= Decimal("0.35"):
            weak_tokens.add(token)

    return _ClusteringHeuristicsContext(token_family_map=token_family_map, weak_tokens=weak_tokens)


def _normalize_token_for_cluster(token: str, *, token_family_map: dict[str, str]) -> str:
    return token_family_map.get(token, token)


def _strong_tokens(tokens: Iterable[str], *, weak_tokens: set[str]) -> tuple[str, ...]:
    return tuple(sorted(token for token in set(tokens) if token not in weak_tokens))


def _build_clusterable_queries(
    rows: Iterable[AnnotatedCanonicalQueryRow],
    *,
    context: _ClusteringHeuristicsContext,
) -> list[_ClusterableQuery]:
    prepared: list[_ClusterableQuery] = []
    for row in rows:
        tokens = _tokenize(row.normalized_query_text)
        canonical_tokens = tuple(sorted({_normalize_token_for_cluster(token, token_family_map=context.token_family_map) for token in tokens}))
        strong_tokens = _strong_tokens(canonical_tokens, weak_tokens=context.weak_tokens)
        prepared.append(
            _ClusterableQuery(
                row=row,
                normalized_query_text=row.normalized_query_text,
                display_query=row.display_query or row.normalized_query_text,
                query_type=row.query_type,
                ranking_value_used=Decimal(str(row.ranking_value_used)),
                exact_signature=_signature(tokens),
                canonical_signature=_signature(canonical_tokens),
                tokens=tokens,
                canonical_tokens=canonical_tokens,
                strong_tokens=strong_tokens,
            )
        )
    return sorted(prepared, key=lambda item: (item.exact_signature, item.normalized_query_text))


def _candidate_parent_signatures_legacy(item: _ClusterableQuery) -> list[str]:
    if item.token_count < 3:
        return []
    signatures = {_signature(candidate) for candidate in combinations(item.tokens, len(item.tokens) - 1)}
    return sorted(signatures)


def _candidate_parent_signatures_tightened(item: _ClusterableQuery) -> list[str]:
    if item.token_count < 3:
        return []
    signatures = {
        _signature(candidate)
        for candidate in combinations(item.canonical_tokens, len(item.canonical_tokens) - 1)
    }
    return sorted(signatures)


def _choose_parent_signature_legacy(item: _ClusterableQuery, *, exact_groups: dict[str, list[_ClusterableQuery]]) -> str | None:
    candidates: list[tuple[int, int, str]] = []
    for signature in _candidate_parent_signatures_legacy(item):
        if signature not in exact_groups:
            continue
        shared_overlap = len(set(item.tokens).intersection(set(signature.split("|"))))
        signature_token_count = len([token for token in signature.split("|") if token])
        candidates.append((-shared_overlap, signature_token_count, signature))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][2]


def _choose_parent_signature_tightened(
    item: _ClusterableQuery,
    *,
    exact_groups: dict[str, list[_ClusterableQuery]],
    context: _ClusteringHeuristicsContext,
) -> str | None:
    candidates: list[tuple[int, int, int, str]] = []
    for signature in _candidate_parent_signatures_tightened(item):
        if signature not in exact_groups:
            continue
        parent_tokens = tuple(token for token in signature.split("|") if token)
        parent_strong_tokens = _strong_tokens(parent_tokens, weak_tokens=context.weak_tokens)
        if not parent_strong_tokens:
            continue
        shared_overlap = len(set(item.canonical_tokens).intersection(set(parent_tokens)))
        removed_tokens = len(set(item.canonical_tokens).difference(set(parent_tokens)))
        candidates.append((-len(parent_strong_tokens), -shared_overlap, removed_tokens, signature))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][3]


def _assemble_cluster_candidates_legacy(rows: list[AnnotatedCanonicalQueryRow]) -> list[_ClusterCandidate]:
    context = _build_clustering_context(rows)
    clusterable = _build_clusterable_queries(rows, context=context)
    exact_groups: dict[str, list[_ClusterableQuery]] = defaultdict(list)
    for item in clusterable:
        exact_groups[item.exact_signature].append(item)

    cluster_candidates: dict[str, _ClusterCandidate] = {}
    for signature in sorted(exact_groups):
        group = exact_groups[signature]
        if len(group) > 1:
            candidate = cluster_candidates.setdefault(signature, _ClusterCandidate(seed_signature=signature))
            for item in sorted(group, key=lambda member: member.normalized_query_text):
                candidate.members.append(item)
                candidate.membership_reason_by_query[item.normalized_query_text] = "exact_token_signature"
            continue

        item = group[0]
        parent_signature = _choose_parent_signature_legacy(item, exact_groups=exact_groups)
        if parent_signature:
            candidate = cluster_candidates.setdefault(parent_signature, _ClusterCandidate(seed_signature=parent_signature))
            candidate.members.append(item)
            candidate.membership_reason_by_query[item.normalized_query_text] = "superset_plus_one_token"
            continue

        candidate = cluster_candidates.setdefault(signature, _ClusterCandidate(seed_signature=signature))
        candidate.members.append(item)
        candidate.membership_reason_by_query[item.normalized_query_text] = "singleton_fallback"

    return [cluster_candidates[key] for key in sorted(cluster_candidates)]


def _assemble_cluster_candidates(rows: list[AnnotatedCanonicalQueryRow]) -> list[_ClusterCandidate]:
    context = _build_clustering_context(rows)
    clusterable = _build_clusterable_queries(rows, context=context)
    exact_groups: dict[str, list[_ClusterableQuery]] = defaultdict(list)
    for item in clusterable:
        exact_groups[item.canonical_signature].append(item)

    cluster_candidates: dict[str, _ClusterCandidate] = {}
    for signature in sorted(exact_groups):
        group = exact_groups[signature]
        if len(group) > 1:
            candidate = cluster_candidates.setdefault(signature, _ClusterCandidate(seed_signature=signature))
            for item in sorted(group, key=lambda member: (-member.ranking_value_used, member.normalized_query_text)):
                candidate.members.append(item)
                candidate.membership_reason_by_query[item.normalized_query_text] = "canonical_token_signature"
            continue

        item = group[0]
        parent_signature = _choose_parent_signature_tightened(
            item,
            exact_groups=exact_groups,
            context=context,
        )
        if parent_signature:
            candidate = cluster_candidates.setdefault(parent_signature, _ClusterCandidate(seed_signature=parent_signature))
            candidate.members.append(item)
            candidate.membership_reason_by_query[item.normalized_query_text] = "guarded_parent_signature"
            continue

        candidate = cluster_candidates.setdefault(signature, _ClusterCandidate(seed_signature=signature))
        candidate.members.append(item)
        candidate.membership_reason_by_query[item.normalized_query_text] = "singleton_fallback"

    return [cluster_candidates[key] for key in sorted(cluster_candidates)]


def _representative_query(members: list[_ClusterableQuery]) -> _ClusterableQuery:
    return sorted(
        members,
        key=lambda item: (-item.ranking_value_used, item.token_count, item.normalized_query_text),
    )[0]


def _base_signature(members: list[_ClusterableQuery]) -> str:
    return sorted(
        {member.exact_signature for member in members},
        key=lambda signature: (
            len([token for token in signature.split("|") if token]),
            signature,
        ),
    )[0]


def _persisted_cluster_key(base_signature: str) -> str:
    digest = hashlib.sha1(base_signature.encode("utf-8")).hexdigest()
    return f"qcl:v1:{digest}"


def _member_preview(item: _ClusterableQuery, *, membership_reason_code: str) -> QueryClusterMemberPreview:
    return QueryClusterMemberPreview(
        normalized_query_text=item.normalized_query_text,
        display_query=item.display_query,
        query_type=item.query_type,
        ranking_value_used=_decimal_to_string(item.ranking_value_used),
        membership_reason_code=membership_reason_code,
    )


def _cluster_preview(
    *,
    project_id: int,
    category_id: int,
    cluster_key: str,
    cluster_label_candidate: str,
    top_query_text: str,
    query_count: int,
    head_query_count: int,
    mid_query_count: int,
    tail_query_count: int,
    members: list[QueryClusterMemberPreview],
) -> QueryClusterPreview:
    return QueryClusterPreview(
        project_id=project_id,
        category_id=category_id,
        cluster_key=cluster_key,
        cluster_label_candidate=cluster_label_candidate,
        top_query_text=top_query_text,
        query_count=query_count,
        head_query_count=head_query_count,
        mid_query_count=mid_query_count,
        tail_query_count=tail_query_count,
        members=members,
    )


def _build_cluster_views(
    *,
    project_id: int,
    category_id: int,
    bucket: str | None,
    cluster_candidates: list[_ClusterCandidate],
) -> list[PersistedQueryClusterView]:
    cluster_views: list[PersistedQueryClusterView] = []
    for candidate in cluster_candidates:
        ordered_members = sorted(
            candidate.members,
            key=lambda item: (-item.ranking_value_used, item.normalized_query_text),
        )
        representative = _representative_query(ordered_members)
        base_signature = candidate.seed_signature or _base_signature(ordered_members)
        member_previews = [
            _member_preview(member, membership_reason_code=candidate.membership_reason_by_query[member.normalized_query_text])
            for member in ordered_members
        ]
        query_type_counts = Counter(member.query_type for member in ordered_members)
        cluster_key = _persisted_cluster_key(base_signature)
        cluster_views.append(
            PersistedQueryClusterView(
                project_id=project_id,
                category_id=category_id,
                cluster_id=0,
                cluster_key=cluster_key,
                cluster_label_candidate=representative.display_query or representative.normalized_query_text,
                top_query_text=representative.normalized_query_text,
                query_count=len(ordered_members),
                head_query_count=int(query_type_counts.get("head", 0)),
                mid_query_count=int(query_type_counts.get("mid", 0)),
                tail_query_count=int(query_type_counts.get("tail", 0)),
                members=member_previews,
                bucket_filter_used=bucket,
            )
        )
    return sorted(cluster_views, key=lambda item: (-item.query_count, item.cluster_key))


def _persist_clusters(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    bucket: str | None,
    cluster_views: list[PersistedQueryClusterView],
) -> list[PersistedQueryClusterView]:
    existing_clusters = session.scalars(
        select(SeoQueryCluster).where(
            SeoQueryCluster.project_id == project_id,
            SeoQueryCluster.category_id == category_id,
        )
    ).all()
    clusters_by_key = {str(item.cluster_key): item for item in existing_clusters}

    persisted_views: list[PersistedQueryClusterView] = []
    target_keys = {cluster.cluster_key for cluster in cluster_views}

    for cluster_view in cluster_views:
        cluster_row = clusters_by_key.get(cluster_view.cluster_key)
        if cluster_row is None:
            cluster_row = SeoQueryCluster(
                project_id=project_id,
                category_id=category_id,
                cluster_key=cluster_view.cluster_key,
            )
            session.add(cluster_row)
            session.flush()
            clusters_by_key[cluster_view.cluster_key] = cluster_row

        member_signatures = sorted(
            {
                _signature(_tokenize(member.normalized_query_text))
                for member in cluster_view.members
            }
        )
        base_signature = member_signatures[0] if member_signatures else ""
        cluster_row.source_batch_id = None
        cluster_row.label = cluster_view.cluster_label_candidate
        cluster_row.top_query_text = cluster_view.top_query_text
        cluster_row.status = "deterministic_v2"
        cluster_row.is_other = False
        cluster_row.is_noise = False
        cluster_row.manual_review_required = False
        cluster_row.query_count = cluster_view.query_count
        cluster_row.head_query_count = cluster_view.head_query_count
        cluster_row.mid_query_count = cluster_view.mid_query_count
        cluster_row.tail_query_count = cluster_view.tail_query_count
        cluster_row.meta = {
            "base_signature": base_signature,
            "member_signatures": member_signatures,
            "bucket_filter_used": bucket,
        }
        session.flush()

        persisted_views.append(
            PersistedQueryClusterView(
                **{
                    **cluster_view.__dict__,
                    "cluster_id": int(cluster_row.id),
                }
            )
        )

    session.execute(
        delete(SeoQueryClusterMembership).where(
            SeoQueryClusterMembership.project_id == project_id,
            SeoQueryClusterMembership.category_id == category_id,
        )
    )

    stale_cluster_ids = [
        int(item.id)
        for item in existing_clusters
        if str(item.cluster_key) not in target_keys
    ]
    if stale_cluster_ids:
        session.execute(delete(SeoQueryCluster).where(SeoQueryCluster.id.in_(stale_cluster_ids)))

    session.flush()
    return persisted_views


def _cluster_views_with_annotation_ids(
    *,
    cluster_views: list[PersistedQueryClusterView],
    input_queries: list[AnnotatedCanonicalQueryRow],
) -> tuple[list[PersistedQueryClusterView], dict[tuple[str, str], int]]:
    annotation_id_by_query = {
        row.normalized_query_text: int(row.annotation_id)
        for row in input_queries
        if row.annotation_id is not None
    }
    missing = [item.normalized_query_text for cluster in cluster_views for item in cluster.members if item.normalized_query_text not in annotation_id_by_query]
    if missing:
        raise ValueError(f"Clustering requires persisted annotations for all clean queries. Missing: {sorted(set(missing))[:5]}")
    mapping = {
        (cluster.cluster_key, member.normalized_query_text): annotation_id_by_query[member.normalized_query_text]
        for cluster in cluster_views
        for member in cluster.members
    }
    return cluster_views, mapping


def _persist_cluster_memberships(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    persisted_views: list[PersistedQueryClusterView],
    annotation_id_mapping: dict[tuple[str, str], int],
) -> None:
    for cluster_view in persisted_views:
        for member in cluster_view.members:
            session.add(
                SeoQueryClusterMembership(
                    project_id=project_id,
                    category_id=category_id,
                    cluster_id=cluster_view.cluster_id,
                    annotation_id=annotation_id_mapping[(cluster_view.cluster_key, member.normalized_query_text)],
                    normalized_query_text=member.normalized_query_text,
                    query_type=member.query_type,
                    ranking_value_used=Decimal(member.ranking_value_used),
                    membership_reason_code=member.membership_reason_code,
                )
            )
    session.flush()


def _average_cluster_size(cluster_views: list[PersistedQueryClusterView]) -> str:
    if not cluster_views:
        return "0"
    total_queries = sum(item.query_count for item in cluster_views)
    return _decimal_to_string(Decimal(total_queries) / Decimal(len(cluster_views)))


def _cluster_size_distribution(cluster_views: list[PersistedQueryClusterView]) -> dict[str, int]:
    counts = {label: 0 for label, _ in _CLUSTER_SIZE_BUCKETS}
    for cluster in cluster_views:
        for label, predicate in _CLUSTER_SIZE_BUCKETS:
            if predicate(cluster.query_count):
                counts[label] += 1
                break
    return counts


def _preview_clusters(cluster_views: list[PersistedQueryClusterView], *, limit: int) -> list[QueryClusterPreview]:
    return [
        _cluster_preview(
            project_id=item.project_id,
            category_id=item.category_id,
            cluster_key=item.cluster_key,
            cluster_label_candidate=item.cluster_label_candidate,
            top_query_text=item.top_query_text,
            query_count=item.query_count,
            head_query_count=item.head_query_count,
            mid_query_count=item.mid_query_count,
            tail_query_count=item.tail_query_count,
            members=item.members,
        )
        for item in cluster_views[:limit]
    ]


def _small_cluster_previews(cluster_views: list[PersistedQueryClusterView], *, limit: int) -> list[QueryClusterPreview]:
    small_clusters = sorted(
        [item for item in cluster_views if item.query_count <= 2],
        key=lambda item: (item.query_count, item.cluster_key),
    )
    return _preview_clusters(small_clusters, limit=limit)


def _build_diagnostics(
    *,
    project_id: int,
    category_id: int,
    cluster_views: list[PersistedQueryClusterView],
    top_limit: int,
    samples_limit: int,
) -> QueryClusteringDiagnostics:
    counts_by_query_type = {key: 0 for key in _QUERY_TYPE_KEYS}
    singleton_cluster_count = 0
    two_member_cluster_count = 0
    for cluster_view in cluster_views:
        counts_by_query_type["head"] += cluster_view.head_query_count
        counts_by_query_type["mid"] += cluster_view.mid_query_count
        counts_by_query_type["tail"] += cluster_view.tail_query_count
        if cluster_view.query_count == 1:
            singleton_cluster_count += 1
        if cluster_view.query_count == 2:
            two_member_cluster_count += 1

    return QueryClusteringDiagnostics(
        project_id=project_id,
        category_id=category_id,
        total_input_queries=sum(item.query_count for item in cluster_views),
        total_clusters_created=len(cluster_views),
        singleton_cluster_count=singleton_cluster_count,
        two_member_cluster_count=two_member_cluster_count,
        average_cluster_size=_average_cluster_size(cluster_views),
        biggest_cluster_size=max((item.query_count for item in cluster_views), default=0),
        counts_by_query_type=counts_by_query_type,
        cluster_size_distribution=_cluster_size_distribution(cluster_views),
        top_clusters=_preview_clusters(cluster_views, limit=top_limit),
        sample_clusters_with_members=_preview_clusters(cluster_views, limit=samples_limit),
        sample_small_clusters=_small_cluster_previews(cluster_views, limit=samples_limit),
    )


def build_cluster_views_for_rows(
    *,
    project_id: int,
    category_id: int,
    rows: list[AnnotatedCanonicalQueryRow],
    bucket: str | None = None,
    heuristic_version: str = "tightened",
) -> list[PersistedQueryClusterView]:
    if heuristic_version == "legacy":
        cluster_candidates = _assemble_cluster_candidates_legacy(rows)
    elif heuristic_version == "tightened":
        cluster_candidates = _assemble_cluster_candidates(rows)
    else:
        raise ValueError("Unknown clustering heuristic version")

    return _build_cluster_views(
        project_id=project_id,
        category_id=category_id,
        bucket=bucket,
        cluster_candidates=cluster_candidates,
    )


def run_query_clustering(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    bucket: str | None = None,
    top_limit: int = 20,
    samples_limit: int = 20,
    persist: bool = True,
) -> QueryClusteringResult:
    """Run deterministic lexical clustering over the current clean query set."""

    if persist:
        # Clustering operates on the persisted pruning overlay. Refresh it first so
        # a direct clustering run uses the current canonical dataset.
        run_query_pruning_and_basic_annotation(
            session,
            project_id=project_id,
            category_id=category_id,
            top_limit=top_limit,
            samples_limit=samples_limit,
            persist=True,
        )

    input_queries = get_clean_query_set(session, project_id=project_id, category_id=category_id, bucket=bucket)
    cluster_views = build_cluster_views_for_rows(
        project_id=project_id,
        category_id=category_id,
        rows=input_queries,
        bucket=bucket,
    )

    if persist:
        _, annotation_id_mapping = _cluster_views_with_annotation_ids(cluster_views=cluster_views, input_queries=input_queries)
        persisted_views = _persist_clusters(
            session,
            project_id=project_id,
            category_id=category_id,
            bucket=bucket,
            cluster_views=cluster_views,
        )
        _persist_cluster_memberships(
            session,
            project_id=project_id,
            category_id=category_id,
            persisted_views=persisted_views,
            annotation_id_mapping=annotation_id_mapping,
        )
        cluster_views = persisted_views

    diagnostics = _build_diagnostics(
        project_id=project_id,
        category_id=category_id,
        cluster_views=cluster_views,
        top_limit=max(1, int(top_limit)),
        samples_limit=max(1, int(samples_limit)),
    )
    return QueryClusteringResult(
        project_id=project_id,
        category_id=category_id,
        bucket=bucket,
        input_queries=input_queries,
        clusters=cluster_views,
        diagnostics=diagnostics,
    )


def get_query_clusters(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    bucket: str | None = None,
) -> list[PersistedQueryClusterView]:
    """Return current persisted query clusters for one project/category scope."""

    cluster_rows = session.scalars(
        select(SeoQueryCluster).where(
            SeoQueryCluster.project_id == project_id,
            SeoQueryCluster.category_id == category_id,
        )
    ).all()
    membership_rows = session.scalars(
        select(SeoQueryClusterMembership).where(
            SeoQueryClusterMembership.project_id == project_id,
            SeoQueryClusterMembership.category_id == category_id,
        )
    ).all()
    clean_rows = get_clean_query_set(session, project_id=project_id, category_id=category_id)
    display_by_query = {row.normalized_query_text: row.display_query for row in clean_rows}

    members_by_cluster_id: dict[int, list[QueryClusterMemberPreview]] = defaultdict(list)
    for membership in membership_rows:
        if bucket is not None and membership.query_type != bucket:
            continue
        members_by_cluster_id[int(membership.cluster_id)].append(
            QueryClusterMemberPreview(
                normalized_query_text=str(membership.normalized_query_text),
                display_query=display_by_query.get(str(membership.normalized_query_text), str(membership.normalized_query_text)),
                query_type=str(membership.query_type),
                ranking_value_used=_decimal_to_string(Decimal(str(membership.ranking_value_used or 0))),
                membership_reason_code=str(membership.membership_reason_code),
            )
        )

    cluster_views: list[PersistedQueryClusterView] = []
    for cluster_row in cluster_rows:
        cluster_id = int(cluster_row.id)
        members = sorted(
            members_by_cluster_id.get(cluster_id, []),
            key=lambda item: (-Decimal(item.ranking_value_used), item.normalized_query_text),
        )
        if bucket is not None and not members:
            continue
        cluster_views.append(
            PersistedQueryClusterView(
                project_id=int(cluster_row.project_id),
                category_id=int(cluster_row.category_id),
                cluster_id=cluster_id,
                cluster_key=str(cluster_row.cluster_key),
                cluster_label_candidate=str(cluster_row.label or cluster_row.top_query_text or cluster_row.cluster_key),
                top_query_text=str(cluster_row.top_query_text or ""),
                query_count=int(cluster_row.query_count or 0),
                head_query_count=int(cluster_row.head_query_count or 0),
                mid_query_count=int(cluster_row.mid_query_count or 0),
                tail_query_count=int(cluster_row.tail_query_count or 0),
                members=members,
                bucket_filter_used=(cluster_row.meta or {}).get("bucket_filter_used"),
            )
        )
    return sorted(cluster_views, key=lambda item: (-item.query_count, item.cluster_key))
