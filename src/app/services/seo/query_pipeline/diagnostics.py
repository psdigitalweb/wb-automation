"""Diagnostics structures for SEO query import, unification, pruning, and clustering."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def _serialize_value(value: Any) -> Any:
    """Convert dataclass payloads to JSON-serializable primitives."""

    if is_dataclass(value):
        return {key: _serialize_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize_value(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


@dataclass(frozen=True)
class SuspiciousRow:
    """A skipped or suspicious CSV row sample."""

    row_number: int
    reason: str
    raw_query: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TopNormalizedQuery:
    """Top normalized query entry used in diagnostics output."""

    normalized_query: str
    raw_row_count: int
    frequency_total: Decimal | None


@dataclass(frozen=True)
class ImportDiagnostics:
    """Readable summary for one local CSV import batch."""

    batch_id: int
    project_id: int
    category_id: int
    source_file_path: str
    query_column_resolved: str
    frequency_column_resolved: str | None
    raw_rows_imported: int
    raw_rows_skipped: int
    normalized_rows_created: int
    duplicate_groups_collapsed: int
    duplicate_raw_rows_detected: int
    suspicious_rows: list[SuspiciousRow] = field(default_factory=list)
    top_normalized_queries: list[TopNormalizedQuery] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable diagnostics payload."""

        return _serialize_value(self)


@dataclass(frozen=True)
class SourceInventoryItem:
    """Describes one persisted query source used by unified dataset assembly."""

    source_type: str
    source_table: str
    project_linkage: str
    category_linkage: str
    query_fields: list[str] = field(default_factory=list)
    demand_fields: list[str] = field(default_factory=list)
    source_identifiers: list[str] = field(default_factory=list)
    freshness_fields: list[str] = field(default_factory=list)
    record_count: int = 0
    latest_timestamp: str | None = None


@dataclass(frozen=True)
class CanonicalQueryPreview:
    """Compact canonical-query payload for diagnostics and script output."""

    project_id: int
    category_id: int
    normalized_query_text: str
    display_query: str
    source_presence_key: str
    source_presence: dict[str, bool] = field(default_factory=dict)
    source_count: int = 0
    source_record_count: int = 0
    frequency_total: str = "0"
    orders_total: str = "0"
    ranking_value_used: str = "0"
    bucket_basis: str = "none"
    head_tail_bucket: str = "tail"
    preparation_flag_reasons: list[str] = field(default_factory=list)
    display_variants: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UnifiedQueryDatasetDiagnostics:
    """Readable diagnostics for one project/category unified query dataset."""

    project_id: int
    category_id: int
    source_inventory: list[SourceInventoryItem] = field(default_factory=list)
    total_canonical_queries: int = 0
    total_source_linked_queries: int = 0
    queries_by_source_presence: dict[str, int] = field(default_factory=dict)
    queries_by_head_tail_bucket: dict[str, int] = field(default_factory=dict)
    top_queries: list[CanonicalQueryPreview] = field(default_factory=list)
    partial_coverage_samples: list[CanonicalQueryPreview] = field(default_factory=list)
    flagged_samples: list[CanonicalQueryPreview] = field(default_factory=list)
    conflict_samples: list[CanonicalQueryPreview] = field(default_factory=list)
    latest_csv_batch_id: int | None = None
    assembly_basis: str = "normalized_query_text"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable diagnostics payload."""

        return _serialize_value(self)


@dataclass(frozen=True)
class PrunedQueryPreview:
    """Compact query payload for pruning and annotation diagnostics."""

    project_id: int
    category_id: int
    normalized_query_text: str
    display_query: str
    normalized_query_id: int | None = None
    pruning_status: str = "review"
    pruning_reason_code: str = "migrated_pending"
    is_kept_for_pipeline: bool = False
    query_type: str = "tail"
    intent_type: str = "unknown"
    annotation_reason_code: str = "migrated_pending"
    source_count: int = 0
    source_presence_key: str = "csv_only"
    ranking_value_used: str = "0"
    bucket_basis: str = "none"
    head_tail_bucket: str = "tail"
    preparation_flag_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class QueryPruningDiagnostics:
    """Readable diagnostics for one pruning + basic annotation run."""

    project_id: int
    category_id: int
    total_canonical_queries_processed: int = 0
    keep_count: int = 0
    drop_count: int = 0
    review_count: int = 0
    counts_by_pruning_reason_code: dict[str, int] = field(default_factory=dict)
    counts_by_intent_type: dict[str, int] = field(default_factory=dict)
    kept_counts_by_query_type: dict[str, int] = field(default_factory=dict)
    top_kept_queries: list[PrunedQueryPreview] = field(default_factory=list)
    sample_dropped_queries: list[PrunedQueryPreview] = field(default_factory=list)
    sample_review_queries: list[PrunedQueryPreview] = field(default_factory=list)
    sample_unknown_queries: list[PrunedQueryPreview] = field(default_factory=list)
    stale_persisted_annotation_count: int = 0
    stale_persisted_annotation_samples: list[PrunedQueryPreview] = field(default_factory=list)
    removed_since_last_run_count: int = 0
    annotations_upserted: int = 0
    versions_created: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable diagnostics payload."""

        return _serialize_value(self)


@dataclass(frozen=True)
class QueryClusterMemberPreview:
    """Compact member payload for one persisted query cluster."""

    normalized_query_text: str
    display_query: str
    query_type: str
    ranking_value_used: str
    membership_reason_code: str


@dataclass(frozen=True)
class QueryClusterPreview:
    """Compact cluster payload for diagnostics and script output."""

    project_id: int
    category_id: int
    cluster_key: str
    cluster_label_candidate: str
    top_query_text: str
    query_count: int
    head_query_count: int
    mid_query_count: int
    tail_query_count: int
    members: list[QueryClusterMemberPreview] = field(default_factory=list)


