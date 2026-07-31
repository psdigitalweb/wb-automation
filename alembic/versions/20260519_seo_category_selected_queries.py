"""Add operator selected category queries.

Revision ID: 20260519_seo_category_selected_queries
Revises: 20260424_2200_seo_category_profile_derive_runs
Create Date: 2026-05-19
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "20260519_seo_category_selected_queries"
down_revision: Union[str, None] = "20260424_2200_seo_category_profile_derive_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CATEGORY_SCOPE_COMMENT = (
    "WB category scope for SEO pipeline (Wildberries subject_id/category scope), "
    "not a foreign key to internal_categories.id."
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "seo_category_selected_queries" in tables:
        return

    op.create_table(
        "seo_category_selected_queries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("category_id", sa.Integer(), nullable=False, index=True, comment=CATEGORY_SCOPE_COMMENT),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "category_id", "query_text", name="uq_seo_category_selected_queries_scope_query"),
    )
    op.create_index(
        "ix_seo_category_selected_queries_scope_order",
        "seo_category_selected_queries",
        ["project_id", "category_id", "sort_order"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "seo_category_selected_queries" not in tables:
        return
    op.drop_index("ix_seo_category_selected_queries_scope_order", table_name="seo_category_selected_queries")
    op.drop_table("seo_category_selected_queries")
