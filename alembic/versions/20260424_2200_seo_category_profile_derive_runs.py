"""Add seo_category_profile_derive_runs table for Phase 0 Step 3.

Revision ID: 20260424_2200_seo_category_profile_derive_runs
Revises: 20260424_seo_iter2_category_profile_eval_promotion
Create Date: 2026-04-24
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "20260424_2200_seo_category_profile_derive_runs"
down_revision: Union[str, None] = "20260424_seo_iter2_category_profile_eval_promotion"
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

    if "seo_category_profile_derive_runs" in tables:
        return

    op.create_table(
        "seo_category_profile_derive_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "category_id",
            sa.Integer(),
            nullable=False,
            index=True,
            comment=CATEGORY_SCOPE_COMMENT,
        ),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("method", sa.String(length=64), nullable=False, server_default="skeleton_v0"),
        sa.Column("llm_model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("evidence_hash", sa.String(length=128), nullable=True),
        sa.Column("profile_version", sa.String(length=64), nullable=True),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("seo_category_profiles.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("self_check_json", _json_type(), nullable=False, server_default=_json_default_object()),
        sa.Column("eval_baseline_json", _json_type(), nullable=True),
        sa.Column("eval_new_json", _json_type(), nullable=True),
        sa.Column("diff_summary", _json_type(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("run_id", name="uq_seo_category_profile_derive_runs_run_id"),
    )
    op.create_index(
        "ix_seo_category_profile_derive_runs_scope",
        "seo_category_profile_derive_runs",
        ["project_id", "category_id", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "seo_category_profile_derive_runs" not in tables:
        return
    op.drop_index("ix_seo_category_profile_derive_runs_scope", table_name="seo_category_profile_derive_runs")
    op.drop_table("seo_category_profile_derive_runs")
