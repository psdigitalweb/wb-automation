"""add WB product group memberships

Revision ID: 20260727_wb_product_groups
Revises: 20260721_wb_funnel_ctr
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260727_wb_product_groups"
down_revision: Union[str, None] = "20260721_wb_funnel_ctr"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "wb_product_group_memberships",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("wb_group_id", sa.BigInteger(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("missing_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_ingest_run_id", sa.Integer(), nullable=True),
        sa.Column("last_ingest_run_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id", "nm_id"],
            ["products.project_id", "products.nm_id"],
            ondelete="CASCADE",
            name="fk_wb_product_group_memberships_product",
        ),
        sa.ForeignKeyConstraint(
            ["first_ingest_run_id"],
            ["ingest_runs.id"],
            ondelete="SET NULL",
            name="fk_wb_product_group_memberships_first_run",
        ),
        sa.ForeignKeyConstraint(
            ["last_ingest_run_id"],
            ["ingest_runs.id"],
            ondelete="SET NULL",
            name="fk_wb_product_group_memberships_last_run",
        ),
        sa.CheckConstraint("missing_runs >= 0", name="ck_wb_product_group_memberships_missing_runs"),
    )
    op.create_index(
        "uq_wb_product_group_memberships_current_nm",
        "wb_product_group_memberships",
        ["project_id", "nm_id"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index(
        "ix_wb_product_group_memberships_current_group",
        "wb_product_group_memberships",
        ["project_id", "wb_group_id", "nm_id"],
        postgresql_where=sa.text("valid_to IS NULL"),
    )
    op.create_index(
        "ix_wb_product_group_memberships_history",
        "wb_product_group_memberships",
        ["project_id", "nm_id", "first_seen_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_wb_product_group_memberships_history", table_name="wb_product_group_memberships")
    op.drop_index("ix_wb_product_group_memberships_current_group", table_name="wb_product_group_memberships")
    op.drop_index("uq_wb_product_group_memberships_current_nm", table_name="wb_product_group_memberships")
    op.drop_table("wb_product_group_memberships")
