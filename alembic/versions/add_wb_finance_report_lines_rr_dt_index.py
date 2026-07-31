"""add rr_dt expression index to wb_finance_report_lines

Revision ID: add_wb_finance_rr_dt_idx
Revises: d112ea543439
Create Date: 2026-02-13

Index for period-mode Unit PnL queries filtering by (payload->>'rr_dt')::date.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "add_wb_finance_rr_dt_idx"
down_revision: Union[str, None] = "d112ea543439"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL requires index expressions to use IMMUTABLE functions.
    # (payload->>'rr_dt')::date is STABLE; use make_date+substring instead.
    op.execute("""
        CREATE OR REPLACE FUNCTION _alembic_iso_to_date(t text)
        RETURNS date
        LANGUAGE sql IMMUTABLE PARALLEL SAFE
        AS $$
          SELECT CASE WHEN t ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
            THEN make_date(
              (substring(t from 1 for 4))::integer,
              (substring(t from 6 for 2))::integer,
              (substring(t from 9 for 2))::integer
            )
            ELSE NULL
          END
        $$
    """)
    op.execute("""
        CREATE INDEX ix_wb_finance_report_lines_project_rr_dt
        ON wb_finance_report_lines (project_id, (_alembic_iso_to_date(payload->>'rr_dt')))
        WHERE payload->>'rr_dt' IS NOT NULL
          AND payload->>'rr_dt' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
    """)


def downgrade() -> None:
    op.drop_index(
        "ix_wb_finance_report_lines_project_rr_dt",
        table_name="wb_finance_report_lines",
    )
    op.execute("DROP FUNCTION IF EXISTS _alembic_iso_to_date(text)")
