"""Add WB search report MVP tables.

Revision ID: add_wb_search_report_mvp_001
Revises: add_hl_mvp_tables_001
Create Date: 2026-04-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_wb_search_report_mvp_001"
down_revision: Union[str, None] = "add_hl_mvp_tables_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wb_search_report_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("include_search_texts", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("include_substituted_skus", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("position_cluster", sa.Text(), nullable=False, server_default=sa.text("'all'")),
        sa.Column("order_by", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("request_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("raw_main_page", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("stats", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ingest_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["ingest_run_id"], ["ingest_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_wb_search_report_snapshots_project_created_at",
        "wb_search_report_snapshots",
        ["project_id", "created_at"],
    )
    op.create_index(
        "idx_wb_search_report_snapshots_project_period",
        "wb_search_report_snapshots",
        ["project_id", "period_from", "period_to"],
    )

    op.create_table(
        "wb_search_report_products",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("vendor_code", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("brand_name", sa.Text(), nullable=True),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("subject_name", sa.Text(), nullable=True),
        sa.Column("tag_id", sa.Integer(), nullable=True),
        sa.Column("tag_name", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ingest_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["ingest_run_id"], ["ingest_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["wb_search_report_snapshots.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("snapshot_id", "nm_id", name="uq_wb_search_report_products_snapshot_nm"),
    )
    op.create_index(
        "idx_wb_search_report_products_project_nm",
        "wb_search_report_products",
        ["project_id", "nm_id"],
    )
    op.create_index(
        "idx_wb_search_report_products_snapshot",
        "wb_search_report_products",
        ["snapshot_id"],
    )

    op.create_table(
        "wb_search_report_snapshot_scope",
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("days_present", sa.Integer(), nullable=False),
        sa.Column("min_daily_qty", sa.Integer(), nullable=False),
        sa.Column("min_required_qty", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["wb_search_report_snapshots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("snapshot_id", "nm_id", name="wb_search_report_snapshot_scope_pkey"),
    )
    op.create_index(
        "idx_wb_search_report_scope_snapshot",
        "wb_search_report_snapshot_scope",
        ["snapshot_id"],
    )

    op.create_table(
        "wb_search_report_keywords_cache",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("top_order_by", sa.Text(), nullable=False),
        sa.Column("limit", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("items", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("ingest_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["ingest_run_id"], ["ingest_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["wb_search_report_snapshots.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("snapshot_id", "nm_id", "top_order_by", name="uq_wb_search_report_keywords_cache_snapshot_nm_top"),
    )
    op.create_index(
        "idx_wb_search_report_keywords_cache_project_snapshot",
        "wb_search_report_keywords_cache",
        ["project_id", "snapshot_id"],
    )
    op.create_index(
        "idx_wb_search_report_keywords_cache_snapshot_nm",
        "wb_search_report_keywords_cache",
        ["snapshot_id", "nm_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_wb_search_report_keywords_cache_snapshot_nm", table_name="wb_search_report_keywords_cache")
    op.drop_index("idx_wb_search_report_keywords_cache_project_snapshot", table_name="wb_search_report_keywords_cache")
    op.drop_table("wb_search_report_keywords_cache")
    op.drop_index("idx_wb_search_report_scope_snapshot", table_name="wb_search_report_snapshot_scope")
    op.drop_table("wb_search_report_snapshot_scope")
    op.drop_index("idx_wb_search_report_products_snapshot", table_name="wb_search_report_products")
    op.drop_index("idx_wb_search_report_products_project_nm", table_name="wb_search_report_products")
    op.drop_table("wb_search_report_products")
    op.drop_index("idx_wb_search_report_snapshots_project_period", table_name="wb_search_report_snapshots")
    op.drop_index("idx_wb_search_report_snapshots_project_created_at", table_name="wb_search_report_snapshots")
    op.drop_table("wb_search_report_snapshots")
