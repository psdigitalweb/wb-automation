"""SQLAlchemy declarative models for core and SEO foundation tables."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Table, Text, UniqueConstraint
from sqlalchemy.sql import func

from .db import Base


CATEGORY_SCOPE_COMMENT = (
    "WB category scope for SEO pipeline (Wildberries subject_id/category scope), "
    "not a foreign key to internal_categories.id."
)


# The app still manages `projects` mostly through raw SQL helpers, but SEO models
# reference `projects.id` via ORM foreign keys. Register a minimal table in
# SQLAlchemy metadata so those FKs resolve at runtime.
if "projects" not in Base.metadata.tables:
    Table("projects", Base.metadata, Column("id", Integer, primary_key=True))


class TimestampMixin:
    """Shared timestamps for SEO models."""

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class SeoProjectCategoryScopedMixin:
    """Adds project_id plus WB category scope, never internal_categories.id."""

    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(Integer, nullable=False, index=True, comment=CATEGORY_SCOPE_COMMENT)


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    nm_id = Column(Integer, unique=True, index=True, nullable=False)
    vendor_code = Column(String(64), index=True)
    category = Column(String(128))


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"

    id = Column(Integer, primary_key=True)
    nm_id = Column(Integer, index=True, nullable=False)
    wb_price = Column(Numeric(12, 2))
    wb_discount = Column(Numeric(5, 2))
    spp = Column(Numeric(5, 2))
    customer_price = Column(Numeric(12, 2))
    rrc = Column(Numeric(12, 2))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class SeoQueryBatch(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Batch metadata for one local CSV import."""

    __tablename__ = "seo_query_batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(String(32), nullable=False, server_default="csv")
    source_path = Column(Text, nullable=True)
    original_filename = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, server_default="pending")
    row_count = Column(Integer, nullable=False, server_default="0")
    normalized_row_count = Column(Integer, nullable=False, server_default="0")
    deduplicated_row_count = Column(Integer, nullable=False, server_default="0")
    meta = Column(JSON, nullable=False, default=dict)


