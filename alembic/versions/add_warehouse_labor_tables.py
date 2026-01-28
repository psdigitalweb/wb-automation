"""add warehouse_labor_days and warehouse_labor_day_rates tables

Revision ID: add_warehouse_labor_tables
Revises: add_scope_additional_costs
Create Date: 2026-01-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_warehouse_labor_tables"
down_revision: Union[str, None] = "add_scope_additional_costs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create warehouse_labor_days table
    op.create_table(
        "warehouse_labor_days",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("marketplace_code", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    
    # Foreign key to projects
    op.create_foreign_key(
        "fk_warehouse_labor_days_project_id",
        "warehouse_labor_days",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    
    # Partial unique indexes to handle NULL marketplace_code correctly
    op.execute(
        """
        CREATE UNIQUE INDEX uq_warehouse_labor_days_project_date_null
        ON warehouse_labor_days (project_id, work_date)
        WHERE marketplace_code IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_warehouse_labor_days_project_date_marketplace
        ON warehouse_labor_days (project_id, work_date, marketplace_code)
        WHERE marketplace_code IS NOT NULL
        """
    )
    
    # Regular index for queries
    op.create_index(
        "ix_warehouse_labor_days_project_date",
        "warehouse_labor_days",
        ["project_id", "work_date"],
    )
    
    # Create warehouse_labor_day_rates table
    op.create_table(
        "warehouse_labor_day_rates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("labor_day_id", sa.BigInteger(), nullable=False),
        sa.Column("rate_name", sa.Text(), nullable=False),
        sa.Column("employees_count", sa.Integer(), nullable=False),
        sa.Column("rate_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default="RUB"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    
    # Foreign key to warehouse_labor_days
    op.create_foreign_key(
        "fk_warehouse_labor_day_rates_labor_day_id",
        "warehouse_labor_day_rates",
        "warehouse_labor_days",
        ["labor_day_id"],
        ["id"],
        ondelete="CASCADE",
    )
    
    # CHECK constraint for employees_count
    op.create_check_constraint(
        "ck_warehouse_labor_day_rates_employees_count_positive",
        "warehouse_labor_day_rates",
        sa.text("employees_count > 0"),
    )
    
    # Index for labor_day_id
    op.create_index(
        "ix_warehouse_labor_day_rates_labor_day_id",
        "warehouse_labor_day_rates",
        ["labor_day_id"],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_warehouse_labor_day_rates_labor_day_id", table_name="warehouse_labor_day_rates")
    op.drop_index("ix_warehouse_labor_days_project_date", table_name="warehouse_labor_days")
    
    # Drop partial unique indexes
    op.execute("DROP INDEX IF EXISTS uq_warehouse_labor_days_project_date_marketplace")
    op.execute("DROP INDEX IF EXISTS uq_warehouse_labor_days_project_date_null")
    
    # Drop CHECK constraint
    op.drop_constraint("ck_warehouse_labor_day_rates_employees_count_positive", table_name="warehouse_labor_day_rates", type_="check")
    
    # Drop foreign keys
    op.drop_constraint("fk_warehouse_labor_day_rates_labor_day_id", table_name="warehouse_labor_day_rates", type_="foreignkey")
    op.drop_constraint("fk_warehouse_labor_days_project_id", table_name="warehouse_labor_days", type_="foreignkey")
    
    # Drop tables
    op.drop_table("warehouse_labor_day_rates")
    op.drop_table("warehouse_labor_days")
