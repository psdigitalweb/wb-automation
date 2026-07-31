"""Add query cluster memberships and enrich current query cluster fields.

Revision ID: 20260414_add_query_cluster_memberships_and_enrich_query_clusters
Revises: 20260414_evolve_seo_query_annotations_for_canonical_pruning
Create Date: 2026-04-14
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "20260414_add_query_cluster_memberships_and_enrich_query_clusters"
down_revision: Union[str, None] = "20260414_evolve_seo_query_annotations_for_canonical_pruning"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CATEGORY_SCOPE_COMMENT = (
    "WB category scope for SEO pipeline (Wildberries subject_id/category scope), "
    "not a foreign key to internal_categories.id."
)


def _create_indexes(inspector: sa.Inspector, table_name: str, specs: list[tuple[str, list[str]]]) -> None:
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    for index_name, columns in specs:
        if index_name not in existing:
            op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "seo_query_clusters" in existing_tables:
        existing_columns = {item["name"] for item in inspector.get_columns("seo_query_clusters")}
        if "top_query_text" not in existing_columns:
            op.add_column("seo_query_clusters", sa.Column("top_query_text", sa.Text(), nullable=True))
        if "head_query_count" not in existing_columns:
            op.add_column(
                "seo_query_clusters",
                sa.Column("head_query_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            )
        if "mid_query_count" not in existing_columns:
            op.add_column(
                "seo_query_clusters",
                sa.Column("mid_query_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            )
        if "tail_query_count" not in existing_columns:
            op.add_column(
                "seo_query_clusters",
                sa.Column("tail_query_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            )

    if "seo_query_cluster_memberships" not in existing_tables:
        op.create_table(
            "seo_query_cluster_memberships",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False, comment=CATEGORY_SCOPE_COMMENT),
            sa.Column("cluster_id", sa.Integer(), nullable=False),
            sa.Column("annotation_id", sa.Integer(), nullable=False),
            sa.Column("normalized_query_text", sa.Text(), nullable=False),
            sa.Column("query_type", sa.String(length=32), nullable=False, server_default=sa.text("'tail'")),
            sa.Column("ranking_value_used", sa.Numeric(14, 4), nullable=False, server_default=sa.text("0")),
            sa.Column(
                "membership_reason_code",
                sa.String(length=64),
                nullable=False,
                server_default=sa.text("'singleton_fallback'"),
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["cluster_id"], ["seo_query_clusters.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["annotation_id"], ["seo_query_annotations.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "project_id",
                "category_id",
                "normalized_query_text",
                name="uq_seo_query_cluster_memberships_scope_query",
            ),
        )
        inspector = inspect(bind)

    _create_indexes(
        inspector,
        "seo_query_cluster_memberships",
        [
            ("idx_seo_query_cluster_memberships_project_id", ["project_id"]),
            ("idx_seo_query_cluster_memberships_category_id", ["category_id"]),
            ("idx_seo_query_cluster_memberships_cluster_id", ["cluster_id"]),
            ("idx_seo_query_cluster_memberships_annotation_id", ["annotation_id"]),
            ("idx_seo_query_cluster_memberships_normalized_query_text", ["normalized_query_text"]),
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "seo_query_cluster_memberships" in existing_tables:
        for index_name in (
            "idx_seo_query_cluster_memberships_normalized_query_text",
            "idx_seo_query_cluster_memberships_annotation_id",
            "idx_seo_query_cluster_memberships_cluster_id",
            "idx_seo_query_cluster_memberships_category_id",
            "idx_seo_query_cluster_memberships_project_id",
        ):
            op.drop_index(index_name, table_name="seo_query_cluster_memberships")
        op.drop_table("seo_query_cluster_memberships")

    if "seo_query_clusters" in existing_tables:
        existing_columns = {item["name"] for item in inspector.get_columns("seo_query_clusters")}
        for column_name in ("tail_query_count", "mid_query_count", "head_query_count", "top_query_text"):
            if column_name in existing_columns:
                op.drop_column("seo_query_clusters", column_name)
