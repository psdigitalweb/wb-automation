"""add additional_cost_entries table

Revision ID: add_additional_cost_entries
Revises: add_tax_adjustments_table
Create Date: 2026-01-23 14:13:19.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_additional_cost_entries"
down_revision: Union[str, None] = "add_tax_adjustments_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create additional_cost_entries table
    op.create_table(
        "additional_cost_entries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("marketplace_code", sa.Text(), nullable=True),
        sa.Column("period_from", sa.Date(), nullable=False),
        sa.Column("period_to", sa.Date(), nullable=False),
        sa.Column("date_incurred", sa.Date(), nullable=True),
        sa.Column("currency", sa.Text(), nullable=False, server_default="RUB"),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("subcategory", sa.Text(), nullable=True),
        sa.Column("vendor", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("internal_sku", sa.Text(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default="manual"),
        sa.Column("external_uid", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("payload_hash", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # Foreign key to projects
    op.create_foreign_key(
        "fk_additional_cost_entries_project_id",
        "additional_cost_entries",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # CHECK constraints
    op.create_check_constraint(
        "ck_additional_cost_entries_period_valid",
        "additional_cost_entries",
        sa.text("period_to >= period_from"),
    )
    # Note: amount >= 0 constraint is optional - not adding it to allow negative adjustments if needed

    # Indexes
    op.create_index(
        "ix_additional_cost_entries_project_period",
        "additional_cost_entries",
        ["project_id", "period_from", "period_to"],
    )
    op.create_index(
        "ix_additional_cost_entries_project_marketplace_period",
        "additional_cost_entries",
        ["project_id", "marketplace_code", "period_from", "period_to"],
    )
    op.create_index(
        "ix_additional_cost_entries_project_category_period",
        "additional_cost_entries",
        ["project_id", "category", "period_from", "period_to"],
    )
    op.create_index(
        "ix_additional_cost_entries_project_nm_id_period",
        "additional_cost_entries",
        ["project_id", "nm_id", "period_from", "period_to"],
        postgresql_where=sa.text("nm_id IS NOT NULL"),
    )

    # Unique constraint for deduplication (for imports)
    op.create_index(
        "uq_additional_cost_entries_project_source_external_uid",
        "additional_cost_entries",
        ["project_id", "source", "external_uid"],
        unique=True,
        postgresql_where=sa.text("external_uid IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_additional_cost_entries_project_source_external_uid",
        table_name="additional_cost_entries",
    )
    op.drop_index("ix_additional_cost_entries_project_nm_id_period", table_name="additional_cost_entries")
    op.drop_index("ix_additional_cost_entries_project_category_period", table_name="additional_cost_entries")
    op.drop_index("ix_additional_cost_entries_project_marketplace_period", table_name="additional_cost_entries")
    op.drop_index("ix_additional_cost_entries_project_period", table_name="additional_cost_entries")
    op.drop_constraint("ck_additional_cost_entries_period_valid", table_name="additional_cost_entries", type_="check")
    op.drop_constraint("fk_additional_cost_entries_project_id", table_name="additional_cost_entries", type_="foreignkey")
    op.drop_table("additional_cost_entries")
