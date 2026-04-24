"""Add query meaning library and meaning embeddings.

Revision ID: 20260421_add_query_meaning_library_and_embeddings
Revises: 20260421_add_sku_meaning_annotation_tables
Create Date: 2026-04-21
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "20260421_add_query_meaning_library_and_embeddings"
down_revision: Union[str, None] = "20260421_add_sku_meaning_annotation_tables"
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


def _json_default_array() -> sa.TextClause:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.text("'[]'::jsonb")
    return sa.text("'[]'")


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

    if "seo_query_meanings" not in existing_tables:
        op.create_table(
            "seo_query_meanings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False, comment=CATEGORY_SCOPE_COMMENT),
            sa.Column("cluster_id", sa.Integer(), nullable=True),
            sa.Column("cluster_key", sa.String(length=128), nullable=False),
            sa.Column("schema_version", sa.String(length=64), nullable=False, server_default=sa.text("'query_meaning_v0'")),
            sa.Column("source_query_examples", json_type, nullable=False, server_default=_json_default_array()),
            sa.Column("meaning_payload", json_type, nullable=False, server_default=_json_default_object()),
            sa.Column("canonical_text", sa.Text(), nullable=False),
            sa.Column("genericness", sa.String(length=32), nullable=False, server_default=sa.text("'specific'")),
            sa.Column("constraints", json_type, nullable=False, server_default=_json_default_array()),
            sa.Column("conflicts_if_missing", json_type, nullable=False, server_default=_json_default_array()),
            sa.Column("llm_model", sa.String(length=128), nullable=True),
            sa.Column("prompt_version", sa.String(length=64), nullable=False, server_default=sa.text("'query_meaning_library_v0'")),
            sa.Column("input_hash", sa.String(length=128), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'draft'")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["cluster_id"], ["seo_query_clusters.id"], ondelete="SET NULL"),
            sa.UniqueConstraint(
                "project_id",
                "category_id",
                "cluster_key",
                "schema_version",
                name="uq_seo_query_meanings_scope_cluster_schema",
            ),
        )
        inspector = inspect(bind)

    _create_indexes(
        inspector,
        "seo_query_meanings",
        [
            ("idx_seo_query_meanings_project_id", ["project_id"]),
            ("idx_seo_query_meanings_category_id", ["category_id"]),
            ("idx_seo_query_meanings_cluster_id", ["cluster_id"]),
            ("idx_seo_query_meanings_status", ["status"]),
            ("idx_seo_query_meanings_genericness", ["genericness"]),
        ],
    )

    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "seo_meaning_embeddings" not in existing_tables:
        op.create_table(
            "seo_meaning_embeddings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("category_id", sa.Integer(), nullable=False, comment=CATEGORY_SCOPE_COMMENT),
            sa.Column("entity_type", sa.String(length=32), nullable=False),
            sa.Column("entity_id", sa.Integer(), nullable=False),
            sa.Column("model", sa.String(length=128), nullable=False),
            sa.Column("input_hash", sa.String(length=128), nullable=False),
            sa.Column("embedding", json_type, nullable=False, server_default=_json_default_array()),
            sa.Column("canonical_text", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "entity_type",
                "entity_id",
                "model",
                "input_hash",
                name="uq_seo_meaning_embeddings_entity_model_hash",
            ),
        )
        inspector = inspect(bind)

    _create_indexes(
        inspector,
        "seo_meaning_embeddings",
        [
            ("idx_seo_meaning_embeddings_project_id", ["project_id"]),
            ("idx_seo_meaning_embeddings_category_id", ["category_id"]),
            ("idx_seo_meaning_embeddings_entity_type", ["entity_type"]),
            ("idx_seo_meaning_embeddings_entity_id", ["entity_id"]),
            ("idx_seo_meaning_embeddings_input_hash", ["input_hash"]),
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "seo_meaning_embeddings" in existing_tables:
        for index_name in (
            "idx_seo_meaning_embeddings_input_hash",
            "idx_seo_meaning_embeddings_entity_id",
            "idx_seo_meaning_embeddings_entity_type",
            "idx_seo_meaning_embeddings_category_id",
            "idx_seo_meaning_embeddings_project_id",
        ):
            op.drop_index(index_name, table_name="seo_meaning_embeddings")
        op.drop_table("seo_meaning_embeddings")

    if "seo_query_meanings" in existing_tables:
        for index_name in (
            "idx_seo_query_meanings_genericness",
            "idx_seo_query_meanings_status",
            "idx_seo_query_meanings_cluster_id",
            "idx_seo_query_meanings_category_id",
            "idx_seo_query_meanings_project_id",
        ):
            op.drop_index(index_name, table_name="seo_query_meanings")
        op.drop_table("seo_query_meanings")
