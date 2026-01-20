"""add wb_finance_reports and wb_finance_report_lines tables

Revision ID: add_wb_finance_reports_001
Revises: 7f8e9a0b1c2d
Create Date: 2026-01-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_wb_finance_reports_001"
down_revision: Union[str, None] = "7f8e9a0b1c2d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Table for report headers (for list view)
    op.create_table(
        "wb_finance_reports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("marketplace_code", sa.Text(), nullable=False, server_default="wildberries"),
        sa.Column("report_id", sa.BigInteger(), nullable=False),  # Main report identifier from API
        sa.Column("period_from", sa.Date(), nullable=True),
        sa.Column("period_to", sa.Date(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("total_amount", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("rows_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # Foreign key to projects
    op.create_foreign_key(
        "fk_wb_finance_reports_project_id",
        "wb_finance_reports",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Unique constraint: one report per project
    op.create_index(
        "uq_wb_finance_reports_project_report",
        "wb_finance_reports",
        ["project_id", "marketplace_code", "report_id"],
        unique=True,
    )

    # Index for listing reports by project
    op.create_index(
        "ix_wb_finance_reports_project_last_seen",
        "wb_finance_reports",
        ["project_id", sa.text("last_seen_at DESC")],
        unique=False,
    )

    # Table for report lines (raw lines from API)
    op.create_table(
        "wb_finance_report_lines",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("report_id", sa.BigInteger(), nullable=False),  # Same report_id as in wb_finance_reports
        sa.Column("line_uid", sa.Text(), nullable=False),  # Unique identifier for line (hash or API id)
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # Foreign keys
    op.create_foreign_key(
        "fk_wb_finance_report_lines_project_id",
        "wb_finance_report_lines",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Unique constraint: one line per project+report+line_uid
    op.create_index(
        "uq_wb_finance_report_lines_project_report_line",
        "wb_finance_report_lines",
        ["project_id", "report_id", "line_uid"],
        unique=True,
    )

    # Index for fetching lines by report
    op.create_index(
        "ix_wb_finance_report_lines_project_report",
        "wb_finance_report_lines",
        ["project_id", "report_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_wb_finance_report_lines_project_report", table_name="wb_finance_report_lines")
    op.drop_index("uq_wb_finance_report_lines_project_report_line", table_name="wb_finance_report_lines")
    op.drop_table("wb_finance_report_lines")
    
    op.drop_index("ix_wb_finance_reports_project_last_seen", table_name="wb_finance_reports")
    op.drop_index("uq_wb_finance_reports_project_report", table_name="wb_finance_reports")
    op.drop_table("wb_finance_reports")
