"""fix wb_finances: add line_id and fix report grouping

Revision ID: fix_wb_finances_grouping_001
Revises: add_wb_finance_reports_001
Create Date: 2026-01-21 18:00:00.000000

Fixes:
- Add line_id column to wb_finance_report_lines (stores rrd_id from API)
- Change unique constraint from (project_id, report_id, line_uid) to (project_id, report_id, line_id)
- Allows proper grouping: report_id = realizationreport_id (report header), line_id = rrd_id (line within report)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fix_wb_finances_grouping_001"
down_revision: Union[str, None] = "add_wb_finance_reports_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add line_id column to wb_finance_report_lines
    # line_id will store rrd_id from WB API (unique line identifier within report)
    op.add_column(
        "wb_finance_report_lines",
        sa.Column("line_id", sa.BigInteger(), nullable=True),  # Nullable for migration, will be populated
    )

    # Drop old unique constraint
    op.drop_index(
        "uq_wb_finance_report_lines_project_report_line",
        table_name="wb_finance_report_lines",
    )

    # Create new unique constraint with line_id instead of line_uid
    op.create_index(
        "uq_wb_finance_report_lines_project_report_line_id",
        "wb_finance_report_lines",
        ["project_id", "report_id", "line_id"],
        unique=True,
    )

    # After migration, old records will have line_id=NULL
    # They should be re-ingested to get proper line_id values
    # For now, we allow NULL temporarily, but new ingestion will populate it


def downgrade() -> None:
    # Restore old unique constraint
    op.drop_index(
        "uq_wb_finance_report_lines_project_report_line_id",
        table_name="wb_finance_report_lines",
    )

    op.create_index(
        "uq_wb_finance_report_lines_project_report_line",
        "wb_finance_report_lines",
        ["project_id", "report_id", "line_uid"],
        unique=True,
    )

    # Remove line_id column
    op.drop_column("wb_finance_report_lines", "line_id")
