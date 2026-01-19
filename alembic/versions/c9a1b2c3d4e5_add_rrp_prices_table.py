"""add rrp_prices table for 1C RRP XML ingestion

Revision ID: c9a1b2c3d4e5
Revises: b3d4e5f6a7b8
Create Date: 2026-01-19

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c9a1b2c3d4e5"
down_revision: Union[str, None] = "b3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rrp_prices",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.Text(), nullable=False),
        sa.Column("rrp_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("qty", sa.Integer(), nullable=True),
        sa.Column("source_file", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_index("ix_rrp_prices_project_id", "rrp_prices", ["project_id"], unique=False)
    op.create_index("ix_rrp_prices_sku", "rrp_prices", ["sku"], unique=False)
    op.create_index(
        "uq_rrp_prices_project_sku",
        "rrp_prices",
        ["project_id", "sku"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_rrp_prices_project_sku", table_name="rrp_prices")
    op.drop_index("ix_rrp_prices_sku", table_name="rrp_prices")
    op.drop_index("ix_rrp_prices_project_id", table_name="rrp_prices")
    op.drop_table("rrp_prices")

