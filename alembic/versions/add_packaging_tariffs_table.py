"""add packaging_tariffs table

Revision ID: add_packaging_tariffs
Revises: add_warehouse_labor_tables
Create Date: 2026-01-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_packaging_tariffs"
down_revision: Union[str, None] = "add_warehouse_labor_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create packaging_tariffs table
    op.create_table(
        "packaging_tariffs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("internal_sku", sa.Text(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("cost_per_unit", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default="RUB"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    
    # Foreign key to projects
    op.create_foreign_key(
        "fk_packaging_tariffs_project_id",
        "packaging_tariffs",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    
    # Unique constraint: (project_id, internal_sku, valid_from)
    op.create_unique_constraint(
        "uq_packaging_tariffs_project_sku_date",
        "packaging_tariffs",
        ["project_id", "internal_sku", "valid_from"],
    )
    
    # Indexes
    op.create_index(
        "ix_packaging_tariffs_project_sku",
        "packaging_tariffs",
        ["project_id", "internal_sku"],
        unique=False,
    )
    op.create_index(
        "ix_packaging_tariffs_project_date",
        "packaging_tariffs",
        ["project_id", "valid_from"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_packaging_tariffs_project_date", table_name="packaging_tariffs")
    op.drop_index("ix_packaging_tariffs_project_sku", table_name="packaging_tariffs")
    op.drop_constraint("uq_packaging_tariffs_project_sku_date", table_name="packaging_tariffs")
    op.drop_table("packaging_tariffs")
