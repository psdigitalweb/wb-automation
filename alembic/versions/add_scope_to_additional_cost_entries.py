"""add scope column to additional_cost_entries

Revision ID: add_scope_additional_costs
Revises: add_cogs_applies_to_price_source
Create Date: 2026-01-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_scope_additional_costs"
down_revision: Union[str, None] = "add_cogs_applies_to_price_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add scope column with default 'project'
    op.add_column(
        "additional_cost_entries",
        sa.Column("scope", sa.Text(), nullable=True, server_default="project"),
    )
    
    # Backfill existing records based on current data
    op.execute("""
        UPDATE additional_cost_entries
        SET scope = CASE
            WHEN nm_id IS NOT NULL THEN 'product'
            WHEN marketplace_code IS NOT NULL THEN 'marketplace'
            ELSE 'project'
        END
        WHERE scope IS NULL;
    """)
    
    # Make scope NOT NULL after backfill
    op.alter_column(
        "additional_cost_entries",
        "scope",
        nullable=False,
        server_default="project",
    )
    
    # Add CHECK constraint for scope values
    op.create_check_constraint(
        "ck_additional_cost_entries_scope_valid",
        "additional_cost_entries",
        sa.text("scope IN ('project', 'marketplace', 'product')"),
    )
    
    # Add CHECK constraints for scope field consistency
    # scope='project': marketplace_code IS NULL AND internal_sku IS NULL AND nm_id IS NULL
    op.create_check_constraint(
        "ck_additional_cost_entries_scope_project",
        "additional_cost_entries",
        sa.text("(scope != 'project') OR (marketplace_code IS NULL AND internal_sku IS NULL AND nm_id IS NULL)"),
    )
    
    # scope='marketplace': marketplace_code IS NOT NULL AND internal_sku IS NULL AND nm_id IS NULL
    op.create_check_constraint(
        "ck_additional_cost_entries_scope_marketplace",
        "additional_cost_entries",
        sa.text("(scope != 'marketplace') OR (marketplace_code IS NOT NULL AND internal_sku IS NULL AND nm_id IS NULL)"),
    )
    
    # scope='product': internal_sku IS NOT NULL
    op.create_check_constraint(
        "ck_additional_cost_entries_scope_product",
        "additional_cost_entries",
        sa.text("(scope != 'product') OR (internal_sku IS NOT NULL)"),
    )
    
    # Drop old index for nm_id and create new one for internal_sku
    op.drop_index("ix_additional_cost_entries_project_nm_id_period", table_name="additional_cost_entries")
    op.create_index(
        "ix_additional_cost_entries_project_internal_sku_period",
        "additional_cost_entries",
        ["project_id", "internal_sku", "period_from", "period_to"],
        postgresql_where=sa.text("internal_sku IS NOT NULL"),
    )
    
    # Add index for scope-based queries (for summary optimization)
    op.create_index(
        "ix_additional_cost_entries_project_scope_period",
        "additional_cost_entries",
        ["project_id", "scope", "period_from", "period_to"],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_additional_cost_entries_project_scope_period", table_name="additional_cost_entries")
    op.drop_index("ix_additional_cost_entries_project_internal_sku_period", table_name="additional_cost_entries")
    
    # Recreate old nm_id index
    op.create_index(
        "ix_additional_cost_entries_project_nm_id_period",
        "additional_cost_entries",
        ["project_id", "nm_id", "period_from", "period_to"],
        postgresql_where=sa.text("nm_id IS NOT NULL"),
    )
    
    # Drop CHECK constraints
    op.drop_constraint("ck_additional_cost_entries_scope_product", table_name="additional_cost_entries", type_="check")
    op.drop_constraint("ck_additional_cost_entries_scope_marketplace", table_name="additional_cost_entries", type_="check")
    op.drop_constraint("ck_additional_cost_entries_scope_project", table_name="additional_cost_entries", type_="check")
    op.drop_constraint("ck_additional_cost_entries_scope_valid", table_name="additional_cost_entries", type_="check")
    
    # Drop scope column
    op.drop_column("additional_cost_entries", "scope")
