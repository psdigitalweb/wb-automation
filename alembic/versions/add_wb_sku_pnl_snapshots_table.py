"""add wb_sku_pnl_snapshots table

Revision ID: add_wb_sku_pnl_001
Revises: add_wb_financial_events_001
Create Date: 2026-01-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_wb_sku_pnl_001"
down_revision: Union[str, None] = "add_wb_financial_events_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wb_sku_pnl_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("internal_sku", sa.Text(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default="RUB"),
        sa.Column("gmv", sa.Numeric(precision=20, scale=2), nullable=False, server_default="0"),
        sa.Column("wb_commission_no_vat", sa.Numeric(precision=20, scale=2), nullable=False, server_default="0"),
        sa.Column("wb_commission_vat", sa.Numeric(precision=20, scale=2), nullable=False, server_default="0"),
        sa.Column("acquiring_fee", sa.Numeric(precision=20, scale=2), nullable=False, server_default="0"),
        sa.Column("delivery_fee", sa.Numeric(precision=20, scale=2), nullable=False, server_default="0"),
        sa.Column("rebill_logistics_cost", sa.Numeric(precision=20, scale=2), nullable=False, server_default="0"),
        sa.Column("pvz_fee", sa.Numeric(precision=20, scale=2), nullable=False, server_default="0"),
        sa.Column("net_before_cogs", sa.Numeric(precision=20, scale=2), nullable=False, server_default="0"),
        sa.Column("net_payable_metric", sa.Numeric(precision=20, scale=2), nullable=False, server_default="0"),
        sa.Column("wb_sales_commission_metric", sa.Numeric(precision=20, scale=2), nullable=False, server_default="0"),
        sa.Column("events_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("built_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_foreign_key(
        "fk_wbsps_project",
        "wb_sku_pnl_snapshots",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "uq_wbsp_key",
        "wb_sku_pnl_snapshots",
        ["project_id", "period_from", "period_to", "internal_sku", "version"],
        unique=True,
    )
    op.create_index(
        "ix_wbsp_proj_period",
        "wb_sku_pnl_snapshots",
        ["project_id", "period_from", "period_to", "version"],
    )
    op.create_index(
        "ix_wbsp_proj_sku",
        "wb_sku_pnl_snapshots",
        ["project_id", "internal_sku", "version"],
    )
    op.create_index(
        "ix_wbsp_proj_net",
        "wb_sku_pnl_snapshots",
        ["project_id", "period_from", "period_to", "net_before_cogs"],
    )


def downgrade() -> None:
    op.drop_index("ix_wbsp_proj_net", table_name="wb_sku_pnl_snapshots")
    op.drop_index("ix_wbsp_proj_sku", table_name="wb_sku_pnl_snapshots")
    op.drop_index("ix_wbsp_proj_period", table_name="wb_sku_pnl_snapshots")
    op.drop_index("uq_wbsp_key", table_name="wb_sku_pnl_snapshots")
    op.drop_table("wb_sku_pnl_snapshots")
