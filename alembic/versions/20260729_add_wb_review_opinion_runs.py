"""add manual WB review opinion analysis runs

Revision ID: 20260729_wb_review_opinion
Revises: 20260727_wb_content_history
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260729_wb_review_opinion"
down_revision: Union[str, None] = "20260727_wb_content_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wb_review_opinion_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False, server_default="all_time"),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("reasoning_effort", sa.String(16), nullable=False),
        sa.Column("reviews_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reviews_with_text", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reviews_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_json", postgresql.JSONB(), nullable=True),
        sa.Column("validation_json", postgresql.JSONB(), nullable=True),
        sa.Column("usage_json", postgresql.JSONB(), nullable=True),
        sa.Column("provider_request_id", sa.String(128), nullable=True),
        sa.Column("raw_output_text", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'ready', 'failed')",
            name="ck_wb_review_opinion_runs_status",
        ),
        sa.CheckConstraint(
            "scope_type IN ('all_time')",
            name="ck_wb_review_opinion_runs_scope",
        ),
        sa.CheckConstraint(
            "reviews_total >= 0 AND reviews_with_text >= 0 AND reviews_sent >= 0",
            name="ck_wb_review_opinion_runs_review_counts",
        ),
    )
    op.create_index(
        "ix_wb_review_opinion_runs_project_nm_created",
        "wb_review_opinion_runs",
        ["project_id", "nm_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_wb_review_opinion_runs_input",
        "wb_review_opinion_runs",
        ["project_id", "nm_id", "input_hash", "prompt_version", "model"],
    )
    op.create_index(
        "uq_wb_review_opinion_runs_active",
        "wb_review_opinion_runs",
        ["project_id", "nm_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_wb_review_opinion_runs_active", table_name="wb_review_opinion_runs")
    op.drop_index("ix_wb_review_opinion_runs_input", table_name="wb_review_opinion_runs")
    op.drop_index(
        "ix_wb_review_opinion_runs_project_nm_created",
        table_name="wb_review_opinion_runs",
    )
    op.drop_table("wb_review_opinion_runs")
