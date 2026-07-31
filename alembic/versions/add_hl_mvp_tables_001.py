"""Add Hypothesis Lab MVP experiment tables.

Revision ID: add_hl_mvp_tables_001
Revises: add_hypotheses_mvp_001
Create Date: 2026-04-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_hl_mvp_tables_001"
down_revision: Union[str, None] = "add_hypotheses_mvp_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "hl_mvp_experiments",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("hypothesis_id", sa.BigInteger(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("change_type", sa.String(32), nullable=False),
        sa.Column("change_note", sa.Text(), nullable=False),
        sa.Column("metric", sa.String(32), nullable=False),
        sa.Column("control_mode", sa.String(16), nullable=False, server_default="none"),
        sa.Column("controls_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hypothesis_id"], ["hypotheses.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_hl_mvp_experiments_project_id", "hl_mvp_experiments", ["project_id"])
    op.create_index("ix_hl_mvp_experiments_status", "hl_mvp_experiments", ["status"])
    op.create_index("ix_hl_mvp_experiments_nm_id", "hl_mvp_experiments", ["project_id", "nm_id"])

    op.create_table(
        "hl_mvp_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("experiment_id", sa.BigInteger(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("change_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.ForeignKeyConstraint(["experiment_id"], ["hl_mvp_experiments.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_hl_mvp_runs_experiment_id", "hl_mvp_runs", ["experiment_id"])

    op.create_table(
        "hl_mvp_results",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("control_mode", sa.String(16), nullable=False),
        sa.Column("did_effect", sa.Numeric(20, 6), nullable=True),
        sa.Column("p_value", sa.Numeric(10, 6), nullable=True),
        sa.Column("ci_low", sa.Numeric(20, 6), nullable=True),
        sa.Column("ci_high", sa.Numeric(20, 6), nullable=True),
        sa.Column("pretrend_pass", sa.Boolean(), nullable=True),
        sa.Column("before_after_delta", sa.Numeric(20, 6), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["hl_mvp_runs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_hl_mvp_results_run_id", "hl_mvp_results", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_hl_mvp_results_run_id", table_name="hl_mvp_results")
    op.drop_table("hl_mvp_results")
    op.drop_index("ix_hl_mvp_runs_experiment_id", table_name="hl_mvp_runs")
    op.drop_table("hl_mvp_runs")
    op.drop_index("ix_hl_mvp_experiments_nm_id", table_name="hl_mvp_experiments")
    op.drop_index("ix_hl_mvp_experiments_status", table_name="hl_mvp_experiments")
    op.drop_index("ix_hl_mvp_experiments_project_id", table_name="hl_mvp_experiments")
    op.drop_table("hl_mvp_experiments")
