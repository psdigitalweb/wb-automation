"""Add SEO query ingestion tables.

Revision ID: 20260404_add_seo_query_ingestion_tables
Revises: add_wb_search_report_mvp_001
Create Date: 2026-04-04
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "20260404_add_seo_query_ingestion_tables"
down_revision: Union[str, None] = "add_wb_search_report_mvp_001"
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


def _create_indexes(inspector: sa.Inspector, table_name: str, specs: list[tuple[str, list[str]]]) -> None:
    existing = {item["name"] for item in inspector.get_indexes(table_name)}
    for index_name, columns in specs:
        if index_name not in existing:
            op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "seo_query_batches" not in existing_tables:
        op.create_table(
            "seo_query_batches",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False, comment=CATEGORY_SCOPE_COMMENT),
            sa.Column("source_type", sa.String(length=32), nullable=False, server_default=sa.text("'csv'")),
            sa.Column("source_path", sa.Text(), nullable=True),
            sa.Column("original_filename", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'pending'")),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("normalized_row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("deduplicated_row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            *_timestamps(),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        )
        inspector = inspect(bind)
    _create_indexes(
        inspector,
        "seo_query_batches",
        [
            ("idx_seo_query_batches_project_id", ["project_id"]),
            ("idx_seo_query_batches_category_id", ["category_id"]),
        ],
    )

    if "seo_queries_raw" not in existing_tables:
        op.create_table(
            "seo_queries_raw",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("batch_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False, comment=CATEGORY_SCOPE_COMMENT),
            sa.Column("row_number", sa.Integer(), nullable=False),
            sa.Column("raw_query", sa.Text(), nullable=False),
            sa.Column("raw_frequency", sa.Numeric(14, 4), nullable=False, server_default=sa.text("1")),
            sa.Column("source_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["batch_id"], ["seo_query_batches.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("batch_id", "row_number", name="uq_seo_queries_raw_batch_row_number"),
        )
        inspector = inspect(bind)
    _create_indexes(
        inspector,
        "seo_queries_raw",
        [
            ("idx_seo_queries_raw_batch_id", ["batch_id"]),
            ("idx_seo_queries_raw_project_id", ["project_id"]),
            ("idx_seo_queries_raw_category_id", ["category_id"]),
        ],
    )

    if "seo_queries_normalized" not in existing_tables:
        op.create_table(
            "seo_queries_normalized",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("batch_id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False, comment=CATEGORY_SCOPE_COMMENT),
            sa.Column("normalized_query", sa.Text(), nullable=False),
            sa.Column("display_query", sa.Text(), nullable=False),
            sa.Column("normalization_version", sa.String(length=32), nullable=False, server_default=sa.text("'v1_minimal'")),
            sa.Column("raw_row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("frequency_total", sa.Numeric(14, 4), nullable=False, server_default=sa.text("0")),
            sa.Column("sample_source_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            *_timestamps(),
            sa.ForeignKeyConstraint(["batch_id"], ["seo_query_batches.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("batch_id", "normalized_query", name="uq_seo_queries_normalized_batch_query"),
        )
        inspector = inspect(bind)
    _create_indexes(
        inspector,
        "seo_queries_normalized",
        [
            ("idx_seo_queries_normalized_batch_id", ["batch_id"]),
            ("idx_seo_queries_normalized_project_id", ["project_id"]),
            ("idx_seo_queries_normalized_category_id", ["category_id"]),
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "seo_queries_normalized" in existing_tables:
        for index_name in (
            "idx_seo_queries_normalized_category_id",
            "idx_seo_queries_normalized_project_id",
            "idx_seo_queries_normalized_batch_id",
        ):
            op.drop_index(index_name, table_name="seo_queries_normalized")
        op.drop_table("seo_queries_normalized")

    if "seo_queries_raw" in existing_tables:
        for index_name in (
            "idx_seo_queries_raw_category_id",
            "idx_seo_queries_raw_project_id",
            "idx_seo_queries_raw_batch_id",
        ):
            op.drop_index(index_name, table_name="seo_queries_raw")
        op.drop_table("seo_queries_raw")

    if "seo_query_batches" in existing_tables:
        for index_name in (
            "idx_seo_query_batches_category_id",
            "idx_seo_query_batches_project_id",
        ):
            op.drop_index(index_name, table_name="seo_query_batches")
        op.drop_table("seo_query_batches")
