"""add manually collected WB competitor reviews

Revision ID: 20260730_wb_competitor_reviews
Revises: 20260729_wb_review_opinion
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260730_wb_competitor_reviews"
down_revision: Union[str, None] = "20260729_wb_review_opinion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wb_competitor_review_targets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("root_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("category_name", sa.Text(), nullable=True),
        sa.Column("wb_review_rating", sa.Numeric(5, 2), nullable=True),
        sa.Column("wb_feedback_count", sa.Integer(), nullable=True),
        sa.Column("collected_reviews_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text_reviews_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calculated_avg_rating", sa.Numeric(5, 2), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "nm_id", name="uq_wb_competitor_targets_project_nm"),
        sa.CheckConstraint(
            "status IN ('queued','collecting','ready','partial','failed','not_found')",
            name="ck_wb_competitor_targets_status",
        ),
    )
    op.create_index(
        "ix_wb_competitor_targets_project_updated",
        "wb_competitor_review_targets",
        ["project_id", sa.text("updated_at DESC")],
    )

    op.create_table(
        "wb_competitor_reviews",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column("review_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("pros", sa.Text(), nullable=True),
        sa.Column("cons", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["wb_competitor_review_targets.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("target_id", "external_id", name="uq_wb_competitor_reviews_target_external"),
    )
    op.create_index(
        "ix_wb_competitor_reviews_target_created",
        "wb_competitor_reviews",
        ["target_id", sa.text("review_created_at DESC")],
    )

    op.create_table(
        "wb_competitor_review_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("requested_nm_ids", postgresql.JSONB(), nullable=False),
        sa.Column("completed_nm_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("failed_nm_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed')",
            name="ck_wb_competitor_runs_status",
        ),
    )
    op.create_index(
        "ix_wb_competitor_runs_project_created",
        "wb_competitor_review_runs",
        ["project_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "uq_wb_competitor_runs_active",
        "wb_competitor_review_runs",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_wb_competitor_runs_active", table_name="wb_competitor_review_runs")
    op.drop_index("ix_wb_competitor_runs_project_created", table_name="wb_competitor_review_runs")
    op.drop_table("wb_competitor_review_runs")
    op.drop_index("ix_wb_competitor_reviews_target_created", table_name="wb_competitor_reviews")
    op.drop_table("wb_competitor_reviews")
    op.drop_index("ix_wb_competitor_targets_project_updated", table_name="wb_competitor_review_targets")
    op.drop_table("wb_competitor_review_targets")
