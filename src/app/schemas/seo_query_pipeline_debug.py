"""Schemas for internal SEO query pipeline debug endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SeoQueryPipelineDiagnosticsSummary(BaseModel):
    total_queries: int
    keep_count: int
    drop_count: int
    review_count: int
    total_clusters: int
    singleton_clusters: int


class SeoQueryPipelinePagination(BaseModel):
    page: int
    page_size: int
    total_count: int
    total_pages: int


class SeoQueryPipelineQueryItem(BaseModel):
    normalized_query_text: str
    ranking_value_used: str
    bucket: Literal["head", "mid", "tail"]
    pruning_status: Literal["keep", "drop", "review"]
    intent_type: str
    cluster_key: str | None = None
    cluster_label_candidate: str | None = None


class SeoQueryPipelineClusterMemberItem(BaseModel):
    normalized_query_text: str
    bucket: Literal["head", "mid", "tail"]
    ranking_value_used: str
    intent_type: str
    membership_reason_code: str


class SeoQueryPipelineClusterItem(BaseModel):
    cluster_key: str
    cluster_label_candidate: str
    query_count: int
    head_query_count: int
    mid_query_count: int
    tail_query_count: int
    members: list[SeoQueryPipelineClusterMemberItem] = Field(default_factory=list)


class SeoQueryPipelineHybridItem(BaseModel):
    normalized_query_text: str
    ranking_value_used: str
    bucket: Literal["head", "mid", "tail"]
    cluster_key: str | None = None
    is_anchor: bool = False
    cluster_label_candidate: str | None = None
    cluster_query_count: int | None = None
    provenance: Literal["individual", "cluster", "rejected", "fallback"]
    source_anchor_query: str | None = None
    intent_type: str
    inheritance_reason_code: str


class SeoQueryPipelineHybridClusterMemberItem(BaseModel):
    normalized_query_text: str
    bucket: Literal["head", "mid", "tail"]
    is_anchor: bool = False
    provenance: Literal["individual", "cluster", "rejected", "fallback"]
    source_anchor_query: str | None = None
    intent_type: str
    inheritance_reason_code: str


class SeoQueryPipelineHybridClusterDetailItem(BaseModel):
    cluster_key: str
    cluster_label_candidate: str
    query_count: int
    anchor_query: str | None = None
    members: list[SeoQueryPipelineHybridClusterMemberItem] = Field(default_factory=list)


class SeoQueryPipelineHybridClusterIssueItem(BaseModel):
    cluster_key: str
    cluster_label_candidate: str
    query_count: int
    rejected_count: int
    reject_rate: str
    anchor_query: str | None = None
    issue_reason: str | None = None


class SeoQueryPipelineHybridDiagnostics(BaseModel):
    total_queries_processed: int
    individual_count: int
    cluster_derived_count: int
    rejected_count: int
    fallback_count: int
    anchor_count: int = 0
    inherited_head_member_count: int = 0
    rejected_head_member_count: int = 0
    counts_by_provenance: dict[str, int] = Field(default_factory=dict)
    counts_by_inheritance_reason_code: dict[str, int] = Field(default_factory=dict)
    sample_inherited_queries: list[SeoQueryPipelineHybridItem] = Field(default_factory=list)
    sample_rejected_queries: list[SeoQueryPipelineHybridItem] = Field(default_factory=list)
    sample_inherited_head_member_queries: list[SeoQueryPipelineHybridItem] = Field(default_factory=list)
    sample_rejected_head_member_queries: list[SeoQueryPipelineHybridItem] = Field(default_factory=list)
    top_inherited_relaxed_cases: list[SeoQueryPipelineHybridItem] = Field(default_factory=list)
    top_still_rejected_similar_cases: list[SeoQueryPipelineHybridItem] = Field(default_factory=list)
    clusters_without_anchor: list[SeoQueryPipelineHybridClusterIssueItem] = Field(default_factory=list)
    clusters_with_high_reject_rate: list[SeoQueryPipelineHybridClusterIssueItem] = Field(default_factory=list)
    annotations_upserted: int = 0
    versions_created: int = 0


class SeoQueryProfileMarkerItem(BaseModel):
    value: str
    normalized_value: str
    family: str | None = None
    support_query_count: int
    support_share: float
    weighted_support: float
    evidence_queries: list[str] = Field(default_factory=list)


class SeoQueryProfileMarkerDecisionItem(BaseModel):
    slot: str
    value: str
    normalized_value: str
    family: str | None = None
    support_query_count: int
    support_ratio: float
    evidence_queries: list[str] = Field(default_factory=list)
    source_kinds: list[str] = Field(default_factory=list)
    selected: bool
    reason: str


class SeoQueryPipelineProfileItem(BaseModel):
    cluster_key: str
    profile_label_candidate: str
    profile_strength: Literal["strong", "medium", "weak", "empty"]
    profile_confidence: float
    source_cluster_key: str
    source_anchor_query: str | None = None
    source_query_examples: list[str] = Field(default_factory=list)
    query_count: int
    evidence_query_count: int
    weighted_signal: float = 0.0
    product_type_markers: list[SeoQueryProfileMarkerItem] = Field(default_factory=list)
    use_case_markers: list[SeoQueryProfileMarkerItem] = Field(default_factory=list)
    attribute_markers: list[SeoQueryProfileMarkerItem] = Field(default_factory=list)
    language_markers: list[SeoQueryProfileMarkerItem] = Field(default_factory=list)
    marker_decisions: list[SeoQueryProfileMarkerDecisionItem] = Field(default_factory=list)
    conflicting_attribute_families: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    confidence_factors: dict[str, Any] = Field(default_factory=dict)


class SeoQueryPipelineProfilesDiagnostics(BaseModel):
    total_profiles_built: int
    strong_profiles_count: int
    medium_profiles_count: int
    weak_profiles_count: int
    empty_profiles_count: int
    profiles_with_conflicts_count: int = 0
    profiles_with_low_confidence_count: int = 0
    counts_by_marker_type: dict[str, int] = Field(default_factory=dict)
    counts_by_attribute_family: dict[str, int] = Field(default_factory=dict)
    sample_profiles: list[SeoQueryPipelineProfileItem] = Field(default_factory=list)
    top_profiles_by_signal: list[SeoQueryPipelineProfileItem] = Field(default_factory=list)
    profiles_with_conflicting_markers: list[SeoQueryPipelineProfileItem] = Field(default_factory=list)
    profiles_with_low_confidence: list[SeoQueryPipelineProfileItem] = Field(default_factory=list)


class SeoQueryPipelineScoringPrepMarkerItem(BaseModel):
    value: str
    normalized_value: str
    family: str | None = None
    status: Literal["matched", "missed", "conflicting", "unknown"]
    fields_checked: list[str] = Field(default_factory=list)
    matched_fields: list[str] = Field(default_factory=list)
    conflicting_with: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    reason: str = ""


class SeoQueryPipelineScoringPrepProductTypeMatchItem(BaseModel):
    status: Literal["matched", "not_matched", "unknown"]
    evidence: list[str] = Field(default_factory=list)
    reason: str = ""
    marker_evaluations: list[SeoQueryPipelineScoringPrepMarkerItem] = Field(default_factory=list)


class SeoQueryPipelineScoringPrepUseCaseMatchItem(BaseModel):
    matched_markers: list[SeoQueryPipelineScoringPrepMarkerItem] = Field(default_factory=list)
    missed_markers: list[SeoQueryPipelineScoringPrepMarkerItem] = Field(default_factory=list)
    unknown_markers: list[SeoQueryPipelineScoringPrepMarkerItem] = Field(default_factory=list)
    reason: str = ""


class SeoQueryPipelineScoringPrepAttributeMatchItem(BaseModel):
    matched_markers: list[SeoQueryPipelineScoringPrepMarkerItem] = Field(default_factory=list)
    missed_markers: list[SeoQueryPipelineScoringPrepMarkerItem] = Field(default_factory=list)
    conflicting_markers: list[SeoQueryPipelineScoringPrepMarkerItem] = Field(default_factory=list)
    unknown_markers: list[SeoQueryPipelineScoringPrepMarkerItem] = Field(default_factory=list)
    reason: str = ""


class SeoQueryPipelineScoringPrepSkuEvidenceSummary(BaseModel):
    title_present: bool = False
    attributes_present: bool = False
    description_present: bool = False
    normalized_evidence_fields_used: list[str] = Field(default_factory=list)


class SeoQueryPipelineScoringPrepFlags(BaseModel):
    weak_profile: bool = False
    empty_profile: bool = False
    missing_product_type: bool = False
    conflicting_profile_markers: bool = False
    insufficient_sku_data: bool = False


class SeoQueryPipelineScoringPrepItem(BaseModel):
    cluster_key: str
    profile_label_candidate: str
    profile_strength: Literal["strong", "medium", "weak", "empty"]
    profile_confidence: float
    product_type_match: SeoQueryPipelineScoringPrepProductTypeMatchItem
    use_case_match: SeoQueryPipelineScoringPrepUseCaseMatchItem
    attribute_match: SeoQueryPipelineScoringPrepAttributeMatchItem
    sku_evidence_summary: SeoQueryPipelineScoringPrepSkuEvidenceSummary
    preparation_flags: SeoQueryPipelineScoringPrepFlags
    readiness_for_scoring: Literal["ready", "partial", "poor"]


class SeoQueryPipelineScoringPrepDiagnostics(BaseModel):
    project_id: int
    category_id: int
    nm_id: int
    total_cluster_comparisons: int = 0
    ready_count: int = 0
    partial_count: int = 0
    poor_count: int = 0
    product_type_matched_rate: float = 0.0
    use_case_matched_rate: float = 0.0
    attribute_matched_rate: float = 0.0
    insufficient_sku_data_count: int = 0
    weak_profile_count: int = 0
    missing_product_type_count: int = 0
    sample_preparations: list[SeoQueryPipelineScoringPrepItem] = Field(default_factory=list)


class SeoQueryPipelineActualScoringModifiers(BaseModel):
    profile_strength: Literal["strong", "medium", "weak", "empty"]
    profile_strength_multiplier: float
    readiness_for_scoring: Literal["ready", "partial", "poor"]
    readiness_multiplier: float
    combined_multiplier: float


class SeoQueryPipelineActualScoringPenalty(BaseModel):
    name: str
    value: float
    reason: str


class SeoQueryPipelineActualScoringItem(BaseModel):
    cluster_key: str
    profile_label_candidate: str
    final_score: float
    base_score: float
    weighted_score: float
    product_type_score: float
    use_case_score: float
    attribute_score: float
    modifiers: SeoQueryPipelineActualScoringModifiers
    penalties: list[SeoQueryPipelineActualScoringPenalty] = Field(default_factory=list)
    penalties_total: float = 0.0
    readiness_for_scoring: Literal["ready", "partial", "poor"]
    preparation_flags: SeoQueryPipelineScoringPrepFlags
    ranking_eligible: bool = False
    generation_eligible: bool = False
    generation_guardrail_reason: str | None = None
    final_reason: str = ""


class SeoQueryPipelineActualScoringDiagnostics(BaseModel):
    project_id: int
    category_id: int
    nm_id: int
    total_clusters_scored: int = 0
    avg_score: float = 0.0
    top_score: float = 0.0
    bottom_score: float = 0.0
    positive_score_count: int = 0
    neutral_score_count: int = 0
    negative_score_count: int = 0
    positive_score_share: float = 0.0
    neutral_score_share: float = 0.0
    negative_score_share: float = 0.0
    avg_product_type_score: float = 0.0
    avg_use_case_score: float = 0.0
    avg_attribute_score: float = 0.0
    top_clusters: list[SeoQueryPipelineActualScoringItem] = Field(default_factory=list)
    bottom_clusters: list[SeoQueryPipelineActualScoringItem] = Field(default_factory=list)


class SeoQueryPipelineDebugResponse(BaseModel):
    project_id: int
    category_id: int
    diagnostics: SeoQueryPipelineDiagnosticsSummary
    audit: dict[str, Any] = Field(default_factory=dict)
    compare: dict[str, Any] = Field(default_factory=dict)
    hybrid_diagnostics: SeoQueryPipelineHybridDiagnostics = Field(
        default_factory=lambda: SeoQueryPipelineHybridDiagnostics(
            total_queries_processed=0,
            individual_count=0,
            cluster_derived_count=0,
            rejected_count=0,
            fallback_count=0,
        )
    )
    profiles_diagnostics: SeoQueryPipelineProfilesDiagnostics = Field(
        default_factory=lambda: SeoQueryPipelineProfilesDiagnostics(
            total_profiles_built=0,
            strong_profiles_count=0,
            medium_profiles_count=0,
            weak_profiles_count=0,
            empty_profiles_count=0,
        )
    )
    scoring_prep_diagnostics: SeoQueryPipelineScoringPrepDiagnostics = Field(
        default_factory=lambda: SeoQueryPipelineScoringPrepDiagnostics(
            project_id=0,
            category_id=0,
            nm_id=0,
        )
    )
    actual_scoring_diagnostics: SeoQueryPipelineActualScoringDiagnostics = Field(
        default_factory=lambda: SeoQueryPipelineActualScoringDiagnostics(
            project_id=0,
            category_id=0,
            nm_id=0,
        )
    )
    queries_pagination: SeoQueryPipelinePagination
    clusters_pagination: SeoQueryPipelinePagination
    hybrid_pagination: SeoQueryPipelinePagination
    profiles_pagination: SeoQueryPipelinePagination
    scoring_prep_pagination: SeoQueryPipelinePagination
    actual_scoring_pagination: SeoQueryPipelinePagination
    queries: list[SeoQueryPipelineQueryItem] = Field(default_factory=list)
    clusters: list[SeoQueryPipelineClusterItem] = Field(default_factory=list)
    hybrid: list[SeoQueryPipelineHybridItem] = Field(default_factory=list)
    hybrid_cluster_details: list[SeoQueryPipelineHybridClusterDetailItem] = Field(default_factory=list)
    profiles: list[SeoQueryPipelineProfileItem] = Field(default_factory=list)
    scoring_preparations: list[SeoQueryPipelineScoringPrepItem] = Field(default_factory=list)
    actual_scores: list[SeoQueryPipelineActualScoringItem] = Field(default_factory=list)
