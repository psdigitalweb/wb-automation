"""SQLAlchemy declarative models for core and SEO foundation tables."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, Boolean
from sqlalchemy.sql import func

from .db import Base


CATEGORY_SCOPE_COMMENT = (
    "WB category scope for SEO pipeline (Wildberries subject_id/category scope), "
    "not a foreign key to internal_categories.id."
)


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
    status = Column(String(32), nullable=False, server_default="placeholder")
    is_other = Column(Boolean, nullable=False, server_default="false")
    is_noise = Column(Boolean, nullable=False, server_default="false")
    manual_review_required = Column(Boolean, nullable=False, server_default="false")
    query_count = Column(Integer, nullable=False, server_default="0")
    meta = Column(JSON, nullable=False, default=dict)


class SeoQueryAnnotation(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """Annotation tracking shell for normalized queries."""

    __tablename__ = "seo_query_annotations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    normalized_query_id = Column(Integer, ForeignKey("seo_queries_normalized.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    annotation_status = Column(String(32), nullable=False, server_default="pending")
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
    """SKU clustering run skeleton."""

    __tablename__ = "seo_sku_cluster_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(32), nullable=False, server_default="placeholder")
    presegmentation_strategy = Column(String(64), nullable=False, server_default="todo_rule_based")
    representation_strategy = Column(String(64), nullable=False, server_default="trust_aware_placeholder")
    clustering_backend = Column(String(64), nullable=False, server_default="hdbscan_placeholder")
    config = Column(JSON, nullable=False, default=dict)
    stats = Column(JSON, nullable=False, default=dict)


class SeoSkuCluster(SeoProjectCategoryScopedMixin, TimestampMixin, Base):
    """SKU cluster shell."""

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
    """SKU cluster assignment shell."""

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
    """Cluster profile shell."""

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
    """Cluster profile version shell."""

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
    """Score run shell."""

    __tablename__ = "seo_score_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scoring_weights_version = Column(String(64), nullable=False, server_default="v1_default")
    status = Column(String(32), nullable=False, server_default="placeholder")
    config = Column(JSON, nullable=False, default=dict)
    stats = Column(JSON, nullable=False, default=dict)


class SeoQueryScore(SeoProjectCategoryScopedMixin, Base):
    """Per-query score shell."""

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
    """Explainability rows for query scores."""

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
