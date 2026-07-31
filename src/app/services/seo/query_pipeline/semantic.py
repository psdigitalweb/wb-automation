"""Experimental semantic clustering for SEO query pipeline."""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.services.seo.query_pipeline.clustering import (
    PersistedQueryClusterView,
    get_query_clusters,
    run_query_clustering,
)
from app.services.seo.query_pipeline.diagnostics import _serialize_value
from app.services.seo.query_pipeline.pruning import AnnotatedCanonicalQueryRow, get_clean_query_set
from app.services.seo.query_pipeline.unified_dataset import _decimal_to_string


DEFAULT_SEMANTIC_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_SIMILARITY_THRESHOLD = Decimal("0.80")
DEFAULT_MIN_COMMUNITY_SIZE = 2
DEFAULT_COMMUNITY_BATCH_SIZE = 1024
DEFAULT_GATING_STRATEGY = "anchor_family_gate"
AVAILABLE_GATING_STRATEGIES = {
    "bucket_gate": "Bucket Gate",
    "token_length_gate": "Token Length Gate",
    "family_gate": "Family Gate",
    "anchor_family_gate": "Anchor + Family Gate",
}
_MODEL_CACHE: dict[str, Any] = {}
_TOKEN_RE = re.compile(r"[^0-9a-zа-яё]+", re.IGNORECASE)
_CLUSTER_SIZE_BUCKETS = (
    ("1", lambda size: size == 1),
    ("2", lambda size: size == 2),
    ("3-5", lambda size: 3 <= size <= 5),
    ("6-10", lambda size: 6 <= size <= 10),
    ("11-20", lambda size: 11 <= size <= 20),
    ("21-50", lambda size: 21 <= size <= 50),
    ("51-200", lambda size: 51 <= size <= 200),
    ("201+", lambda size: size >= 201),
)
_STOPWORDS = {"для", "с", "со", "на", "под", "над", "из", "как", "в", "во", "и", "или", "к", "ко", "по", "от", "до", "у", "за", "без", "про", "при", "не"}
_CATEGORY_TOKENS = {"тарелка", "тарелки", "тарелок", "тарелке", "тарелку", "тарелкой", "тарелкам", "тарелками", "тарелках", "тарелочка", "тарелочки", "тарелочку", "тарелочек"}
_SET_MARKERS = {"набор", "наборы", "комплект", "комплекты", "сервиз", "сервизы"}
_QTY_MARKERS = {"шт", "штук", "штуки", "персон", "предмет", "предмета", "предметов", "см", "мм"}
_DECOR_MARKERS = {"цветочками", "сердечками", "бантиками", "лимонами", "гусями", "зайчиком", "кроликом", "котиками", "пчелами", "бабочками"}
_USE_CASE_MARKERS = {"супа", "суповые", "суповая", "сервировки", "второго", "салата", "пасты", "микроволновки", "рамена", "завтрака", "десерта", "закусок", "пиццы", "конфет", "похудения"}
_MATERIAL_MARKERS = {"керамика", "керамическая", "керамические", "стекло", "стеклянная", "стеклянные", "фарфор", "фарфоровая", "фарфоровые", "пластик", "пластиковая", "пластиковые", "бумажная", "бумажные", "бамбук", "бамбуковая", "бамбуковые", "деревянная", "деревянные"}
_GENERIC_FAMILY_MARKERS = _SET_MARKERS | _QTY_MARKERS


@dataclass(frozen=True)
class SemanticClusterMemberPreview:
    normalized_query_text: str
    display_query: str
    query_type: str
    intent_type: str
    ranking_value_used: str
    assignment_reason_code: str


@dataclass(frozen=True)
class SemanticClusterPreview:
    project_id: int
    category_id: int
    cluster_key: str
    cluster_label_candidate: str
    top_query_text: str
    query_count: int
    head_query_count: int
    mid_query_count: int
    tail_query_count: int
    semantic_kind: str
    member_samples: list[str] = field(default_factory=list)
    members: list[SemanticClusterMemberPreview] = field(default_factory=list)


@dataclass(frozen=True)
class SemanticNoiseQueryPreview:
    normalized_query_text: str
    display_query: str
    ranking_value_used: str
    query_type: str
    intent_type: str


