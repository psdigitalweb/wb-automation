"""Add global hypotheses tables for MVP.

Revision ID: add_hypotheses_mvp_001
Revises: add_wb_feedback_snapshots_cols_001
Create Date: 2026-04-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_hypotheses_mvp_001"
down_revision: Union[str, None] = "add_wb_feedback_snapshots_cols_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hypotheses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("domain", sa.String(64), nullable=True),
        sa.Column("hypothesis_type", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_hypotheses_key", "hypotheses", ["key"], unique=True)

    op.create_table(
        "hypothesis_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("hypothesis_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("hypothesis_text", sa.Text(), nullable=True),
        sa.Column("primary_metric_key", sa.String(64), nullable=True),
        sa.Column("guardrails_jsonb", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("action_washout_policy_jsonb", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("requirements_jsonb", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["hypothesis_id"], ["hypotheses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("hypothesis_id", "version", name="uq_hypothesis_versions_hypothesis_version"),
    )
    op.create_index("ix_hypothesis_versions_hypothesis_id", "hypothesis_versions", ["hypothesis_id"])


def downgrade() -> None:
    op.drop_index("ix_hypothesis_versions_hypothesis_id", table_name="hypothesis_versions")
    op.drop_table("hypothesis_versions")
    op.drop_index("ix_hypotheses_key", table_name="hypotheses")
    op.drop_table("hypotheses")
