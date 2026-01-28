"""add cogs_direct_rules table

Revision ID: add_cogs_direct_rules
Revises: add_internal_data_mapping_json
Create Date: 2026-01-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_cogs_direct_rules"
down_revision: Union[str, None] = "add_internal_data_mapping_json"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cogs_direct_rules",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("internal_sku", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("value", sa.Numeric(12, 4), nullable=False),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column(
            "meta_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_cogs_direct_rules_project_id",
            ondelete="CASCADE",
        ),
    )
    op.create_unique_constraint(
        "uq_cogs_direct_rules_project_sku_valid_from",
        "cogs_direct_rules",
        ["project_id", "internal_sku", "valid_from"],
    )
    op.create_index(
        "ix_cogs_direct_rules_project_internal_sku",
        "cogs_direct_rules",
        ["project_id", "internal_sku"],
    )
    op.create_index(
        "ix_cogs_direct_rules_project_sku_valid_from",
        "cogs_direct_rules",
        ["project_id", "internal_sku", "valid_from"],
    )


def downgrade() -> None:
    op.drop_index("ix_cogs_direct_rules_project_sku_valid_from", table_name="cogs_direct_rules")
    op.drop_index("ix_cogs_direct_rules_project_internal_sku", table_name="cogs_direct_rules")
    op.drop_constraint(
        "uq_cogs_direct_rules_project_sku_valid_from",
        "cogs_direct_rules",
        type_="unique",
    )
    op.drop_table("cogs_direct_rules")