class SeoQueryRaw(SeoProjectCategoryScopedMixin, Base):
    """Raw CSV rows persisted as imported."""

    __tablename__ = "seo_queries_raw"
    __table_args__ = (
        UniqueConstraint("batch_id", "row_number", name="uq_seo_queries_raw_batch_row_number"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey("seo_query_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    row_number = Column(Integer, nullable=False)
    raw_query = Column(Text, nullable=False)
    raw_frequency = Column(Numeric(14, 4), nullable=False, server_default="1")
    source_payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SeoQueryNormalized(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Deterministically normalized and deduplicated queries."""

    __tablename__ = "seo_queries_normalized"
    __table_args__ = (
        UniqueConstraint("batch_id", "normalized_query", name="uq_seo_queries_normalized_batch_query"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(Integer, ForeignKey("seo_query_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    normalized_query = Column(Text, nullable=False)
    display_query = Column(Text, nullable=False)
    normalization_version = Column(String(32), nullable=False, server_default="v1_minimal")
    raw_row_count = Column(Integer, nullable=False, server_default="0")
    frequency_total = Column(Numeric(14, 4), nullable=False, server_default="0")
    sample_source_payload = Column(JSON, nullable=False, default=dict)


class SeoQueryCluster(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Query cluster skeleton scoped by WB category."""

    __tablename__ = "seo_query_clusters"
    __table_args__ = (
        UniqueConstraint("project_id", "category_id", "cluster_key", name="uq_seo_query_clusters_scope_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_batch_id = Column(Integer, ForeignKey("seo_query_batches.id", ondelete="SET NULL"), nullable=True, index=True)
    cluster_key = Column(String(128), nullable=False)
    label = Column(Text, nullable=True)
    top_query_text = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, server_default="placeholder")
    is_other = Column(Boolean, nullable=False, server_default="false")
    is_noise = Column(Boolean, nullable=False, server_default="false")
    manual_review_required = Column(Boolean, nullable=False, server_default="false")
    query_count = Column(Integer, nullable=False, server_default="0")
    head_query_count = Column(Integer, nullable=False, server_default="0")
    mid_query_count = Column(Integer, nullable=False, server_default="0")
    tail_query_count = Column(Integer, nullable=False, server_default="0")
    meta = Column(JSON, nullable=False, default=dict)


class SeoQueryClusterMembership(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Current membership of one canonical query in one query cluster."""

    __tablename__ = "seo_query_cluster_memberships"
    __table_args__ = (
        UniqueConstraint("project_id", "category_id", "normalized_query_text", name="uq_seo_query_cluster_memberships_scope_query"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(Integer, ForeignKey("seo_query_clusters.id", ondelete="CASCADE"), nullable=False, index=True)
    annotation_id = Column(Integer, ForeignKey("seo_query_annotations.id", ondelete="CASCADE"), nullable=False, index=True)
    normalized_query_text = Column(Text, nullable=False, index=True)
    query_type = Column(String(32), nullable=False, server_default="tail")
    ranking_value_used = Column(Numeric(14, 4), nullable=False, server_default="0")
    membership_reason_code = Column(String(64), nullable=False, server_default="singleton_fallback")


class SeoQueryAnnotation(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Current pruning/annotation state for one canonical query."""

    __tablename__ = "seo_query_annotations"
    __table_args__ = (
        UniqueConstraint("project_id", "category_id", "normalized_query_text", name="uq_seo_query_annotations_scope_query"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    normalized_query_id = Column(Integer, ForeignKey("seo_queries_normalized.id", ondelete="SET NULL"), nullable=True, index=True)
    normalized_query_text = Column(Text, nullable=False, index=True)
    annotation_status = Column(String(32), nullable=False, server_default="pending")
    pruning_status = Column(String(32), nullable=False, server_default="review")
    pruning_reason_code = Column(String(64), nullable=False, server_default="migrated_pending")
    is_kept_for_pipeline = Column(Boolean, nullable=False, server_default="false")
    query_type = Column(String(32), nullable=False, server_default="tail")
    intent_type = Column(String(32), nullable=False, server_default="unknown")
    annotation_reason_code = Column(String(64), nullable=False, server_default="migrated_pending")
    latest_version_number = Column(Integer, nullable=False, server_default="0")
    meta = Column(JSON, nullable=False, default=dict)


class SeoQueryAnnotationVersion(SeoProjectCategoryScopedMixin, Base):
    """Versioned query annotation payloads."""

    __tablename__ = "seo_query_annotation_versions"
    __table_args__ = (
        UniqueConstraint("annotation_id", "version_number", name="uq_seo_query_annotation_versions_version"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    annotation_id = Column(Integer, ForeignKey("seo_query_annotations.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    annotation_payload = Column(JSON, nullable=False, default=dict)
    rationale = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SeoSkuClusterRun(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """[FROZEN iter-1] SKU clustering run skeleton.

    DEPRECATED as of SEO iteration 1 (see
    docs/seo-module/implementation-plan/10_implementation_decision_lock_v1.md
    §4.1 E — dead schema freeze). Table rows stay in place but no new code is
    allowed to import this class from production paths; matcher_v2 replaces
    the clustering+scoring legacy pipeline. Removal is scheduled for a later
    iteration, after backfill/migration decisions are made.
    """

    __frozen__ = True

    __tablename__ = "seo_sku_cluster_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(32), nullable=False, server_default="placeholder")
    presegmentation_strategy = Column(String(64), nullable=False, server_default="todo_rule_based")
    representation_strategy = Column(String(64), nullable=False, server_default="trust_aware_placeholder")
    clustering_backend = Column(String(64), nullable=False, server_default="hdbscan_placeholder")
    config = Column(JSON, nullable=False, default=dict)
    stats = Column(JSON, nullable=False, default=dict)


class SeoSkuCluster(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """[FROZEN iter-1] SKU cluster shell.

    DEPRECATED (see ``SeoSkuClusterRun``). Do not import from production
    code; use ``SeoMatcherRun``/``SeoMatcherResult`` via ``matcher_v2``.
    """

    __frozen__ = True

    __tablename__ = "seo_sku_clusters"
    __table_args__ = (
        UniqueConstraint("run_id", "cluster_key", name="uq_seo_sku_clusters_run_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("seo_sku_cluster_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    cluster_key = Column(String(128), nullable=False)
    segment_key = Column(String(128), nullable=True)
    label = Column(Text, nullable=True)
    is_other = Column(Boolean, nullable=False, server_default="false")
    is_noise_bucket = Column(Boolean, nullable=False, server_default="false")
    manual_review_required = Column(Boolean, nullable=False, server_default="false")
    sku_count = Column(Integer, nullable=False, server_default="0")
    meta = Column(JSON, nullable=False, default=dict)


class SeoSkuClusterAssignment(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """[FROZEN iter-1] SKU cluster assignment shell.

    DEPRECATED (see ``SeoSkuClusterRun``). Do not import from production
    code; use ``SeoMatcherRun``/``SeoMatcherResult`` via ``matcher_v2``.
    """

    __frozen__ = True

    __tablename__ = "seo_sku_cluster_assignments"
    __table_args__ = (
        UniqueConstraint("run_id", "nm_id", name="uq_seo_sku_cluster_assignments_run_nm"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("seo_sku_cluster_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    cluster_id = Column(Integer, ForeignKey("seo_sku_clusters.id", ondelete="SET NULL"), nullable=True, index=True)
    nm_id = Column(Integer, nullable=False, index=True)
    assignment_source = Column(String(64), nullable=False, server_default="manual_review_required")
    confidence = Column(Numeric(10, 4), nullable=True)
    is_noise = Column(Boolean, nullable=False, server_default="false")
    manual_review_required = Column(Boolean, nullable=False, server_default="false")
    explanation = Column(JSON, nullable=False, default=dict)


class SeoClusterProfile(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """[FROZEN iter-1] Cluster profile shell.

    DEPRECATED (see ``SeoSkuClusterRun``). Category profiles ship in
    iteration 2 as ``SeoCategoryProfile``; this legacy cluster-level profile
    is retained only for rollback.
    """

    __frozen__ = True

    __tablename__ = "seo_cluster_profiles"
    __table_args__ = (
        UniqueConstraint("cluster_id", name="uq_seo_cluster_profiles_cluster_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(Integer, ForeignKey("seo_sku_clusters.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), nullable=False, server_default="draft")
    current_version_number = Column(Integer, nullable=False, server_default="0")
    summary = Column(JSON, nullable=False, default=dict)


class SeoClusterProfileVersion(SeoProjectCategoryScopedMixin, Base):
    """[FROZEN iter-1] Cluster profile version shell.

    DEPRECATED (see ``SeoClusterProfile``). Do not import from production
    code.
    """

    __frozen__ = True

    __tablename__ = "seo_cluster_profile_versions"
    __table_args__ = (
        UniqueConstraint("profile_id", "version_number", name="uq_seo_cluster_profile_versions_version"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Integer, ForeignKey("seo_cluster_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)
    product_type = Column(JSON, nullable=False, default=dict)
    use_cases = Column(JSON, nullable=False, default=dict)
    attributes = Column(JSON, nullable=False, default=dict)
    language_markers = Column(JSON, nullable=False, default=dict)
    anti_patterns = Column(JSON, nullable=False, default=dict)
    source_summary = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SeoScoreRun(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """[FROZEN iter-1] Score run shell.

    DEPRECATED. The legacy scoring pipeline (``services/seo/scoring``) is
    diagnostic-only. Production matching+scoring is owned by
    ``services/seo/matcher_v2``. See decision lock §4.1 E.
    """

    __frozen__ = True

    __tablename__ = "seo_score_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scoring_weights_version = Column(String(64), nullable=False, server_default="v1_default")
    status = Column(String(32), nullable=False, server_default="placeholder")
    config = Column(JSON, nullable=False, default=dict)
    stats = Column(JSON, nullable=False, default=dict)


class SeoQueryScore(SeoProjectCategoryScopedMixin, Base):
    """[FROZEN iter-1] Per-query score shell.

    DEPRECATED (see ``SeoScoreRun``). Use ``SeoMatcherResult`` instead.
    """

    __frozen__ = True

    __tablename__ = "seo_query_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    score_run_id = Column(Integer, ForeignKey("seo_score_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    normalized_query_id = Column(Integer, ForeignKey("seo_queries_normalized.id", ondelete="SET NULL"), nullable=True, index=True)
    nm_id = Column(Integer, nullable=True, index=True)
    cluster_id = Column(Integer, ForeignKey("seo_sku_clusters.id", ondelete="SET NULL"), nullable=True, index=True)
    total_score = Column(Numeric(12, 4), nullable=False, server_default="0")
    decision = Column(String(32), nullable=False, server_default="candidate")
    component_values = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SeoScoreExplanation(Base):
    """[FROZEN iter-1] Explainability rows for query scores.

    DEPRECATED (see ``SeoScoreRun``). ``SeoMatcherResult.score_components``
    now carries per-component explanations.
    """

    __frozen__ = True

    __tablename__ = "seo_score_explanations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_score_id = Column(Integer, ForeignKey("seo_query_scores.id", ondelete="CASCADE"), nullable=False, index=True)
    component_name = Column(String(64), nullable=False)
    component_value = Column(Numeric(12, 4), nullable=False, server_default="0")
    weight = Column(Numeric(12, 4), nullable=False, server_default="0")
    contribution = Column(Numeric(12, 4), nullable=False, server_default="0")
    details = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SeoContentVersion(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Content version shell."""

    __tablename__ = "seo_content_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    nm_id = Column(Integer, nullable=False, index=True)
    cluster_profile_version_id = Column(Integer, ForeignKey("seo_cluster_profile_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    score_run_id = Column(Integer, ForeignKey("seo_score_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    content_kind = Column(String(32), nullable=False, server_default="draft")
    title = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    query_snapshot = Column(JSON, nullable=False, default=dict)
    score_breakdown = Column(JSON, nullable=False, default=dict)
    status = Column(String(32), nullable=False, server_default="draft")
    # Iteration 1 additive columns (see docs/seo-module/implementation-plan/04_* §2.4).
    quality_mode = Column(String(16), nullable=True)
    degraded_reasons = Column(JSON, nullable=True)
    mode_used = Column(String(16), nullable=False, server_default="current")
    publishable = Column(Boolean, nullable=False, server_default="false")
    matcher_run_id = Column(Integer, ForeignKey("seo_matcher_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    # Iteration 2 (WS-D): tightened lifecycle.
    # ``content_kind`` valid values become ``preview | candidate | approved | published``.
    # ``preview`` replaces the iteration-1 ``llm_draft`` label (migration writes the map).
    # ``published`` is unreachable in iteration 2 (production generation OFF).
    # ``category_profile_version`` is mirrored from the upstream matcher run so promotion
    # gates can quote the profile that produced the candidate text.
    category_profile_version = Column(String(64), nullable=True)


class SeoGenerationRun(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Generation run shell."""

    __tablename__ = "seo_generation_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_version_id = Column(Integer, ForeignKey("seo_content_versions.id", ondelete="SET NULL"), nullable=True, index=True)
    provider_name = Column(String(64), nullable=True)
    model_name = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False, server_default="not_started")
    request_payload = Column(JSON, nullable=False, default=dict)
    response_payload = Column(JSON, nullable=False, default=dict)
    error_text = Column(Text, nullable=True)
    # Iteration 1 additive columns.
    quality_mode = Column(String(16), nullable=True)
    degraded_reasons = Column(JSON, nullable=True)
    matcher_run_id = Column(Integer, ForeignKey("seo_matcher_runs.id", ondelete="SET NULL"), nullable=True, index=True)


class SeoQueryMeaning(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Cluster-level query meaning library for meaning-aware matching."""

    __tablename__ = "seo_query_meanings"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_id",
            "cluster_key",
            "schema_version",
            name="uq_seo_query_meanings_scope_cluster_schema",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    cluster_id = Column(Integer, ForeignKey("seo_query_clusters.id", ondelete="SET NULL"), nullable=True, index=True)
    cluster_key = Column(String(128), nullable=False)
    schema_version = Column(String(64), nullable=False, server_default="query_meaning_v0")
    source_query_examples = Column(JSON, nullable=False, default=list)
    meaning_payload = Column(JSON, nullable=False, default=dict)
    canonical_text = Column(Text, nullable=False)
    genericness = Column(String(32), nullable=False, server_default="specific")
    constraints = Column(JSON, nullable=False, default=list)
    conflicts_if_missing = Column(JSON, nullable=False, default=list)
    llm_model = Column(String(128), nullable=True)
    prompt_version = Column(String(64), nullable=False, server_default="query_meaning_library_v0")
    input_hash = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False, server_default="draft")


class SeoMeaningEmbedding(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Embeddings for stored query meanings and SKU meanings."""

    __tablename__ = "seo_meaning_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "entity_type",
            "entity_id",
            "model",
            "input_hash",
            name="uq_seo_meaning_embeddings_entity_model_hash",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(32), nullable=False, index=True)
    entity_id = Column(Integer, nullable=False, index=True)
    model = Column(String(128), nullable=False)
    input_hash = Column(String(128), nullable=False, index=True)
    embedding = Column(JSON, nullable=False, default=list)
    canonical_text = Column(Text, nullable=False)


class SeoMeaningAtom(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Production storage for extracted query/SKU/Vision meaning atoms."""

    __tablename__ = "seo_meaning_atoms"
    __table_args__ = (
        Index("ix_seo_meaning_atoms_entity_scope", "project_id", "category_id", "entity_type", "entity_id"),
        Index("ix_seo_meaning_atoms_sku_scope", "project_id", "category_id", "nm_id", "entity_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(32), nullable=False, index=True)
    entity_id = Column(Integer, nullable=True, index=True)
    nm_id = Column(Integer, nullable=True, index=True)
    schema_version = Column(String(64), nullable=False, server_default="meaning_atoms_v0")
    source_version = Column(String(64), nullable=False, server_default="meaning_atoms_v0")
    model = Column(String(128), nullable=True)
    prompt_version = Column(String(64), nullable=True)
    input_hash = Column(String(128), nullable=False, index=True)
    atoms_payload = Column(JSON, nullable=False, default=dict)
    canonical_summary = Column(Text, nullable=False, server_default="")
    status = Column(String(32), nullable=False, server_default="ready")
    error = Column(Text, nullable=True)


class SeoCategoryBootstrapRun(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """One category bootstrap execution for meaning-aware matching readiness."""

    __tablename__ = "seo_category_bootstrap_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trigger = Column(String(32), nullable=False, server_default="manual")
    status = Column(String(32), nullable=False, server_default="queued")
    current_step = Column(String(64), nullable=True)
    step_statuses = Column(JSON, nullable=False, default=dict)
    input_hash = Column(String(128), nullable=True)
    error = Column(Text, nullable=True)


class SeoCategoryMatchingReadiness(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Current category readiness state for meaning-aware matching."""

    __tablename__ = "seo_category_matching_readiness"
    __table_args__ = (
        UniqueConstraint("project_id", "category_id", name="uq_seo_category_matching_readiness_scope"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(32), nullable=False, server_default="not_started")
    latest_run_id = Column(Integer, ForeignKey("seo_category_bootstrap_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    query_batch_id = Column(Integer, ForeignKey("seo_query_batches.id", ondelete="SET NULL"), nullable=True, index=True)
    queries_count = Column(Integer, nullable=False, server_default="0")
    clusters_count = Column(Integer, nullable=False, server_default="0")
    query_meanings_count = Column(Integer, nullable=False, server_default="0")
    query_atoms_count = Column(Integer, nullable=False, server_default="0")
    embeddings_count = Column(Integer, nullable=False, server_default="0")
    category_axes_status = Column(String(32), nullable=False, server_default="not_started")
    last_error = Column(Text, nullable=True)
    # Iteration 2 (WS-E): eligibility tier for the candidate matcher.
    # Single writer: app.services.seo.eval.harness.update_eligibility_tier.
    # See docs/seo-module/implementation-plan/05_backend_contract_changes.md.
    eligibility_tier = Column(String(32), nullable=False, server_default="preview_only")


class SeoCategoryMeaningAxes(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Category-level meaning axes extracted from products, queries, and reviews."""

    __tablename__ = "seo_category_meaning_axes"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_id",
            "schema_version",
            "source",
            name="uq_seo_category_meaning_axes_scope_schema_source",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    schema_version = Column(String(64), nullable=False, server_default="category_meaning_axes_v0")
    source = Column(String(32), nullable=False, server_default="deterministic")
    status = Column(String(32), nullable=False, server_default="draft")
    evidence_hash = Column(String(128), nullable=False)
    axes_payload = Column(JSON, nullable=False, default=dict)
    canonical_text = Column(Text, nullable=False)
    llm_model = Column(String(128), nullable=True)
    prompt_version = Column(String(64), nullable=False, server_default="category_meaning_axes_v0")
    input_hash = Column(String(128), nullable=False)


class SeoSkuMeaningAnnotation(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Human-reviewed SKU meaning annotation for internal SEO eval work."""

    __tablename__ = "seo_sku_meaning_annotations"
    __table_args__ = (
        UniqueConstraint("project_id", "nm_id", "schema_version", name="uq_seo_sku_meaning_annotations_scope_schema"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    nm_id = Column(Integer, nullable=False, index=True)
    schema_version = Column(String(64), nullable=False, server_default="sku_meaning_v0")
    status = Column(String(32), nullable=False, server_default="draft")
    meaning_payload = Column(JSON, nullable=False, default=dict)
    reviewer = Column(String(128), nullable=True)
    evidence_hash = Column(String(128), nullable=False)
    source_metadata = Column(JSON, nullable=False, default=dict)
    draft_model = Column(String(128), nullable=True)
    draft_prompt_version = Column(String(64), nullable=True)
    draft_artifact_path = Column(Text, nullable=True)
    # Iteration 1 additive columns.
    quality_mode = Column(String(16), nullable=True)
    degraded_reasons = Column(JSON, nullable=True)


class SeoSkuQueryJudgment(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Manual query relevance judgment attached to a SKU meaning annotation."""

    __tablename__ = "seo_sku_query_judgments"
    __table_args__ = (
        UniqueConstraint("annotation_id", "normalized_query_text", name="uq_seo_sku_query_judgments_annotation_query"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    annotation_id = Column(Integer, ForeignKey("seo_sku_meaning_annotations.id", ondelete="CASCADE"), nullable=False, index=True)
    nm_id = Column(Integer, nullable=False, index=True)
    query_text = Column(Text, nullable=False)
    normalized_query_text = Column(Text, nullable=False, index=True)
    query_id = Column(Integer, ForeignKey("seo_query_annotations.id", ondelete="SET NULL"), nullable=True, index=True)
    cluster_id = Column(Integer, ForeignKey("seo_query_clusters.id", ondelete="SET NULL"), nullable=True, index=True)
    cluster_key = Column(String(128), nullable=True)
    label = Column(String(32), nullable=False)
    rationale = Column(Text, nullable=True)
    reviewer = Column(String(128), nullable=True)
    matcher_version = Column(String(64), nullable=True)
    source = Column(String(64), nullable=False, server_default="manual")


class SeoSkuQuerySet(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Saved query set for future SKU content generation."""

    __tablename__ = "seo_sku_query_sets"
    __table_args__ = (
        UniqueConstraint("project_id", "category_id", "nm_id", "status", name="uq_seo_sku_query_sets_scope_status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    nm_id = Column(Integer, nullable=False, index=True)
    status = Column(String(32), nullable=False, server_default="draft")
    matcher_version = Column(String(64), nullable=True)
    atoms_version = Column(String(64), nullable=True)
    source_hash = Column(String(128), nullable=True, index=True)
    # Iteration 1 additive columns.
    quality_mode = Column(String(16), nullable=True)
    degraded_reasons = Column(JSON, nullable=True)
    matcher_run_id = Column(Integer, ForeignKey("seo_matcher_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    # Iteration 2 (WS-C / WS-E): query-set-level approval and trust state.
    # ``approval_state`` replaces the legacy ``status == 'confirmed'`` semantic
    # at the candidate-path level; the legacy ``status`` column stays in place
    # for backward compatibility this iteration. ``trust_state`` is written
    # only when an eval run has cleared the SKU's category for use.
    # ``category_profile_version`` is mirrored from ``SeoMatcherRun`` so the
    # downstream generation lifecycle can quote the exact profile version.
    # Names intentionally avoid colliding with ``SeoSkuQuerySetItem.selection_state``.
    approval_state = Column(String(32), nullable=False, server_default="draft")
    trust_state = Column(String(32), nullable=False, server_default="unverified")
    category_profile_version = Column(String(64), nullable=True)


class SeoSkuQuerySetItem(TimestampMixin, Base):
    """One query inside a saved SKU query set."""

    __tablename__ = "seo_sku_query_set_items"
    __table_args__ = (
        UniqueConstraint("query_set_id", "normalized_query_text", name="uq_seo_sku_query_set_items_set_query"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_set_id = Column(Integer, ForeignKey("seo_sku_query_sets.id", ondelete="CASCADE"), nullable=False, index=True)
    normalized_query_text = Column(Text, nullable=False)
    display_query = Column(Text, nullable=False)
    cluster_key = Column(String(128), nullable=True)
    bucket = Column(String(32), nullable=False)
    score = Column(Numeric(12, 4), nullable=False, server_default="0")
    ranking_value_used = Column(Numeric(14, 4), nullable=True)
    selection_state = Column(String(32), nullable=False, server_default="auto_selected")
    reasons_payload = Column(JSON, nullable=False, default=dict)


class SeoCategorySelectedQuery(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Operator-maintained reusable query list for a category."""

    __tablename__ = "seo_category_selected_queries"
    __table_args__ = (
        UniqueConstraint("project_id", "category_id", "query_text", name="uq_seo_category_selected_queries_scope_query"),
        Index("ix_seo_category_selected_queries_scope_order", "project_id", "category_id", "sort_order"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_text = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, server_default="0")
    created_by = Column(String(128), nullable=True)


class SeoSkuMeaningAuditEvent(SeoProjectCategoryScopedMixin, Base):
    """Append-only audit events for the SKU meaning annotation tool."""

    __tablename__ = "seo_sku_meaning_audit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    annotation_id = Column(Integer, ForeignKey("seo_sku_meaning_annotations.id", ondelete="SET NULL"), nullable=True, index=True)
    nm_id = Column(Integer, nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    actor = Column(String(128), nullable=True)
    event_payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


# ---------------------------------------------------------------------------
# Iteration 1: candidate matcher authority tables.
#
# ``SeoMatcherRun`` + ``SeoMatcherResult`` are the replayable trace for every
# candidate matcher decision. Written only by
# ``services/seo/matcher_v2/api.py::run_matcher_v2``. Re-runs create new rows;
# rows are never mutated.
# ---------------------------------------------------------------------------


class SeoMatcherRun(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Replayable trace of a single candidate-path matcher invocation."""

    __tablename__ = "seo_matcher_runs"
    __table_args__ = (
        Index("ix_seo_matcher_runs_scope", "project_id", "category_id", "nm_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    nm_id = Column(Integer, nullable=False, index=True)
    matcher_version = Column(String(64), nullable=False)
    policy_version = Column(String(64), nullable=False)
    category_profile_version = Column(String(64), nullable=False)
    sku_atoms_id = Column(Integer, ForeignKey("seo_meaning_atoms.id", ondelete="SET NULL"), nullable=True, index=True)
    vision_atoms_id = Column(Integer, ForeignKey("seo_meaning_atoms.id", ondelete="SET NULL"), nullable=True, index=True)
    query_atoms_version = Column(String(64), nullable=True)
    embedding_model = Column(String(128), nullable=True)
    readiness_snapshot = Column(JSON, nullable=False, default=dict)
    quality_mode = Column(String(16), nullable=True)
    degraded_reasons = Column(JSON, nullable=True)
    metrics = Column(JSON, nullable=False, default=dict)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(JSON, nullable=True)


class SeoMatcherResult(Base):
    """Per-query bucket + score + explanation tied to a specific matcher run."""

    __tablename__ = "seo_matcher_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("seo_matcher_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    cluster_key = Column(String(128), nullable=True, index=True)
    query_meaning_id = Column(Integer, ForeignKey("seo_query_meanings.id", ondelete="SET NULL"), nullable=True, index=True)
    query_display = Column(Text, nullable=False)
    normalized_query_text = Column(Text, nullable=False)
    bucket = Column(String(32), nullable=False, index=True)
    eligibility_verdict = Column(String(40), nullable=False)
    score = Column(Numeric(12, 4), nullable=False, server_default="0")
    score_components = Column(JSON, nullable=False, default=dict)
    matched_atoms = Column(JSON, nullable=False, default=list)
    missing_atoms = Column(JSON, nullable=False, default=list)
    conflict_atoms = Column(JSON, nullable=False, default=list)
    reasons = Column(JSON, nullable=False, default=list)
    ranking_value_used = Column(Numeric(14, 4), nullable=True)
    semantic_similarity = Column(Numeric(12, 6), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


# ---------------------------------------------------------------------------
# Iteration 2 — versioned category profile, eval-as-a-gate, generation
# promotion lifecycle, and read-only compare verdicts.
#
# All tables are additive. See:
#   docs/seo-module/implementation-plan/04_data_model_and_state_changes.md
#   docs/seo-module/implementation-plan/05_backend_contract_changes.md
# ---------------------------------------------------------------------------


class SeoCategoryProfile(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Versioned category-calibrated profile consumed by ``matcher_v2``.

    Single writer: the seed/import scripts in ``scripts/seed_seo_category_profile_*``.
    Readers: ``app.services.seo.category_profile.load_active_profile``.

    Iteration 2 ships exactly one active profile for category 812. Adding new
    categories is explicitly out of scope; the table shape supports it though.
    """

    __tablename__ = "seo_category_profiles"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_id",
            "version",
            name="uq_seo_category_profiles_scope_version",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(64), nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="false", index=True)
    payload = Column(JSON, nullable=False, default=dict)
    source_note = Column(Text, nullable=True)


class SeoCategoryProfileDeriveRun(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Observability row for one category-profile derive attempt."""

    __tablename__ = "seo_category_profile_derive_runs"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_seo_category_profile_derive_runs_run_id"),
        Index("ix_seo_category_profile_derive_runs_scope", "project_id", "category_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(36), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(32), nullable=False, server_default="running")
    method = Column(String(64), nullable=False, server_default="skeleton_v0")
    llm_model = Column(String(128), nullable=True)
    prompt_version = Column(String(64), nullable=True)
    evidence_hash = Column(String(128), nullable=True)
    profile_version = Column(String(64), nullable=True)
    profile_id = Column(Integer, ForeignKey("seo_category_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    self_check_json = Column(JSON, nullable=False, default=dict)
    eval_baseline_json = Column(JSON, nullable=True)
    eval_new_json = Column(JSON, nullable=True)
    diff_summary = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)


class SeoEvalLabel(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Gold-standard expected bucket for a (category, query[, nm_id]) row.

    Iteration 2 seed: 191 rows for category 812 imported from
    ``artifacts/meaning_atoms/20260422_*/comparison.csv`` via
    ``scripts/import_seo_eval_labels_812.py``.
    """

    __tablename__ = "seo_eval_labels"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_id",
            "label_set_id",
            "query_text_normalized",
            "nm_id",
            name="uq_seo_eval_labels_scope_query_nm",
        ),
        Index("ix_seo_eval_labels_set_query", "label_set_id", "query_text_normalized"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    label_set_id = Column(Integer, nullable=False, index=True)
    query_text_normalized = Column(Text, nullable=False)
    nm_id = Column(Integer, nullable=True, index=True)
    expected_bucket = Column(String(32), nullable=False)
    expected_reason = Column(Text, nullable=True)
    source = Column(String(64), nullable=False, server_default="comparison_csv_812")


class SeoEvalRun(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Computed metrics for one matcher eval execution.

    Single writer: ``app.services.seo.eval.harness.run_matcher_eval``. The
    harness is also the only writer of
    ``SeoCategoryMatchingReadiness.eligibility_tier`` (D2 single-writer).
    """

    __tablename__ = "seo_eval_runs"
    __table_args__ = (
        Index("ix_seo_eval_runs_scope", "project_id", "category_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    label_set_id = Column(Integer, nullable=False, index=True)
    metrics = Column(JSON, nullable=False, default=dict)
    thresholds = Column(JSON, nullable=False, default=dict)
    verdict = Column(String(32), nullable=False, server_default="preview_only")
    matcher_run_ids = Column(JSON, nullable=False, default=list)
    nm_ids = Column(JSON, nullable=False, default=list)
    notes = Column(Text, nullable=True)
    created_by = Column(String(128), nullable=True)


class SeoGenerationHumanReview(TimestampMixin, Base):
    """Human rubric verdict captured against a content version.

    Required artifact for ``preview -> candidate`` and ``candidate -> approved``
    promotions; written only by the promote endpoint flow.
    """

    __tablename__ = "seo_generation_human_review"
    __table_args__ = (
        Index("ix_seo_generation_human_review_content", "content_version_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_version_id = Column(
        Integer,
        ForeignKey("seo_content_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer = Column(String(128), nullable=True)
    rubric = Column(JSON, nullable=False, default=dict)
    verdict = Column(String(32), nullable=False)  # accept | reject | needs_changes
    notes = Column(Text, nullable=True)


class SeoCompareVerdict(TimestampMixin, Base):
    """Operator verdict captured from the read-only compare layer.

    The compare layer is forbidden from mutating ``SeoMatcherRun`` /
    ``SeoMatcherResult`` / ``SeoContentVersion``. Verdicts live in their own
    append-only table so they cannot leak into the trace.
    """

    __tablename__ = "seo_compare_verdicts"
    __table_args__ = (
        Index("ix_seo_compare_verdicts_subject", "subject_type", "subject_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_type = Column(String(32), nullable=False)  # "matcher" | "generation"
    subject_id = Column(Integer, nullable=False, index=True)
    related_id = Column(Integer, nullable=True)
    verdict = Column(String(32), nullable=False)
    notes = Column(Text, nullable=True)
    created_by = Column(String(128), nullable=True)