@dataclass(frozen=True)
class ComparisonGroupPreview:
    cluster_key: str
    cluster_label_candidate: str
    query_count: int
    sample_queries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SemanticOverbroadCase:
    semantic_cluster_key: str
    semantic_cluster_label_candidate: str
    semantic_query_count: int
    lexical_group_count: int
    dominant_lexical_group_share: str
    lexical_groups: list[ComparisonGroupPreview] = field(default_factory=list)
    sample_queries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SemanticGroupingCase:
    semantic_cluster_key: str
    semantic_cluster_label_candidate: str
    semantic_query_count: int
    lexical_group_count: int
    lexical_groups: list[ComparisonGroupPreview] = field(default_factory=list)
    sample_queries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class QueryAssignmentComparison:
    normalized_query_text: str
    ranking_value_used: str
    query_type: str
    lexical_cluster_label_candidate: str
    lexical_cluster_query_count: int
    semantic_cluster_label_candidate: str
    semantic_cluster_query_count: int
    semantic_kind: str


@dataclass(frozen=True)
class SemanticSegmentPreview:
    segment_key: str
    query_count: int


@dataclass(frozen=True)
class SemanticClusteringDiagnostics:
    project_id: int
    category_id: int
    model_name: str
    clustering_backend: str
    similarity_threshold: str
    min_community_size: int
    gating_strategy: str
    strategy_label: str
    total_input_queries: int
    total_semantic_clusters: int
    multi_member_cluster_count: int
    singleton_noise_count: int
    average_cluster_size: str
    biggest_cluster_size: int
    segment_count: int
    largest_segment_size: int
    counts_by_query_type: dict[str, int] = field(default_factory=dict)
    cluster_size_distribution: dict[str, int] = field(default_factory=dict)
    top_segments: list[SemanticSegmentPreview] = field(default_factory=list)
    top_semantic_clusters: list[SemanticClusterPreview] = field(default_factory=list)
    sample_noise_queries: list[SemanticNoiseQueryPreview] = field(default_factory=list)


@dataclass(frozen=True)
class SemanticVsLexicalComparisonDiagnostics:
    project_id: int
    category_id: int
    total_input_queries: int
    total_lexical_clusters: int
    total_semantic_clusters: int
    lexical_singleton_count: int
    semantic_singleton_noise_count: int
    top_lexical_clusters: list[SemanticClusterPreview] = field(default_factory=list)
    top_semantic_clusters: list[SemanticClusterPreview] = field(default_factory=list)
    semantic_overbroad_cases: list[SemanticOverbroadCase] = field(default_factory=list)
    semantic_grouped_fragment_cases: list[SemanticGroupingCase] = field(default_factory=list)
    top_query_assignments: list[QueryAssignmentComparison] = field(default_factory=list)


@dataclass(frozen=True)
class LexicalClusteringSummary:
    total_clusters: int
    singleton_cluster_count: int
    average_cluster_size: str
    biggest_cluster_size: int
    cluster_size_distribution: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticImprovementSummary:
    raw_biggest_cluster_size: int
    gated_biggest_cluster_size: int
    biggest_cluster_reduction: int
    raw_total_clusters: int
    gated_total_clusters: int
    raw_singleton_noise_count: int
    gated_singleton_noise_count: int


@dataclass(frozen=True)
class SemanticClusteringExperimentResult:
    project_id: int
    category_id: int
    bucket: str | None
    model_name: str
    strategy: str
    lexical_summary: LexicalClusteringSummary
    raw_semantic: SemanticClusteringDiagnostics
    raw_comparison: SemanticVsLexicalComparisonDiagnostics
    gated_semantic: SemanticClusteringDiagnostics
    gated_comparison: SemanticVsLexicalComparisonDiagnostics
    improvement_summary: SemanticImprovementSummary

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)

    def to_debug_payload(self) -> dict[str, Any]:
        return _serialize_value(
            {
                "project_id": self.project_id,
                "category_id": self.category_id,
                "bucket": self.bucket,
                "model_name": self.model_name,
                "strategy": self.strategy,
                "available_strategies": AVAILABLE_GATING_STRATEGIES,
                "lexical_summary": self.lexical_summary,
                "raw_semantic": self.raw_semantic,
                "raw_comparison": self.raw_comparison,
                "gated_semantic": self.gated_semantic,
                "gated_comparison": self.gated_comparison,
                "improvement_summary": self.improvement_summary,
            }
        )


