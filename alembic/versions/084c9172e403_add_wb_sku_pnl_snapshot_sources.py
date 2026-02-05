"""add_wb_sku_pnl_snapshot_sources

Revision ID: 084c9172e403
Revises: 066e55f40ab9
Create Date: 2026-02-02 09:16:57.569952

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '084c9172e403'
down_revision: Union[str, None] = '066e55f40ab9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wb_sku_pnl_snapshot_sources",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("internal_sku", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.BigInteger(), nullable=False),
        sa.Column("report_period_from", sa.Date(), nullable=True),
        sa.Column("report_period_to", sa.Date(), nullable=True),
        sa.Column("report_type", sa.Text(), nullable=False, server_default="Реализация"),
        sa.Column("rows_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount_total", sa.Numeric(precision=20, scale=2), nullable=False, server_default="0"),
    )
    op.create_foreign_key(
        "fk_wbspsrc_project",
        "wb_sku_pnl_snapshot_sources",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "uq_wbspsrc_sku_report",
        "wb_sku_pnl_snapshot_sources",
        ["project_id", "period_from", "period_to", "internal_sku", "version", "report_id"],
        unique=True,
    )
    op.create_index(
        "ix_wbspsrc_snapshot",
        "wb_sku_pnl_snapshot_sources",
        ["project_id", "period_from", "period_to", "version"],
    )


def downgrade() -> None:
    op.drop_index("ix_wbspsrc_snapshot", table_name="wb_sku_pnl_snapshot_sources")
    op.drop_index("uq_wbspsrc_sku_report", table_name="wb_sku_pnl_snapshot_sources")
    op.drop_foreign_key("fk_wbspsrc_project", "wb_sku_pnl_snapshot_sources", "projects")
    op.drop_table("wb_sku_pnl_snapshot_sources")
