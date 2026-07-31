"""Add SEO meaning atoms and saved SKU query sets.

Revision ID: 20260422_add_seo_atoms_and_query_sets
Revises: 20260421_add_category_bootstrap_and_axes
Create Date: 2026-04-22
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "20260422_add_seo_atoms_and_query_sets"
down_revision: Union[str, None] = "20260421_add_category_bootstrap_and_axes"
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


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "seo_category_matching_readiness" in tables:
        columns = {column["name"] for column in inspector.get_columns("seo_category_matching_readiness")}
        if "query_atoms_count" not in columns:
            op.add_column(
                "seo_category_matching_readiness",
                sa.Column("query_atoms_count", sa.Integer(), nullable=False, server_default="0"),
            )

    if "seo_meaning_atoms" not in tables:
        op.create_table(
            "seo_meaning_atoms",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("category_id", sa.Integer(), nullable=False, index=True, comment=CATEGORY_SCOPE_COMMENT),
            sa.Column("entity_type", sa.String(length=32), nullable=False, index=True),
            sa.Column("entity_id", sa.Integer(), nullable=True, index=True),
            sa.Column("nm_id", sa.Integer(), nullable=True, index=True),
            sa.Column("schema_version", sa.String(length=64), nullable=False, server_default="meaning_atoms_v0"),
            sa.Column("source_version", sa.String(length=64), nullable=False, server_default="meaning_atoms_v0"),
            sa.Column("model", sa.String(length=128), nullable=True),
            sa.Column("prompt_version", sa.String(length=64), nullable=True),
            sa.Column("input_hash", sa.String(length=128), nullable=False, index=True),
            sa.Column("atoms_payload", _json_type(), nullable=False, server_default=_json_default_object()),
            sa.Column("canonical_summary", sa.Text(), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="ready"),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_seo_meaning_atoms_entity_scope",
            "seo_meaning_atoms",
            ["project_id", "category_id", "entity_type", "entity_id"],
        )
        op.create_index(
            "ix_seo_meaning_atoms_sku_scope",
            "seo_meaning_atoms",
            ["project_id", "category_id", "nm_id", "entity_type"],
        )

    if "seo_sku_query_sets" not in tables:
        op.create_table(
            "seo_sku_query_sets",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("category_id", sa.Integer(), nullable=False, index=True, comment=CATEGORY_SCOPE_COMMENT),
            sa.Column("nm_id", sa.Integer(), nullable=False, index=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("matcher_version", sa.String(length=64), nullable=True),
            sa.Column("atoms_version", sa.String(length=64), nullable=True),
            sa.Column("source_hash", sa.String(length=128), nullable=True, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("project_id", "category_id", "nm_id", "status", name="uq_seo_sku_query_sets_scope_status"),
        )

    if "seo_sku_query_set_items" not in tables:
        op.create_table(
            "seo_sku_query_set_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("query_set_id", sa.Integer(), sa.ForeignKey("seo_sku_query_sets.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("normalized_query_text", sa.Text(), nullable=False),
            sa.Column("display_query", sa.Text(), nullable=False),
            sa.Column("cluster_key", sa.String(length=128), nullable=True),
            sa.Column("bucket", sa.String(length=32), nullable=False),
            sa.Column("score", sa.Numeric(12, 4), nullable=False, server_default="0"),
            sa.Column("ranking_value_used", sa.Numeric(14, 4), nullable=True),
            sa.Column("selection_state", sa.String(length=32), nullable=False, server_default="auto_selected"),
            sa.Column("reasons_payload", _json_type(), nullable=False, server_default=_json_default_object()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("query_set_id", "normalized_query_text", name="uq_seo_sku_query_set_items_set_query"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "seo_sku_query_set_items" in tables:
        op.drop_table("seo_sku_query_set_items")
    if "seo_sku_query_sets" in tables:
        op.drop_table("seo_sku_query_sets")
    if "seo_meaning_atoms" in tables:
        op.drop_index("ix_seo_meaning_atoms_sku_scope", table_name="seo_meaning_atoms")
        op.drop_index("ix_seo_meaning_atoms_entity_scope", table_name="seo_meaning_atoms")
        op.drop_table("seo_meaning_atoms")
    if "seo_category_matching_readiness" in tables:
        columns = {column["name"] for column in inspector.get_columns("seo_category_matching_readiness")}
        if "query_atoms_count" in columns:
            op.drop_column("seo_category_matching_readiness", "query_atoms_count")
