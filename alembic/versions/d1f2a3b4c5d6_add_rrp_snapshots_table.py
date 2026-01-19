"""add rrp_snapshots table for RRP XML snapshots (append-only)

Revision ID: d1f2a3b4c5d6
Revises: c9a1b2c3d4e5
Create Date: 2026-01-19

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1f2a3b4c5d6"
down_revision: Union[str, None] = "c9a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rrp_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("vendor_code_raw", sa.Text(), nullable=True),
        sa.Column("vendor_code_norm", sa.Text(), nullable=False),
        sa.Column("barcode", sa.Text(), nullable=True),
        sa.Column("rrp_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("rrp_stock", sa.Integer(), nullable=True),
        sa.Column("source_file", sa.Text(), nullable=True),
    )

    op.create_index("ix_rrp_snapshots_project_snapshot_at", "rrp_snapshots", ["project_id", "snapshot_at"])
    op.create_index("ix_rrp_snapshots_project_vendor", "rrp_snapshots", ["project_id", "vendor_code_norm"])


def downgrade() -> None:
    op.drop_index("ix_rrp_snapshots_project_vendor", table_name="rrp_snapshots")
    op.drop_index("ix_rrp_snapshots_project_snapshot_at", table_name="rrp_snapshots")
    op.drop_table("rrp_snapshots")

