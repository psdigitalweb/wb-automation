"""add wb_communications tables (feedbacks, questions, watermarks, daily aggregates)

Revision ID: add_wb_communications_001
Revises: add_wb_finance_rr_dt_idx
Create Date: 2026-02-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_wb_communications_001"
down_revision: Union[str, None] = "add_wb_finance_rr_dt_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wb_communications_watermarks",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("last_date_to", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("project_id", "entity_type"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "wb_feedback_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ingest_run_id", sa.BigInteger(), nullable=True),
        sa.Column("product_valuation", sa.SmallInteger(), nullable=True),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_answered", sa.Boolean(), nullable=True),
        sa.Column("has_media", sa.Boolean(), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingest_run_id"], ["ingest_runs.id"], ondelete="SET NULL"),
    )
    op.create_unique_constraint(
        "uq_wb_feedback_snapshots_project_external",
        "wb_feedback_snapshots",
        ["project_id", "external_id"],
    )
    op.create_index("ix_wb_feedback_snapshots_project_snapshot", "wb_feedback_snapshots", ["project_id", "snapshot_at"])
    op.create_index("ix_wb_feedback_snapshots_project_nm_snapshot", "wb_feedback_snapshots", ["project_id", "nm_id", "snapshot_at"])
    op.create_index("ix_wb_feedback_snapshots_ingest_run_id", "wb_feedback_snapshots", ["ingest_run_id"])

    op.create_table(
        "wb_question_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ingest_run_id", sa.BigInteger(), nullable=True),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_answered", sa.Boolean(), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingest_run_id"], ["ingest_runs.id"], ondelete="SET NULL"),
    )
    op.create_unique_constraint(
        "uq_wb_question_snapshots_project_external",
        "wb_question_snapshots",
        ["project_id", "external_id"],
    )
    op.create_index("ix_wb_question_snapshots_project_snapshot", "wb_question_snapshots", ["project_id", "snapshot_at"])
    op.create_index("ix_wb_question_snapshots_project_nm_snapshot", "wb_question_snapshots", ["project_id", "nm_id", "snapshot_at"])
    op.create_index("ix_wb_question_snapshots_ingest_run_id", "wb_question_snapshots", ["ingest_run_id"])

    op.create_table(
        "wb_product_feedback_daily",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_rating", sa.Numeric(5, 2), nullable=True),
        sa.Column("cnt_1_2", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cnt_with_media", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cnt_unanswered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ingest_run_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("project_id", "snapshot_date", "nm_id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingest_run_id"], ["ingest_runs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_wb_product_feedback_daily_project_date", "wb_product_feedback_daily", ["project_id", "snapshot_date"])

    op.create_table(
        "wb_product_questions_daily",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cnt_unanswered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ingest_run_id", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("project_id", "snapshot_date", "nm_id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingest_run_id"], ["ingest_runs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_wb_product_questions_daily_project_date", "wb_product_questions_daily", ["project_id", "snapshot_date"])


def downgrade() -> None:
    op.drop_table("wb_product_questions_daily")
    op.drop_table("wb_product_feedback_daily")
    op.drop_table("wb_question_snapshots")
    op.drop_table("wb_feedback_snapshots")
    op.drop_table("wb_communications_watermarks")
