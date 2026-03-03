"""add is_archived, source_endpoint, last_seen_at to wb_feedback_snapshots

Revision ID: add_wb_feedback_snapshots_cols_001
Revises: add_wb_backfill_range_state_001
Create Date: 2026-03-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_wb_feedback_snapshots_cols_001"
down_revision: Union[str, None] = "add_wb_backfill_range_state_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "wb_feedback_snapshots",
        sa.Column("is_archived", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "wb_feedback_snapshots",
        sa.Column("source_endpoint", sa.Text(), nullable=True),
    )
    op.add_column(
        "wb_feedback_snapshots",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("wb_feedback_snapshots", "last_seen_at")
    op.drop_column("wb_feedback_snapshots", "source_endpoint")
    op.drop_column("wb_feedback_snapshots", "is_archived")
