"""add applies_to and price_source_code to cogs_direct_rules

Revision ID: add_cogs_applies_to_price_source
Revises: add_internal_categories
Create Date: 2026-01-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "add_cogs_applies_to_price_source"
down_revision: Union[str, None] = "add_internal_categories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cogs_direct_rules",
        sa.Column("applies_to", sa.Text(), nullable=False, server_default="sku"),
    )
    op.add_column(
        "cogs_direct_rules",
        sa.Column("price_source_code", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_cogs_direct_rules_project_applies_to",
        "cogs_direct_rules",
        ["project_id", "applies_to"],
    )


def downgrade() -> None:
    op.drop_index("ix_cogs_direct_rules_project_applies_to", table_name="cogs_direct_rules")
    op.drop_column("cogs_direct_rules", "price_source_code")
    op.drop_column("cogs_direct_rules", "applies_to")