@dataclass(frozen=True)
class QueryClusteringDiagnostics:
    """Readable diagnostics for one deterministic query clustering run."""

    project_id: int
    category_id: int
    total_input_queries: int = 0
    total_clusters_created: int = 0
    singleton_cluster_count: int = 0
    two_member_cluster_count: int = 0
    average_cluster_size: str = "0"
    biggest_cluster_size: int = 0
    counts_by_query_type: dict[str, int] = field(default_factory=dict)
    cluster_size_distribution: dict[str, int] = field(default_factory=dict)
    top_clusters: list[QueryClusterPreview] = field(default_factory=list)
    sample_clusters_with_members: list[QueryClusterPreview] = field(default_factory=list)
    sample_small_clusters: list[QueryClusterPreview] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable diagnostics payload."""

        return _serialize_value(self)


@dataclass(frozen=True)
class HybridQueryPreview:
    """Compact hybrid-annotation payload for diagnostics and debug output."""

    normalized_query_text: str
    display_query: str
    ranking_value_used: str
    bucket: str
    cluster_key: str | None
    provenance: str
    source_anchor_query: str | None = None
    intent_type: str = "unknown"
    inheritance_reason_code: str = "unknown"


@dataclass(frozen=True)
class HybridClusterPreview:
    """Cluster-level hybrid annotation summary for diagnostics output."""

    cluster_key: str
    cluster_label_candidate: str
    query_count: int
    rejected_count: int
    reject_rate: str
    anchor_query: str | None = None
    issue_reason: str | None = None


@dataclass(frozen=True)
class QueryHybridAnnotationDiagnostics:
    """Readable diagnostics for one deterministic hybrid annotation run."""

    project_id: int
    category_id: int
    total_queries_processed: int = 0
    individual_count: int = 0
    cluster_derived_count: int = 0
    rejected_count: int = 0
    fallback_count: int = 0
    anchor_count: int = 0
    inherited_head_member_count: int = 0
    rejected_head_member_count: int = 0
    counts_by_provenance: dict[str, int] = field(default_factory=dict)
    counts_by_inheritance_reason_code: dict[str, int] = field(default_factory=dict)
    sample_inherited_queries: list[HybridQueryPreview] = field(default_factory=list)
    sample_rejected_queries: list[HybridQueryPreview] = field(default_factory=list)
    sample_inherited_head_member_queries: list[HybridQueryPreview] = field(default_factory=list)
    sample_rejected_head_member_queries: list[HybridQueryPreview] = field(default_factory=list)
    top_inherited_relaxed_cases: list[HybridQueryPreview] = field(default_factory=list)
    top_still_rejected_similar_cases: list[HybridQueryPreview] = field(default_factory=list)
    clusters_without_anchor: list[HybridClusterPreview] = field(default_factory=list)
    clusters_with_high_reject_rate: list[HybridClusterPreview] = field(default_factory=list)
    annotations_upserted: int = 0
    versions_created: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable diagnostics payload."""

        return _serialize_value(self)


@dataclass(frozen=True)
class QueryProfileMarker:
    """Structured extracted marker with compact evidence summary."""

    value: str
    normalized_value: str
    family: str | None = None
    support_query_count: int = 0
    support_share: float = 0.0
    weighted_support: float = 0.0
    evidence_queries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class QueryProfileMarkerDecision:
    """Explainable selected/rejected marker decision for one extraction slot."""

    slot: str
    value: str
    normalized_value: str
    family: str | None = None
    support_query_count: int = 0
    support_ratio: float = 0.0
    evidence_queries: list[str] = field(default_factory=list)
    source_kinds: list[str] = field(default_factory=list)
    selected: bool = False
    reason: str = ""


@dataclass(frozen=True)
class ExtractedClusterProfile:
    """Deterministic cluster-level query profile projection."""

    cluster_key: str
    profile_label_candidate: str
    profile_strength: str
    profile_confidence: float
    source_cluster_key: str
    source_anchor_query: str | None = None
    source_query_examples: list[str] = field(default_factory=list)
    query_count: int = 0
    evidence_query_count: int = 0
    weighted_signal: float = 0.0
    product_type_markers: list[QueryProfileMarker] = field(default_factory=list)
    use_case_markers: list[QueryProfileMarker] = field(default_factory=list)
    attribute_markers: list[QueryProfileMarker] = field(default_factory=list)
    language_markers: list[QueryProfileMarker] = field(default_factory=list)
    marker_decisions: list[QueryProfileMarkerDecision] = field(default_factory=list)
    conflicting_attribute_families: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)
    confidence_factors: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)


@dataclass(frozen=True)
class QueryProfileExtractionDiagnostics:
    """Readable diagnostics for deterministic query-profile extraction."""

    project_id: int
    category_id: int
    total_profiles_built: int = 0
    strong_profiles_count: int = 0
    medium_profiles_count: int = 0
    weak_profiles_count: int = 0
    empty_profiles_count: int = 0
    profiles_with_conflicts_count: int = 0
    profiles_with_low_confidence_count: int = 0
    counts_by_marker_type: dict[str, int] = field(default_factory=dict)
    counts_by_attribute_family: dict[str, int] = field(default_factory=dict)
    sample_profiles: list[ExtractedClusterProfile] = field(default_factory=list)
    top_profiles_by_signal: list[ExtractedClusterProfile] = field(default_factory=list)
    profiles_with_conflicting_markers: list[ExtractedClusterProfile] = field(default_factory=list)
    profiles_with_low_confidence: list[ExtractedClusterProfile] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _serialize_value(self)
