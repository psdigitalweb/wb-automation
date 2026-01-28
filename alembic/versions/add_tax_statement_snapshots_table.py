"""add tax_statement_snapshots table

Revision ID: tax_stmt_snapshots
Revises: add_tax_profiles_table
Create Date: 2026-01-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "tax_stmt_snapshots"
down_revision: Union[str, None] = "add_tax_profiles_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if table exists
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    if "tax_statement_snapshots" not in existing_tables:
        op.create_table(
            "tax_statement_snapshots",
            sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("period_id", sa.Integer(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("tax_expense_total", sa.Numeric(), nullable=True),
            sa.Column(
                "breakdown_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "stats_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("error_trace", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["project_id"],
                ["projects.id"],
                name="fk_tax_statement_snapshots_project_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["period_id"],
                ["periods.id"],
                name="fk_tax_statement_snapshots_period_id",
                ondelete="CASCADE",
            ),
        )
        
        op.create_index(
            "idx_tax_statement_snapshots_project_period",
            "tax_statement_snapshots",
            ["project_id", "period_id"],
        )
        op.create_index(
            "idx_tax_statement_snapshots_project_period_version",
            "tax_statement_snapshots",
            ["project_id", "period_id", sa.text("version DESC")],
        )


def downgrade() -> None:
    op.drop_index(
        "idx_tax_statement_snapshots_project_period_version",
        table_name="tax_statement_snapshots",
    )
    op.drop_index(
        "idx_tax_statement_snapshots_project_period",
        table_name="tax_statement_snapshots",
    )
    op.drop_table("tax_statement_snapshots")
