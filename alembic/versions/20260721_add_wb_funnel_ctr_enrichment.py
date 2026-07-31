"""add WB funnel report CTR enrichment tables

Revision ID: 20260721_wb_funnel_ctr
Revises: 20260519_seo_category_selected_queries
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260721_wb_funnel_ctr"
down_revision: Union[str, None] = "20260519_seo_category_selected_queries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wb_funnel_report_imports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=True),
        sa.Column("period_to", sa.Date(), nullable=True),
        sa.Column("rows_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quality_summary", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "uq_wb_funnel_report_imports_completed_hash",
        "wb_funnel_report_imports",
        ["project_id", "content_sha256"],
        unique=True,
        postgresql_where=sa.text("status = 'completed'"),
    )
    op.create_index(
        "idx_wb_funnel_report_imports_project_created",
        "wb_funnel_report_imports",
        ["project_id", "created_at"],
    )

    op.create_table(
        "wb_funnel_report_rows",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("import_id", sa.BigInteger(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("vendor_code", sa.Text(), nullable=True),
        sa.Column("product_name", sa.Text(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("impressions", sa.Integer(), nullable=False),
        sa.Column("card_clicks", sa.Integer(), nullable=False),
        sa.Column("reported_ctr", sa.Numeric(14, 4), nullable=True),
        sa.Column("quality_status", sa.String(32), nullable=False),
        sa.Column("quality_flags", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("ARRAY[]::text[]")),
        sa.Column("source_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["import_id"], ["wb_funnel_report_imports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("import_id", "row_number", name="uq_wb_funnel_report_rows_import_row"),
    )
    op.create_index(
        "idx_wb_funnel_report_rows_project_nm_date",
        "wb_funnel_report_rows",
        ["project_id", "nm_id", "stat_date"],
    )

    op.create_table(
        "wb_funnel_ctr_daily",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("impressions", sa.Integer(), nullable=False),
        sa.Column("card_clicks", sa.Integer(), nullable=False),
        sa.Column("reported_ctr", sa.Numeric(14, 4), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("quality_status", sa.String(32), nullable=False),
        sa.Column("quality_flags", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("ARRAY[]::text[]")),
        sa.Column("last_import_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_import_id"], ["wb_funnel_report_imports.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("project_id", "nm_id", "stat_date", name="uq_wb_funnel_ctr_daily_project_nm_date"),
    )
    op.create_index(
        "idx_wb_funnel_ctr_daily_project_date",
        "wb_funnel_ctr_daily",
        ["project_id", "stat_date"],
    )
    op.create_index(
        "idx_wb_funnel_ctr_daily_quality_flags",
        "wb_funnel_ctr_daily",
        ["quality_flags"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("idx_wb_funnel_ctr_daily_quality_flags", table_name="wb_funnel_ctr_daily")
    op.drop_index("idx_wb_funnel_ctr_daily_project_date", table_name="wb_funnel_ctr_daily")
    op.drop_table("wb_funnel_ctr_daily")
    op.drop_index("idx_wb_funnel_report_rows_project_nm_date", table_name="wb_funnel_report_rows")
    op.drop_table("wb_funnel_report_rows")
    op.drop_index("idx_wb_funnel_report_imports_project_created", table_name="wb_funnel_report_imports")
    op.drop_index("uq_wb_funnel_report_imports_completed_hash", table_name="wb_funnel_report_imports")
    op.drop_table("wb_funnel_report_imports")
