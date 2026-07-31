"""Add SKU meaning annotation tables.

Revision ID: 20260421_add_sku_meaning_annotation_tables
Revises: 20260414_add_query_cluster_memberships_and_enrich_query_clusters
Create Date: 2026-04-21
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


revision: str = "20260421_add_sku_meaning_annotation_tables"
down_revision: Union[str, None] = "20260414_add_query_cluster_memberships_and_enrich_query_clusters"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CATEGORY_SCOPE_COMMENT = (
    "WB category scope for SEO pipeline (Wildberries subject_id/category scope), "
    "not a foreign key to internal_categories.id."
)


def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB()
    return sa.JSON()


def _json_default() -> sa.TextClause:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.text("'{}'::jsonb")
    return sa.text("'{}'")


def _create_indexes(inspector: sa.Inspector, table_name: str, specs: list[tuple[str, list[str]]]) -> None:
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    for index_name, columns in specs:
        if index_name not in existing:
            op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    json_type = _json_type()
    json_default = _json_default()

    if "seo_sku_meaning_annotations" not in existing_tables:
        op.create_table(
            "seo_sku_meaning_annotations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False, comment=CATEGORY_SCOPE_COMMENT),
            sa.Column("nm_id", sa.Integer(), nullable=False),
            sa.Column("schema_version", sa.String(length=64), nullable=False, server_default=sa.text("'sku_meaning_v0'")),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'draft'")),
            sa.Column("meaning_payload", json_type, nullable=False, server_default=json_default),
            sa.Column("reviewer", sa.String(length=128), nullable=True),
            sa.Column("evidence_hash", sa.String(length=128), nullable=False),
            sa.Column("source_metadata", json_type, nullable=False, server_default=json_default),
            sa.Column("draft_model", sa.String(length=128), nullable=True),
            sa.Column("draft_prompt_version", sa.String(length=64), nullable=True),
            sa.Column("draft_artifact_path", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "project_id",
                "nm_id",
                "schema_version",
                name="uq_seo_sku_meaning_annotations_scope_schema",
            ),
        )
        inspector = inspect(bind)

    _create_indexes(
        inspector,
        "seo_sku_meaning_annotations",
        [
            ("idx_seo_sku_meaning_annotations_project_id", ["project_id"]),
            ("idx_seo_sku_meaning_annotations_category_id", ["category_id"]),
            ("idx_seo_sku_meaning_annotations_nm_id", ["nm_id"]),
            ("idx_seo_sku_meaning_annotations_status", ["status"]),
        ],
    )

    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "seo_sku_query_judgments" not in existing_tables:
        op.create_table(
            "seo_sku_query_judgments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False, comment=CATEGORY_SCOPE_COMMENT),
            sa.Column("annotation_id", sa.Integer(), nullable=False),
            sa.Column("nm_id", sa.Integer(), nullable=False),
            sa.Column("query_text", sa.Text(), nullable=False),
            sa.Column("normalized_query_text", sa.Text(), nullable=False),
            sa.Column("query_id", sa.Integer(), nullable=True),
            sa.Column("cluster_id", sa.Integer(), nullable=True),
            sa.Column("cluster_key", sa.String(length=128), nullable=True),
            sa.Column("label", sa.String(length=32), nullable=False),
            sa.Column("rationale", sa.Text(), nullable=True),
            sa.Column("reviewer", sa.String(length=128), nullable=True),
            sa.Column("matcher_version", sa.String(length=64), nullable=True),
            sa.Column("source", sa.String(length=64), nullable=False, server_default=sa.text("'manual'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["annotation_id"], ["seo_sku_meaning_annotations.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["query_id"], ["seo_query_annotations.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["cluster_id"], ["seo_query_clusters.id"], ondelete="SET NULL"),
            sa.UniqueConstraint(
                "annotation_id",
                "normalized_query_text",
                name="uq_seo_sku_query_judgments_annotation_query",
            ),
        )
        inspector = inspect(bind)

    _create_indexes(
        inspector,
        "seo_sku_query_judgments",
        [
            ("idx_seo_sku_query_judgments_project_id", ["project_id"]),
            ("idx_seo_sku_query_judgments_category_id", ["category_id"]),
            ("idx_seo_sku_query_judgments_annotation_id", ["annotation_id"]),
            ("idx_seo_sku_query_judgments_nm_id", ["nm_id"]),
            ("idx_seo_sku_query_judgments_normalized_query_text", ["normalized_query_text"]),
            ("idx_seo_sku_query_judgments_query_id", ["query_id"]),
            ("idx_seo_sku_query_judgments_cluster_id", ["cluster_id"]),
        ],
    )

    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "seo_sku_meaning_audit_events" not in existing_tables:
        op.create_table(
            "seo_sku_meaning_audit_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False, comment=CATEGORY_SCOPE_COMMENT),
            sa.Column("annotation_id", sa.Integer(), nullable=True),
            sa.Column("nm_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("actor", sa.String(length=128), nullable=True),
            sa.Column("event_payload", json_type, nullable=False, server_default=json_default),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["annotation_id"], ["seo_sku_meaning_annotations.id"], ondelete="SET NULL"),
        )
        inspector = inspect(bind)

    _create_indexes(
        inspector,
        "seo_sku_meaning_audit_events",
        [
            ("idx_seo_sku_meaning_audit_events_project_id", ["project_id"]),
            ("idx_seo_sku_meaning_audit_events_category_id", ["category_id"]),
            ("idx_seo_sku_meaning_audit_events_annotation_id", ["annotation_id"]),
            ("idx_seo_sku_meaning_audit_events_nm_id", ["nm_id"]),
            ("idx_seo_sku_meaning_audit_events_event_type", ["event_type"]),
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "seo_sku_meaning_audit_events" in existing_tables:
        for index_name in (
            "idx_seo_sku_meaning_audit_events_event_type",
            "idx_seo_sku_meaning_audit_events_nm_id",
            "idx_seo_sku_meaning_audit_events_annotation_id",
            "idx_seo_sku_meaning_audit_events_category_id",
            "idx_seo_sku_meaning_audit_events_project_id",
        ):
            op.drop_index(index_name, table_name="seo_sku_meaning_audit_events")
        op.drop_table("seo_sku_meaning_audit_events")

    if "seo_sku_query_judgments" in existing_tables:
        for index_name in (
            "idx_seo_sku_query_judgments_cluster_id",
            "idx_seo_sku_query_judgments_query_id",
            "idx_seo_sku_query_judgments_normalized_query_text",
            "idx_seo_sku_query_judgments_nm_id",
            "idx_seo_sku_query_judgments_annotation_id",
            "idx_seo_sku_query_judgments_category_id",
            "idx_seo_sku_query_judgments_project_id",
        ):
            op.drop_index(index_name, table_name="seo_sku_query_judgments")
        op.drop_table("seo_sku_query_judgments")

    if "seo_sku_meaning_annotations" in existing_tables:
        for index_name in (
            "idx_seo_sku_meaning_annotations_status",
            "idx_seo_sku_meaning_annotations_nm_id",
            "idx_seo_sku_meaning_annotations_category_id",
            "idx_seo_sku_meaning_annotations_project_id",
        ):
            op.drop_index(index_name, table_name="seo_sku_meaning_annotations")
        op.drop_table("seo_sku_meaning_annotations")
