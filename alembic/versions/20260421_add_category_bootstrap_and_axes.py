"""Add category bootstrap readiness and meaning axes.

Revision ID: 20260421_add_category_bootstrap_and_axes
Revises: 20260421_add_query_meaning_library_and_embeddings
Create Date: 2026-04-21
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "20260421_add_category_bootstrap_and_axes"
down_revision: Union[str, None] = "20260421_add_query_meaning_library_and_embeddings"
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


def _json_default_object() -> sa.TextClause:
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

    if "seo_category_bootstrap_runs" not in existing_tables:
        op.create_table(
            "seo_category_bootstrap_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False, comment=CATEGORY_SCOPE_COMMENT),
            sa.Column("trigger", sa.String(length=32), nullable=False, server_default=sa.text("'manual'")),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'queued'")),
            sa.Column("current_step", sa.String(length=64), nullable=True),
            sa.Column("step_statuses", json_type, nullable=False, server_default=_json_default_object()),
            sa.Column("input_hash", sa.String(length=128), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        )
        inspector = inspect(bind)

    _create_indexes(
        inspector,
        "seo_category_bootstrap_runs",
        [
            ("idx_seo_category_bootstrap_runs_project_id", ["project_id"]),
            ("idx_seo_category_bootstrap_runs_category_id", ["category_id"]),
            ("idx_seo_category_bootstrap_runs_status", ["status"]),
        ],
    )

    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "seo_category_matching_readiness" not in existing_tables:
        op.create_table(
            "seo_category_matching_readiness",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False, comment=CATEGORY_SCOPE_COMMENT),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'not_started'")),
            sa.Column("latest_run_id", sa.Integer(), nullable=True),
            sa.Column("query_batch_id", sa.Integer(), nullable=True),
            sa.Column("queries_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("clusters_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("query_meanings_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("embeddings_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("category_axes_status", sa.String(length=32), nullable=False, server_default=sa.text("'not_started'")),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["latest_run_id"], ["seo_category_bootstrap_runs.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["query_batch_id"], ["seo_query_batches.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("project_id", "category_id", name="uq_seo_category_matching_readiness_scope"),
        )
        inspector = inspect(bind)

    _create_indexes(
        inspector,
        "seo_category_matching_readiness",
        [
            ("idx_seo_category_matching_readiness_project_id", ["project_id"]),
            ("idx_seo_category_matching_readiness_category_id", ["category_id"]),
            ("idx_seo_category_matching_readiness_latest_run_id", ["latest_run_id"]),
            ("idx_seo_category_matching_readiness_query_batch_id", ["query_batch_id"]),
            ("idx_seo_category_matching_readiness_status", ["status"]),
        ],
    )

    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "seo_category_meaning_axes" not in existing_tables:
        op.create_table(
            "seo_category_meaning_axes",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False, comment=CATEGORY_SCOPE_COMMENT),
            sa.Column("schema_version", sa.String(length=64), nullable=False, server_default=sa.text("'category_meaning_axes_v0'")),
            sa.Column("source", sa.String(length=32), nullable=False, server_default=sa.text("'deterministic'")),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'draft'")),
            sa.Column("evidence_hash", sa.String(length=128), nullable=False),
            sa.Column("axes_payload", json_type, nullable=False, server_default=_json_default_object()),
            sa.Column("canonical_text", sa.Text(), nullable=False),
            sa.Column("llm_model", sa.String(length=128), nullable=True),
            sa.Column("prompt_version", sa.String(length=64), nullable=False, server_default=sa.text("'category_meaning_axes_v0'")),
            sa.Column("input_hash", sa.String(length=128), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "project_id",
                "category_id",
                "schema_version",
                "source",
                name="uq_seo_category_meaning_axes_scope_schema_source",
            ),
        )
        inspector = inspect(bind)

    _create_indexes(
        inspector,
        "seo_category_meaning_axes",
        [
            ("idx_seo_category_meaning_axes_project_id", ["project_id"]),
            ("idx_seo_category_meaning_axes_category_id", ["category_id"]),
            ("idx_seo_category_meaning_axes_status", ["status"]),
            ("idx_seo_category_meaning_axes_source", ["source"]),
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "seo_category_meaning_axes" in existing_tables:
        for index_name in (
            "idx_seo_category_meaning_axes_source",
            "idx_seo_category_meaning_axes_status",
            "idx_seo_category_meaning_axes_category_id",
            "idx_seo_category_meaning_axes_project_id",
        ):
            op.drop_index(index_name, table_name="seo_category_meaning_axes")
        op.drop_table("seo_category_meaning_axes")

    if "seo_category_matching_readiness" in existing_tables:
        for index_name in (
            "idx_seo_category_matching_readiness_status",
            "idx_seo_category_matching_readiness_query_batch_id",
            "idx_seo_category_matching_readiness_latest_run_id",
            "idx_seo_category_matching_readiness_category_id",
            "idx_seo_category_matching_readiness_project_id",
        ):
            op.drop_index(index_name, table_name="seo_category_matching_readiness")
        op.drop_table("seo_category_matching_readiness")

    if "seo_category_bootstrap_runs" in existing_tables:
        for index_name in (
            "idx_seo_category_bootstrap_runs_status",
            "idx_seo_category_bootstrap_runs_category_id",
            "idx_seo_category_bootstrap_runs_project_id",
        ):
            op.drop_index(index_name, table_name="seo_category_bootstrap_runs")
        op.drop_table("seo_category_bootstrap_runs")
