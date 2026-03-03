"""add wb_backfill_range_state table for wb_card_stats_daily backfill resume

Revision ID: add_wb_backfill_range_state_001
Revises: add_wb_analytics_001
Create Date: 2026-02-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_wb_backfill_range_state_001"
down_revision: Union[str, None] = "add_wb_analytics_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wb_backfill_range_state",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("job_code", sa.String(64), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("cursor_date", sa.Date(), nullable=True),
        sa.Column("cursor_nm_offset", sa.Integer(), nullable=True),
        sa.Column("last_run_id", sa.Integer(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("meta_json", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_run_id"], ["ingest_runs.id"], ondelete="SET NULL"),
    )
    op.create_unique_constraint(
        "uq_wb_backfill_range_state_project_job_dates",
        "wb_backfill_range_state",
        ["project_id", "job_code", "date_from", "date_to"],
    )
    op.create_index(
        "idx_wb_backfill_range_state_project_job",
        "wb_backfill_range_state",
        ["project_id", "job_code"],
    )


def downgrade() -> None:
    op.drop_index("idx_wb_backfill_range_state_project_job", table_name="wb_backfill_range_state")
    op.drop_constraint(
        "uq_wb_backfill_range_state_project_job_dates",
        "wb_backfill_range_state",
        type_="unique",
    )
    op.drop_table("wb_backfill_range_state")