@dataclass(frozen=True)
class _PreparedQuery:
    row: AnnotatedCanonicalQueryRow
    normalized_query_text: str
    display_query: str
    query_type: str
    intent_type: str
    ranking_value_used: Decimal
    tokens: tuple[str, ...]
    strong_tokens: tuple[str, ...]
    primary_anchor: str | None
    token_length_class: str
    family_key: str
    quantity_signature: str | None
    material_signature: str | None


def _import_semantic_stack() -> tuple[Any, Any]:
    try:
        from sentence_transformers import SentenceTransformer, util
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Semantic clustering dependencies are not installed. "
            "Rebuild the api environment with updated requirements to use this experiment."
        ) from exc
    return SentenceTransformer, util


def _load_model(model_name: str) -> Any:
    SentenceTransformer, _ = _import_semantic_stack()
    model = _MODEL_CACHE.get(model_name)
    if model is None:
        model = SentenceTransformer(model_name)
        _MODEL_CACHE[model_name] = model
    return model


def _normalize_token(token: str) -> str:
    return _TOKEN_RE.sub("", str(token or "").strip().lower())


def _tokenize(text_value: str) -> tuple[str, ...]:
    return tuple(token for token in (_normalize_token(part) for part in str(text_value or "").split()) if token)


def _token_length_class(token_count: int) -> str:
    if token_count <= 1:
        return "single_token"
    if token_count <= 3:
        return "short_multi"
    return "long_tail"


def _quantity_signature(tokens: tuple[str, ...]) -> str | None:
    values = [token for token in tokens if token.isdigit() or token in _QTY_MARKERS]
    return "|".join(sorted(set(values))) if values else None


def _material_signature(tokens: tuple[str, ...]) -> str | None:
    values = [token for token in tokens if token in _MATERIAL_MARKERS]
    return "|".join(sorted(set(values))) if values else None


def _family_key(tokens: tuple[str, ...]) -> str:
    families: list[str] = []
    if any(token in _SET_MARKERS for token in tokens):
        families.append("set_like")
    if any(token.isdigit() or token in _QTY_MARKERS for token in tokens):
        families.append("qty_like")
    if any(token in _DECOR_MARKERS for token in tokens):
        families.append("decor_like")
    if any(token in _USE_CASE_MARKERS for token in tokens):
        families.append("use_case_like")
    if any(token in _MATERIAL_MARKERS for token in tokens):
        families.append("material_like")
    return "|".join(sorted(families)) if families else "generic_like"


