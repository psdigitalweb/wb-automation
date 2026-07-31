"""add competitor review analysis runs

Revision ID: 20260731_wb_competitor_analysis
Revises: 20260730_wb_competitor_reviews
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260731_wb_competitor_analysis"
down_revision: Union[str, None] = "20260730_wb_competitor_reviews"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wb_competitor_review_analyses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("pipeline_version", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("reviews_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_last_collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimated_cost_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("max_cost_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("actual_cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("result_json", postgresql.JSONB(), nullable=True),
        sa.Column("validation_json", postgresql.JSONB(), nullable=True),
        sa.Column("usage_json", postgresql.JSONB(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["target_id"],
            ["wb_competitor_review_targets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "status IN ('queued','running','ready','failed')",
            name="ck_wb_competitor_analysis_status",
        ),
        sa.CheckConstraint(
            "reviews_sent >= 0 AND estimated_cost_usd >= 0 AND max_cost_usd > 0",
            name="ck_wb_competitor_analysis_limits",
        ),
    )
    op.create_index(
        "ix_wb_competitor_analysis_target_created",
        "wb_competitor_review_analyses",
        ["target_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "uq_wb_competitor_analysis_active",
        "wb_competitor_review_analyses",
        ["target_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_wb_competitor_analysis_active",
        table_name="wb_competitor_review_analyses",
    )
    op.drop_index(
        "ix_wb_competitor_analysis_target_created",
        table_name="wb_competitor_review_analyses",
    )
    op.drop_table("wb_competitor_review_analyses")
