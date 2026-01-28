"""add tax_adjustments table (optional)

Revision ID: add_tax_adjustments_table
Revises: tax_stmt_snapshots
Create Date: 2026-01-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_tax_adjustments_table"
down_revision: Union[str, None] = "tax_stmt_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if table exists
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    if "tax_adjustments" not in existing_tables:
        op.create_table(
            "tax_adjustments",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("period_id", sa.Integer(), nullable=False),
            sa.Column("amount", sa.Numeric(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["project_id"],
                ["projects.id"],
                name="fk_tax_adjustments_project_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["period_id"],
                ["periods.id"],
                name="fk_tax_adjustments_period_id",
                ondelete="CASCADE",
            ),
        )
        
        op.create_index(
            "idx_tax_adjustments_project_period",
            "tax_adjustments",
            ["project_id", "period_id"],
        )


def downgrade() -> None:
    op.drop_index("idx_tax_adjustments_project_period", table_name="tax_adjustments")
    op.drop_table("tax_adjustments")