def _strong_tokens(tokens: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(token for token in tokens if token not in _STOPWORDS and token not in _CATEGORY_TOKENS)


def _primary_anchor(strong_tokens: tuple[str, ...]) -> str | None:
    if not strong_tokens:
        return None
    for token in strong_tokens:
        if token not in _GENERIC_FAMILY_MARKERS:
            return token
    return strong_tokens[0]


def _prepare_queries(rows: list[AnnotatedCanonicalQueryRow]) -> list[_PreparedQuery]:
    prepared: list[_PreparedQuery] = []
    for row in rows:
        tokens = _tokenize(row.normalized_query_text)
        strong_tokens = _strong_tokens(tokens)
        prepared.append(
            _PreparedQuery(
                row=row,
                normalized_query_text=row.normalized_query_text,
                display_query=row.display_query or row.normalized_query_text,
                query_type=row.query_type,
                intent_type=row.intent_type,
                ranking_value_used=Decimal(str(row.ranking_value_used)),
                tokens=tokens,
                strong_tokens=strong_tokens,
                primary_anchor=_primary_anchor(strong_tokens),
                token_length_class=_token_length_class(len(tokens)),
                family_key=_family_key(tokens),
                quantity_signature=_quantity_signature(tokens),
                material_signature=_material_signature(tokens),
            )
        )
    return sorted(prepared, key=lambda item: (-item.ranking_value_used, item.normalized_query_text))


def _cluster_key(prefix: str, normalized_query_texts: list[str]) -> str:
    digest = hashlib.sha1("||".join(sorted(normalized_query_texts)).encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def _cluster_size_distribution(clusters: list[SemanticClusterPreview]) -> dict[str, int]:
    counts = {label: 0 for label, _ in _CLUSTER_SIZE_BUCKETS}
    for cluster in clusters:
        for label, predicate in _CLUSTER_SIZE_BUCKETS:
            if predicate(cluster.query_count):
                counts[label] += 1
                break
    return counts


def _segment_key(query: _PreparedQuery, strategy: str) -> str:
    if strategy == "bucket_gate":
        return f"bucket:{query.query_type}"
    if strategy == "token_length_gate":
        return f"bucket:{query.query_type}|len:{query.token_length_class}"
    if strategy == "family_gate":
        return f"bucket:{query.query_type}|family:{query.family_key}"
    if strategy == "anchor_family_gate":
        return (
            f"bucket:{query.query_type}|anchor:{query.primary_anchor or '__generic__'}"
            f"|family:{query.family_key}|len:{query.token_length_class}"
        )
    raise ValueError(
        f"Unknown semantic gating strategy '{strategy}'. "
        f"Available: {', '.join(sorted(AVAILABLE_GATING_STRATEGIES))}"
    )


def _guard_key(query: _PreparedQuery) -> tuple[str, str, str, str, str]:
    return (
        query.primary_anchor or ("__single__" if query.token_length_class == "single_token" else "__generic__"),
        query.material_signature or "__no_material__",
        query.quantity_signature or "__no_qty__",
        query.family_key,
        query.token_length_class,
    )


def _encode_queries(prepared_queries: list[_PreparedQuery], model_name: str) -> Any:
    if not prepared_queries:
        return None
    model = _load_model(model_name)
    return model.encode(
        [item.normalized_query_text for item in prepared_queries],
        batch_size=128,
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_tensor=True,
    )


def _semantic_member_preview(item: _PreparedQuery, assignment_reason_code: str) -> SemanticClusterMemberPreview:
    return SemanticClusterMemberPreview(
        normalized_query_text=item.normalized_query_text,
        display_query=item.display_query,
        query_type=item.query_type,
        intent_type=item.intent_type,
        ranking_value_used=_decimal_to_string(item.ranking_value_used),
        assignment_reason_code=assignment_reason_code,
    )


def _cluster_preview(
    *,
    project_id: int,
    category_id: int,
    kind: str,
    members: list[_PreparedQuery],
    assignment_reason_code: str,
) -> SemanticClusterPreview:
    ordered = sorted(members, key=lambda item: (-item.ranking_value_used, item.normalized_query_text))
    representative = ordered[0]
    counts = Counter(item.query_type for item in ordered)
    return SemanticClusterPreview(
        project_id=project_id,
        category_id=category_id,
        cluster_key=_cluster_key("sqc:v3", [item.normalized_query_text for item in ordered]),
        cluster_label_candidate=representative.display_query or representative.normalized_query_text,
        top_query_text=representative.normalized_query_text,
        query_count=len(ordered),
        head_query_count=int(counts.get("head", 0)),
        mid_query_count=int(counts.get("mid", 0)),
        tail_query_count=int(counts.get("tail", 0)),
        semantic_kind=kind,
        member_samples=[item.normalized_query_text for item in ordered[:5]],
        members=[_semantic_member_preview(item, assignment_reason_code) for item in ordered],
    )


def _light_cluster_preview(cluster: SemanticClusterPreview) -> SemanticClusterPreview:
    return SemanticClusterPreview(**{**cluster.__dict__, "members": []})


def _noise_preview(item: _PreparedQuery) -> SemanticNoiseQueryPreview:
    return SemanticNoiseQueryPreview(
        normalized_query_text=item.normalized_query_text,
        display_query=item.display_query,
        ranking_value_used=_decimal_to_string(item.ranking_value_used),
        query_type=item.query_type,
        intent_type=item.intent_type,
    )


def _average_cluster_size(clusters: list[SemanticClusterPreview]) -> str:
    if not clusters:
        return "0"
    return _decimal_to_string(Decimal(sum(item.query_count for item in clusters)) / Decimal(len(clusters)))


def _segment_previews(segments: dict[str, list[int]]) -> list[SemanticSegmentPreview]:
    items = [SemanticSegmentPreview(segment_key=key, query_count=len(indices)) for key, indices in segments.items()]
    return sorted(items, key=lambda item: (-item.query_count, item.segment_key))


def _split_indices_by_guard(indices: list[int], prepared_queries: list[_PreparedQuery]) -> list[list[int]]:
    groups: dict[tuple[str, str, str, str, str], list[int]] = defaultdict(list)
    for index in indices:
        groups[_guard_key(prepared_queries[index])].append(index)
    return [sorted(group) for group in groups.values()]


def _cluster_segment(
    *,
    project_id: int,
    category_id: int,
    prepared_queries: list[_PreparedQuery],
    embeddings: Any,
    segment_indices: list[int],
    similarity_threshold: Decimal,
    min_community_size: int,
    semantic_kind: str,
    apply_safety_gates: bool,
) -> tuple[list[SemanticClusterPreview], list[SemanticNoiseQueryPreview]]:
    if not segment_indices:
        return [], []

    _, util = _import_semantic_stack()
    subset_embeddings = embeddings[segment_indices]
    communities = util.community_detection(
        subset_embeddings,
        threshold=float(similarity_threshold),
        min_community_size=max(2, int(min_community_size)),
        batch_size=DEFAULT_COMMUNITY_BATCH_SIZE,
        show_progress_bar=False,
    )

    assigned: set[int] = set()
    clusters: list[SemanticClusterPreview] = []
    for community in communities:
        global_indices = sorted(
            {
                segment_indices[int(local_index)]
                for local_index in community
                if segment_indices[int(local_index)] not in assigned
            }
        )
        if len(global_indices) < max(2, int(min_community_size)):
            continue

        candidate_groups = _split_indices_by_guard(global_indices, prepared_queries) if apply_safety_gates else [global_indices]
        for group in candidate_groups:
            if len(group) < max(2, int(min_community_size)):
                continue
            assigned.update(group)
            clusters.append(
                _cluster_preview(
                    project_id=project_id,
                    category_id=category_id,
                    kind=semantic_kind,
                    members=[prepared_queries[index] for index in group],
                    assignment_reason_code=(
                        "semantic_segmented_community_with_guards"
                        if apply_safety_gates
                        else "semantic_raw_community_detection"
                    ),
                )
            )

    noise_queries: list[SemanticNoiseQueryPreview] = []
    for index in segment_indices:
        if index in assigned:
            continue
        clusters.append(
            _cluster_preview(
                project_id=project_id,
                category_id=category_id,
                kind="singleton_noise",
                members=[prepared_queries[index]],
                assignment_reason_code="semantic_singleton_noise_fallback",
            )
        )
        noise_queries.append(_noise_preview(prepared_queries[index]))
    return clusters, noise_queries


def _build_semantic_variant(
    *,
    project_id: int,
    category_id: int,
    model_name: str,
    prepared_queries: list[_PreparedQuery],
    embeddings: Any,
    similarity_threshold: Decimal,
    min_community_size: int,
    strategy: str,
    strategy_label: str,
    top_limit: int,
    samples_limit: int,
    apply_safety_gates: bool,
) -> tuple[SemanticClusteringDiagnostics, list[SemanticClusterPreview]]:
    if strategy == "raw_baseline":
        segments = {"all_queries": list(range(len(prepared_queries)))}
        semantic_kind = "semantic_raw_cluster"
    else:
        segments: dict[str, list[int]] = defaultdict(list)
        for index, query in enumerate(prepared_queries):
            segments[_segment_key(query, strategy)].append(index)
        semantic_kind = "semantic_gated_cluster"

    all_clusters: list[SemanticClusterPreview] = []
    all_noise_queries: list[SemanticNoiseQueryPreview] = []
    for segment_key in sorted(segments):
        clusters, noise_queries = _cluster_segment(
            project_id=project_id,
            category_id=category_id,
            prepared_queries=prepared_queries,
            embeddings=embeddings,
            segment_indices=segments[segment_key],
            similarity_threshold=similarity_threshold,
            min_community_size=min_community_size,
            semantic_kind=semantic_kind,
            apply_safety_gates=apply_safety_gates,
        )
        all_clusters.extend(clusters)
        all_noise_queries.extend(noise_queries)

    ordered_clusters = sorted(
        all_clusters,
        key=lambda item: (-item.query_count, item.cluster_label_candidate, item.cluster_key),
    )
    ordered_noise = sorted(
        all_noise_queries,
        key=lambda item: (-Decimal(str(item.ranking_value_used)), item.normalized_query_text),
    )
    counts_by_query_type = Counter(item.query_type for item in prepared_queries)

    diagnostics = SemanticClusteringDiagnostics(
        project_id=project_id,
        category_id=category_id,
        model_name=model_name,
        clustering_backend="sentence_transformers.community_detection",
        similarity_threshold=_decimal_to_string(similarity_threshold),
        min_community_size=int(min_community_size),
        gating_strategy=strategy,
        strategy_label=strategy_label,
        total_input_queries=len(prepared_queries),
        total_semantic_clusters=len(ordered_clusters),
        multi_member_cluster_count=sum(1 for cluster in ordered_clusters if cluster.query_count > 1),
        singleton_noise_count=len(ordered_noise),
        average_cluster_size=_average_cluster_size(ordered_clusters),
        biggest_cluster_size=max((cluster.query_count for cluster in ordered_clusters), default=0),
        segment_count=len(segments),
        largest_segment_size=max((len(indices) for indices in segments.values()), default=0),
        counts_by_query_type={key: int(value) for key, value in counts_by_query_type.items()},
        cluster_size_distribution=_cluster_size_distribution(ordered_clusters),
        top_segments=_segment_previews(segments)[:top_limit],
        top_semantic_clusters=[_light_cluster_preview(cluster) for cluster in ordered_clusters[:top_limit]],
        sample_noise_queries=ordered_noise[:samples_limit],
    )
    return diagnostics, ordered_clusters


def _load_or_build_lexical_clusters(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    bucket: str | None,
    top_limit: int,
    samples_limit: int,
) -> list[PersistedQueryClusterView]:
    persisted_clusters = get_query_clusters(
        session,
        project_id=project_id,
        category_id=category_id,
        bucket=bucket,
    )
    if persisted_clusters:
        return persisted_clusters
    return run_query_clustering(
        session,
        project_id=project_id,
        category_id=category_id,
        bucket=bucket,
        top_limit=top_limit,
        samples_limit=samples_limit,
        persist=False,
    ).clusters


def _as_semantic_cluster_preview_from_lexical(cluster: PersistedQueryClusterView) -> SemanticClusterPreview:
    return SemanticClusterPreview(
        project_id=cluster.project_id,
        category_id=cluster.category_id,
        cluster_key=cluster.cluster_key,
        cluster_label_candidate=cluster.cluster_label_candidate,
        top_query_text=cluster.top_query_text,
        query_count=cluster.query_count,
        head_query_count=cluster.head_query_count,
        mid_query_count=cluster.mid_query_count,
        tail_query_count=cluster.tail_query_count,
        semantic_kind="lexical_current",
        member_samples=[member.normalized_query_text for member in cluster.members[:5]],
        members=[],
    )


def _group_preview(
    *,
    cluster_key: str,
    cluster_label_candidate: str,
    query_count: int,
    sample_queries: list[str],
) -> ComparisonGroupPreview:
    return ComparisonGroupPreview(
        cluster_key=cluster_key,
        cluster_label_candidate=cluster_label_candidate,
        query_count=query_count,
        sample_queries=sample_queries[:5],
    )


def _build_comparison(
    *,
    project_id: int,
    category_id: int,
    prepared_queries: list[_PreparedQuery],
    lexical_clusters: list[PersistedQueryClusterView],
    semantic_clusters: list[SemanticClusterPreview],
    top_limit: int,
    samples_limit: int,
) -> SemanticVsLexicalComparisonDiagnostics:
    lexical_by_query: dict[str, PersistedQueryClusterView] = {}
    for cluster in lexical_clusters:
        for member in cluster.members:
            lexical_by_query[member.normalized_query_text] = cluster

    semantic_by_query: dict[str, SemanticClusterPreview] = {}
    for cluster in semantic_clusters:
        for member in cluster.members:
            semantic_by_query[member.normalized_query_text] = cluster

    overbroad_cases: list[SemanticOverbroadCase] = []
    grouped_fragment_cases: list[SemanticGroupingCase] = []
    for cluster in semantic_clusters:
        if cluster.query_count <= 1 or not cluster.members:
            continue

        lexical_counts: Counter[str] = Counter()
        lexical_groups: dict[str, PersistedQueryClusterView] = {}
        sample_queries_by_group: dict[str, list[str]] = defaultdict(list)
        for member in cluster.members:
            lexical_cluster = lexical_by_query.get(member.normalized_query_text)
            if lexical_cluster is None:
                continue
            lexical_counts[lexical_cluster.cluster_key] += 1
            lexical_groups[lexical_cluster.cluster_key] = lexical_cluster
            if len(sample_queries_by_group[lexical_cluster.cluster_key]) < 5:
                sample_queries_by_group[lexical_cluster.cluster_key].append(member.normalized_query_text)

        if len(lexical_counts) <= 1:
            continue

        dominant_count = max(lexical_counts.values())
        dominant_share = _decimal_to_string(Decimal(dominant_count) / Decimal(cluster.query_count))
        group_previews = sorted(
            [
                _group_preview(
                    cluster_key=group_key,
                    cluster_label_candidate=lexical_groups[group_key].cluster_label_candidate,
                    query_count=count,
                    sample_queries=sample_queries_by_group[group_key],
                )
                for group_key, count in lexical_counts.items()
            ],
            key=lambda item: (-item.query_count, item.cluster_label_candidate, item.cluster_key),
        )
        overbroad_cases.append(
            SemanticOverbroadCase(
                semantic_cluster_key=cluster.cluster_key,
                semantic_cluster_label_candidate=cluster.cluster_label_candidate,
                semantic_query_count=cluster.query_count,
                lexical_group_count=len(lexical_counts),
                dominant_lexical_group_share=dominant_share,
                lexical_groups=group_previews[:5],
                sample_queries=cluster.member_samples[:5],
            )
        )
        if 2 <= len(lexical_counts) <= 8 and cluster.query_count <= 60 and dominant_count * 2 <= cluster.query_count * 3:
            grouped_fragment_cases.append(
                SemanticGroupingCase(
                    semantic_cluster_key=cluster.cluster_key,
                    semantic_cluster_label_candidate=cluster.cluster_label_candidate,
                    semantic_query_count=cluster.query_count,
                    lexical_group_count=len(lexical_counts),
                    lexical_groups=group_previews[:5],
                    sample_queries=cluster.member_samples[:5],
                )
            )

    ordered_lexical = sorted(
        (_as_semantic_cluster_preview_from_lexical(cluster) for cluster in lexical_clusters),
        key=lambda item: (-item.query_count, item.cluster_label_candidate, item.cluster_key),
    )
    top_query_assignments: list[QueryAssignmentComparison] = []
    for item in prepared_queries:
        lexical_cluster = lexical_by_query.get(item.normalized_query_text)
        semantic_cluster = semantic_by_query.get(item.normalized_query_text)
        if lexical_cluster is None or semantic_cluster is None:
            continue
        top_query_assignments.append(
            QueryAssignmentComparison(
                normalized_query_text=item.normalized_query_text,
                ranking_value_used=_decimal_to_string(item.ranking_value_used),
                query_type=item.query_type,
                lexical_cluster_label_candidate=lexical_cluster.cluster_label_candidate,
                lexical_cluster_query_count=lexical_cluster.query_count,
                semantic_cluster_label_candidate=semantic_cluster.cluster_label_candidate,
                semantic_cluster_query_count=semantic_cluster.query_count,
                semantic_kind=semantic_cluster.semantic_kind,
            )
        )
        if len(top_query_assignments) >= samples_limit:
            break

    return SemanticVsLexicalComparisonDiagnostics(
        project_id=project_id,
        category_id=category_id,
        total_input_queries=len(prepared_queries),
        total_lexical_clusters=len(lexical_clusters),
        total_semantic_clusters=len(semantic_clusters),
        lexical_singleton_count=sum(1 for cluster in lexical_clusters if cluster.query_count == 1),
        semantic_singleton_noise_count=sum(1 for cluster in semantic_clusters if cluster.query_count == 1),
        top_lexical_clusters=ordered_lexical[:top_limit],
        top_semantic_clusters=[_light_cluster_preview(cluster) for cluster in semantic_clusters[:top_limit]],
        semantic_overbroad_cases=sorted(
            overbroad_cases,
            key=lambda item: (-item.semantic_query_count, -item.lexical_group_count, item.semantic_cluster_label_candidate),
        )[:top_limit],
        semantic_grouped_fragment_cases=sorted(
            grouped_fragment_cases,
            key=lambda item: (-item.lexical_group_count, -item.semantic_query_count, item.semantic_cluster_label_candidate),
        )[:top_limit],
        top_query_assignments=top_query_assignments,
    )


def _lexical_summary(clusters: list[PersistedQueryClusterView]) -> LexicalClusteringSummary:
    previews = [_as_semantic_cluster_preview_from_lexical(cluster) for cluster in clusters]
    return LexicalClusteringSummary(
        total_clusters=len(clusters),
        singleton_cluster_count=sum(1 for cluster in clusters if cluster.query_count == 1),
        average_cluster_size=_average_cluster_size(previews),
        biggest_cluster_size=max((cluster.query_count for cluster in clusters), default=0),
        cluster_size_distribution=_cluster_size_distribution(previews),
    )


def run_semantic_clustering_experiment(
    session: Session,
    *,
    project_id: int,
    category_id: int,
    bucket: str | None = None,
    model_name: str = DEFAULT_SEMANTIC_MODEL_NAME,
    similarity_threshold: Decimal = DEFAULT_SIMILARITY_THRESHOLD,
    min_community_size: int = DEFAULT_MIN_COMMUNITY_SIZE,
    strategy: str = DEFAULT_GATING_STRATEGY,
    top_limit: int = 20,
    samples_limit: int = 20,
) -> SemanticClusteringExperimentResult:
    if strategy not in AVAILABLE_GATING_STRATEGIES:
        raise ValueError(
            f"Unknown semantic gating strategy '{strategy}'. "
            f"Available: {', '.join(sorted(AVAILABLE_GATING_STRATEGIES))}"
        )

    clean_rows = get_clean_query_set(
        session,
        project_id=project_id,
        category_id=category_id,
        bucket=bucket,
    )
    prepared_queries = _prepare_queries(clean_rows)
    embeddings = _encode_queries(prepared_queries, model_name)

    raw_semantic, raw_clusters = _build_semantic_variant(
        project_id=project_id,
        category_id=category_id,
        model_name=model_name,
        prepared_queries=prepared_queries,
        embeddings=embeddings,
        similarity_threshold=similarity_threshold,
        min_community_size=min_community_size,
        strategy="raw_baseline",
        strategy_label="Raw Baseline",
        top_limit=top_limit,
        samples_limit=samples_limit,
        apply_safety_gates=False,
    )
    gated_semantic, gated_clusters = _build_semantic_variant(
        project_id=project_id,
        category_id=category_id,
        model_name=model_name,
        prepared_queries=prepared_queries,
        embeddings=embeddings,
        similarity_threshold=similarity_threshold,
        min_community_size=min_community_size,
        strategy=strategy,
        strategy_label=AVAILABLE_GATING_STRATEGIES[strategy],
        top_limit=top_limit,
        samples_limit=samples_limit,
        apply_safety_gates=True,
    )

    lexical_clusters = _load_or_build_lexical_clusters(
        session,
        project_id=project_id,
        category_id=category_id,
        bucket=bucket,
        top_limit=top_limit,
        samples_limit=samples_limit,
    )
    raw_comparison = _build_comparison(
        project_id=project_id,
        category_id=category_id,
        prepared_queries=prepared_queries,
        lexical_clusters=lexical_clusters,
        semantic_clusters=raw_clusters,
        top_limit=top_limit,
        samples_limit=samples_limit,
    )
    gated_comparison = _build_comparison(
        project_id=project_id,
        category_id=category_id,
        prepared_queries=prepared_queries,
        lexical_clusters=lexical_clusters,
        semantic_clusters=gated_clusters,
        top_limit=top_limit,
        samples_limit=samples_limit,
    )

    return SemanticClusteringExperimentResult(
        project_id=project_id,
        category_id=category_id,
        bucket=bucket,
        model_name=model_name,
        strategy=strategy,
        lexical_summary=_lexical_summary(lexical_clusters),
        raw_semantic=raw_semantic,
        raw_comparison=raw_comparison,
        gated_semantic=gated_semantic,
        gated_comparison=gated_comparison,
        improvement_summary=SemanticImprovementSummary(
            raw_biggest_cluster_size=raw_semantic.biggest_cluster_size,
            gated_biggest_cluster_size=gated_semantic.biggest_cluster_size,
            biggest_cluster_reduction=max(raw_semantic.biggest_cluster_size - gated_semantic.biggest_cluster_size, 0),
            raw_total_clusters=raw_semantic.total_semantic_clusters,
            gated_total_clusters=gated_semantic.total_semantic_clusters,
            raw_singleton_noise_count=raw_semantic.singleton_noise_count,
            gated_singleton_noise_count=gated_semantic.singleton_noise_count,
        ),
    )
