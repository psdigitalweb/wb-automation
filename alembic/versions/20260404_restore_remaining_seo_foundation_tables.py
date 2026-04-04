"""Restore remaining SEO foundation tables after Task 02 ingestion subset.

Revision ID: 20260404_restore_remaining_seo_foundation_tables
Revises: 20260404_add_seo_query_ingestion_tables
Create Date: 2026-04-04
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "20260404_restore_remaining_seo_foundation_tables"
down_revision: Union[str, None] = "20260404_add_seo_query_ingestion_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CATEGORY_SCOPE_COMMENT = (
    "WB category scope for SEO pipeline (Wildberries subject_id/category scope), "
    "not a foreign key to internal_categories.id."
)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    ]


def _scope_columns() -> list[sa.Column]:
    return [
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False, comment=CATEGORY_SCOPE_COMMENT),
    ]


def _create_indexes(inspector: sa.Inspector, table_name: str, specs: list[tuple[str, list[str]]]) -> None:
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    for index_name, columns in specs:
        if index_name not in existing:
            op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "seo_query_clusters" not in existing_tables:
        op.create_table(
            "seo_query_clusters",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            *_scope_columns(),
            sa.Column("source_batch_id", sa.Integer(), nullable=True),
            sa.Column("cluster_key", sa.String(length=128), nullable=False),
            sa.Column("label", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'placeholder'")),
            sa.Column("is_other", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_noise", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("manual_review_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("query_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            *_timestamps(),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["source_batch_id"], ["seo_query_batches.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("project_id", "category_id", "cluster_key", name="uq_seo_query_clusters_scope_key"),
        )
        inspector = inspect(bind)
    _create_indexes(
        inspector,
        "seo_query_clusters",
        [
            ("idx_seo_query_clusters_project_id", ["project_id"]),
            ("idx_seo_query_clusters_category_id", ["category_id"]),
            ("idx_seo_query_clusters_source_batch_id", ["source_batch_id"]),
        ],
    )

    if "seo_query_annotations" not in existing_tables:
        op.create_table(
            "seo_query_annotations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            *_scope_columns(),
            sa.Column("normalized_query_id", sa.Integer(), nullable=False),
            sa.Column("annotation_status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
            sa.Column("latest_version_number", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            *_timestamps(),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["normalized_query_id"], ["seo_queries_normalized.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("normalized_query_id", name="uq_seo_query_annotations_normalized_query_id"),
        )
        inspector = inspect(bind)
    _create_indexes(
        inspector,
        "seo_query_annotations",
        [
            ("idx_seo_query_annotations_project_id", ["project_id"]),
            ("idx_seo_query_annotations_category_id", ["category_id"]),
            ("idx_seo_query_annotations_normalized_query_id", ["normalized_query_id"]),
        ],
    )

    if "seo_query_annotation_versions" not in existing_tables:
        op.create_table(
            "seo_query_annotation_versions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            *_scope_columns(),
            sa.Column("annotation_id", sa.Integer(), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("annotation_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("rationale", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["annotation_id"], ["seo_query_annotations.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("annotation_id", "version_number", name="uq_seo_query_annotation_versions_version"),
        )
        inspector = inspect(bind)
    _create_indexes(
        inspector,
        "seo_query_annotation_versions",
        [
            ("idx_seo_query_annotation_versions_project_id", ["project_id"]),
            ("idx_seo_query_annotation_versions_category_id", ["category_id"]),
            ("idx_seo_query_annotation_versions_annotation_id", ["annotation_id"]),
        ],
    )

    if "seo_sku_cluster_runs" not in existing_tables:
        op.create_table(
            "seo_sku_cluster_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            *_scope_columns(),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'placeholder'")),
            sa.Column(
                "presegmentation_strategy",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("'todo_rule_based'"),
            ),
            sa.Column(
                "representation_strategy",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("'trust_aware_placeholder'"),
            ),
            sa.Column(
                "clustering_backend",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("'hdbscan_placeholder'"),
            ),
            sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("stats", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            *_timestamps(),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        )
        inspector = inspect(bind)
    _create_indexes(
        inspector,
        "seo_sku_cluster_runs",
        [
            ("idx_seo_sku_cluster_runs_project_id", ["project_id"]),
            ("idx_seo_sku_cluster_runs_category_id", ["category_id"]),
        ],
    )

    if "seo_sku_clusters" not in existing_tables:
        op.create_table(
            "seo_sku_clusters",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            *_scope_columns(),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("cluster_key", sa.String(length=128), nullable=False),
            sa.Column("segment_key", sa.String(length=128), nullable=True),
            sa.Column("label", sa.Text(), nullable=True),
            sa.Column("is_other", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_noise_bucket", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("manual_review_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("sku_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            *_timestamps(),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["run_id"], ["seo_sku_cluster_runs.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("run_id", "cluster_key", name="uq_seo_sku_clusters_run_key"),
        )
        inspector = inspect(bind)
    _create_indexes(
        inspector,
        "seo_sku_clusters",
        [
            ("idx_seo_sku_clusters_project_id", ["project_id"]),
            ("idx_seo_sku_clusters_category_id", ["category_id"]),
            ("idx_seo_sku_clusters_run_id", ["run_id"]),
        ],
    )

    if "seo_sku_cluster_assignments" not in existing_tables:
        op.create_table(
            "seo_sku_cluster_assignments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            *_scope_columns(),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("cluster_id", sa.Integer(), nullable=True),
            sa.Column("nm_id", sa.Integer(), nullable=False),
            sa.Column(
                "assignment_source",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("'manual_review_required'"),
            ),
            sa.Column("confidence", sa.Numeric(10, 4), nullable=True),
            sa.Column("is_noise", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("manual_review_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("explanation", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            *_timestamps(),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["run_id"], ["seo_sku_cluster_runs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["cluster_id"], ["seo_sku_clusters.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("run_id", "nm_id", name="uq_seo_sku_cluster_assignments_run_nm"),
        )
        inspector = inspect(bind)
    _create_indexes(
        inspector,
        "seo_sku_cluster_assignments",
        [
            ("idx_seo_sku_cluster_assignments_project_id", ["project_id"]),
            ("idx_seo_sku_cluster_assignments_category_id", ["category_id"]),
            ("idx_seo_sku_cluster_assignments_run_id", ["run_id"]),
            ("idx_seo_sku_cluster_assignments_cluster_id", ["cluster_id"]),
            ("idx_seo_sku_cluster_assignments_nm_id", ["nm_id"]),
        ],
    )

    if "seo_cluster_profiles" not in existing_tables:
        op.create_table(
            "seo_cluster_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            *_scope_columns(),
            sa.Column("cluster_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'draft'")),
            sa.Column("current_version_number", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            *_timestamps(),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["cluster_id"], ["seo_sku_clusters.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("cluster_id", name="uq_seo_cluster_profiles_cluster_id"),
        )
        inspector = inspect(bind)
    _create_indexes(
        inspector,
        "seo_cluster_profiles",
        [
            ("idx_seo_cluster_profiles_project_id", ["project_id"]),
            ("idx_seo_cluster_profiles_category_id", ["category_id"]),
            ("idx_seo_cluster_profiles_cluster_id", ["cluster_id"]),
        ],
    )

    if "seo_cluster_profile_versions" not in existing_tables:
        op.create_table(
            "seo_cluster_profile_versions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            *_scope_columns(),
            sa.Column("profile_id", sa.Integer(), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("product_type", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("use_cases", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("attributes", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("language_markers", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("anti_patterns", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("source_summary", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["profile_id"], ["seo_cluster_profiles.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("profile_id", "version_number", name="uq_seo_cluster_profile_versions_version"),
        )
        inspector = inspect(bind)
    _create_indexes(
        inspector,
        "seo_cluster_profile_versions",
        [
            ("idx_seo_cluster_profile_versions_project_id", ["project_id"]),
            ("idx_seo_cluster_profile_versions_category_id", ["category_id"]),
            ("idx_seo_cluster_profile_versions_profile_id", ["profile_id"]),
        ],
    )

    if "seo_score_runs" not in existing_tables:
        op.create_table(
            "seo_score_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            *_scope_columns(),
            sa.Column(
                "scoring_weights_version",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("'v1_default'"),
            ),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'placeholder'")),
            sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("stats", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            *_timestamps(),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        )
        inspector = inspect(bind)
    _create_indexes(
        inspector,
        "seo_score_runs",
        [
            ("idx_seo_score_runs_project_id", ["project_id"]),
            ("idx_seo_score_runs_category_id", ["category_id"]),
        ],
    )

    if "seo_query_scores" not in existing_tables:
        op.create_table(
            "seo_query_scores",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            *_scope_columns(),
            sa.Column("score_run_id", sa.Integer(), nullable=False),
            sa.Column("normalized_query_id", sa.Integer(), nullable=True),
            sa.Column("nm_id", sa.Integer(), nullable=True),
            sa.Column("cluster_id", sa.Integer(), nullable=True),
            sa.Column("total_score", sa.Numeric(12, 4), nullable=False, server_default=sa.text("0")),
            sa.Column("decision", sa.String(length=32), nullable=False, server_default=sa.text("'candidate'")),
            sa.Column("component_values", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["score_run_id"], ["seo_score_runs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["normalized_query_id"], ["seo_queries_normalized.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["cluster_id"], ["seo_sku_clusters.id"], ondelete="SET NULL"),
        )
        inspector = inspect(bind)
    _create_indexes(
        inspector,
        "seo_query_scores",
        [
            ("idx_seo_query_scores_score_run_id", ["score_run_id"]),
            ("idx_seo_query_scores_project_id", ["project_id"]),
            ("idx_seo_query_scores_category_id", ["category_id"]),
            ("idx_seo_query_scores_normalized_query_id", ["normalized_query_id"]),
            ("idx_seo_query_scores_nm_id", ["nm_id"]),
            ("idx_seo_query_scores_cluster_id", ["cluster_id"]),
        ],
    )

    if "seo_score_explanations" not in existing_tables:
        op.create_table(
            "seo_score_explanations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("query_score_id", sa.Integer(), nullable=False),
            sa.Column("component_name", sa.String(length=64), nullable=False),
            sa.Column("component_value", sa.Numeric(12, 4), nullable=False, server_default=sa.text("0")),
            sa.Column("weight", sa.Numeric(12, 4), nullable=False, server_default=sa.text("0")),
            sa.Column("contribution", sa.Numeric(12, 4), nullable=False, server_default=sa.text("0")),
            sa.Column("details", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["query_score_id"], ["seo_query_scores.id"], ondelete="CASCADE"),
        )
        inspector = inspect(bind)
    _create_indexes(
        inspector,
        "seo_score_explanations",
        [
            ("idx_seo_score_explanations_query_score_id", ["query_score_id"]),
        ],
    )

    if "seo_content_versions" not in existing_tables:
        op.create_table(
            "seo_content_versions",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            *_scope_columns(),
            sa.Column("nm_id", sa.Integer(), nullable=False),
            sa.Column("cluster_profile_version_id", sa.Integer(), nullable=True),
            sa.Column("score_run_id", sa.Integer(), nullable=True),
            sa.Column("content_kind", sa.String(length=32), nullable=False, server_default=sa.text("'draft'")),
            sa.Column("title", sa.Text(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("query_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("score_breakdown", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'draft'")),
            *_timestamps(),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["cluster_profile_version_id"],
                ["seo_cluster_profile_versions.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(["score_run_id"], ["seo_score_runs.id"], ondelete="SET NULL"),
        )
        inspector = inspect(bind)
    _create_indexes(
        inspector,
        "seo_content_versions",
        [
            ("idx_seo_content_versions_project_id", ["project_id"]),
            ("idx_seo_content_versions_category_id", ["category_id"]),
            ("idx_seo_content_versions_nm_id", ["nm_id"]),
            ("idx_seo_content_versions_cluster_profile_version_id", ["cluster_profile_version_id"]),
            ("idx_seo_content_versions_score_run_id", ["score_run_id"]),
        ],
    )

    if "seo_generation_runs" not in existing_tables:
        op.create_table(
            "seo_generation_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            *_scope_columns(),
            sa.Column("content_version_id", sa.Integer(), nullable=True),
            sa.Column("provider_name", sa.String(length=64), nullable=True),
            sa.Column("model_name", sa.String(length=128), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'not_started'")),
            sa.Column("request_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("response_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("error_text", sa.Text(), nullable=True),
            *_timestamps(),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["content_version_id"], ["seo_content_versions.id"], ondelete="SET NULL"),
        )
        inspector = inspect(bind)
    _create_indexes(
        inspector,
        "seo_generation_runs",
        [
            ("idx_seo_generation_runs_project_id", ["project_id"]),
            ("idx_seo_generation_runs_category_id", ["category_id"]),
            ("idx_seo_generation_runs_content_version_id", ["content_version_id"]),
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "seo_generation_runs" in existing_tables:
        for index_name in (
            "idx_seo_generation_runs_content_version_id",
            "idx_seo_generation_runs_category_id",
            "idx_seo_generation_runs_project_id",
        ):
            op.drop_index(index_name, table_name="seo_generation_runs")
        op.drop_table("seo_generation_runs")

    if "seo_content_versions" in existing_tables:
        for index_name in (
            "idx_seo_content_versions_score_run_id",
            "idx_seo_content_versions_cluster_profile_version_id",
            "idx_seo_content_versions_nm_id",
            "idx_seo_content_versions_category_id",
            "idx_seo_content_versions_project_id",
        ):
            op.drop_index(index_name, table_name="seo_content_versions")
        op.drop_table("seo_content_versions")

    if "seo_score_explanations" in existing_tables:
        op.drop_index("idx_seo_score_explanations_query_score_id", table_name="seo_score_explanations")
        op.drop_table("seo_score_explanations")

    if "seo_query_scores" in existing_tables:
        for index_name in (
            "idx_seo_query_scores_cluster_id",
            "idx_seo_query_scores_nm_id",
            "idx_seo_query_scores_normalized_query_id",
            "idx_seo_query_scores_category_id",
            "idx_seo_query_scores_project_id",
            "idx_seo_query_scores_score_run_id",
        ):
            op.drop_index(index_name, table_name="seo_query_scores")
        op.drop_table("seo_query_scores")

    if "seo_score_runs" in existing_tables:
        for index_name in (
            "idx_seo_score_runs_category_id",
            "idx_seo_score_runs_project_id",
        ):
            op.drop_index(index_name, table_name="seo_score_runs")
        op.drop_table("seo_score_runs")

    if "seo_cluster_profile_versions" in existing_tables:
        for index_name in (
            "idx_seo_cluster_profile_versions_profile_id",
            "idx_seo_cluster_profile_versions_category_id",
            "idx_seo_cluster_profile_versions_project_id",
        ):
            op.drop_index(index_name, table_name="seo_cluster_profile_versions")
        op.drop_table("seo_cluster_profile_versions")

    if "seo_cluster_profiles" in existing_tables:
        for index_name in (
            "idx_seo_cluster_profiles_cluster_id",
            "idx_seo_cluster_profiles_category_id",
            "idx_seo_cluster_profiles_project_id",
        ):
            op.drop_index(index_name, table_name="seo_cluster_profiles")
        op.drop_table("seo_cluster_profiles")

    if "seo_sku_cluster_assignments" in existing_tables:
        for index_name in (
            "idx_seo_sku_cluster_assignments_nm_id",
            "idx_seo_sku_cluster_assignments_cluster_id",
            "idx_seo_sku_cluster_assignments_run_id",
            "idx_seo_sku_cluster_assignments_category_id",
            "idx_seo_sku_cluster_assignments_project_id",
        ):
            op.drop_index(index_name, table_name="seo_sku_cluster_assignments")
        op.drop_table("seo_sku_cluster_assignments")

    if "seo_sku_clusters" in existing_tables:
        for index_name in (
            "idx_seo_sku_clusters_run_id",
            "idx_seo_sku_clusters_category_id",
            "idx_seo_sku_clusters_project_id",
        ):
            op.drop_index(index_name, table_name="seo_sku_clusters")
        op.drop_table("seo_sku_clusters")

    if "seo_sku_cluster_runs" in existing_tables:
        for index_name in (
            "idx_seo_sku_cluster_runs_category_id",
            "idx_seo_sku_cluster_runs_project_id",
        ):
            op.drop_index(index_name, table_name="seo_sku_cluster_runs")
        op.drop_table("seo_sku_cluster_runs")

    if "seo_query_annotation_versions" in existing_tables:
        for index_name in (
            "idx_seo_query_annotation_versions_annotation_id",
            "idx_seo_query_annotation_versions_category_id",
            "idx_seo_query_annotation_versions_project_id",
        ):
            op.drop_index(index_name, table_name="seo_query_annotation_versions")
        op.drop_table("seo_query_annotation_versions")

    if "seo_query_annotations" in existing_tables:
        for index_name in (
            "idx_seo_query_annotations_normalized_query_id",
            "idx_seo_query_annotations_category_id",
            "idx_seo_query_annotations_project_id",
        ):
            op.drop_index(index_name, table_name="seo_query_annotations")
        op.drop_table("seo_query_annotations")

    if "seo_query_clusters" in existing_tables:
        for index_name in (
            "idx_seo_query_clusters_source_batch_id",
            "idx_seo_query_clusters_category_id",
            "idx_seo_query_clusters_project_id",
        ):
            op.drop_index(index_name, table_name="seo_query_clusters")
        op.drop_table("seo_query_clusters")
