"""add wb_analytics tables (card stats daily, search query terms, search query daily)

Revision ID: add_wb_analytics_001
Revises: add_wb_communications_001
Create Date: 2026-02-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_wb_analytics_001"
down_revision: Union[str, None] = "add_wb_communications_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wb_card_stats_daily",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("open_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cart_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("order_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("order_sum", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("buyout_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("buyout_sum", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("buyout_percent", sa.Numeric(10, 4), nullable=True),
        sa.Column("add_to_cart_conversion", sa.Numeric(10, 4), nullable=True),
        sa.Column("cart_to_order_conversion", sa.Numeric(10, 4), nullable=True),
        sa.Column("add_to_wishlist_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("ingest_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingest_run_id"], ["ingest_runs.id"], ondelete="SET NULL"),
    )
    op.create_unique_constraint(
        "uq_wb_card_stats_daily_project_nm_date",
        "wb_card_stats_daily",
        ["project_id", "nm_id", "stat_date"],
    )
    op.create_index(
        "idx_wb_card_stats_daily_project_date",
        "wb_card_stats_daily",
        ["project_id", "stat_date"],
    )
    op.create_index(
        "idx_wb_card_stats_daily_project_nm",
        "wb_card_stats_daily",
        ["project_id", "nm_id", "stat_date"],
    )

    op.create_table(
        "wb_search_query_terms",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("frequency", sa.Integer(), nullable=True),
        sa.Column("is_ad", sa.Boolean(), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("ingest_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingest_run_id"], ["ingest_runs.id"], ondelete="SET NULL"),
    )
    op.create_unique_constraint(
        "uq_wb_search_query_terms_project_nm_text",
        "wb_search_query_terms",
        ["project_id", "nm_id", "search_text"],
    )
    op.create_index(
        "idx_wb_search_query_terms_project_nm",
        "wb_search_query_terms",
        ["project_id", "nm_id"],
    )

    op.create_table(
        "wb_search_query_daily",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("orders", sa.Integer(), server_default="0", nullable=False),
        sa.Column("avg_position", sa.Numeric(10, 2), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("ingest_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingest_run_id"], ["ingest_runs.id"], ondelete="SET NULL"),
    )
    op.create_unique_constraint(
        "uq_wb_search_query_daily_project_nm_text_date",
        "wb_search_query_daily",
        ["project_id", "nm_id", "search_text", "stat_date"],
    )
    op.create_index(
        "idx_wb_search_query_daily_project_date",
        "wb_search_query_daily",
        ["project_id", "stat_date"],
    )
    op.create_index(
        "idx_wb_search_query_daily_project_nm",
        "wb_search_query_daily",
        ["project_id", "nm_id", "stat_date"],
    )


def downgrade() -> None:
    op.drop_index("idx_wb_search_query_daily_project_nm", table_name="wb_search_query_daily")
    op.drop_index("idx_wb_search_query_daily_project_date", table_name="wb_search_query_daily")
    op.drop_constraint("uq_wb_search_query_daily_project_nm_text_date", "wb_search_query_daily", type_="unique")
    op.drop_table("wb_search_query_daily")

    op.drop_index("idx_wb_search_query_terms_project_nm", table_name="wb_search_query_terms")
    op.drop_constraint("uq_wb_search_query_terms_project_nm_text", "wb_search_query_terms", type_="unique")
    op.drop_table("wb_search_query_terms")

    op.drop_index("idx_wb_card_stats_daily_project_nm", table_name="wb_card_stats_daily")
    op.drop_index("idx_wb_card_stats_daily_project_date", table_name="wb_card_stats_daily")
    op.drop_constraint("uq_wb_card_stats_daily_project_nm_date", "wb_card_stats_daily", type_="unique")
    op.drop_table("wb_card_stats_daily")
