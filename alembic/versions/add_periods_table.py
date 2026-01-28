"""add periods table

Revision ID: add_periods_table
Revises: add_internal_data_row_errors
Create Date: 2026-01-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_periods_table"
down_revision: Union[str, None] = "add_internal_data_row_errors"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if table exists
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    if "periods" not in existing_tables:
        op.create_table(
            "periods",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("period_type", sa.String(length=50), nullable=False),
            sa.Column("date_from", sa.Date(), nullable=False),
            sa.Column("date_to", sa.Date(), nullable=False),
            sa.UniqueConstraint(
                "period_type",
                "date_from",
                "date_to",
                name="uq_periods_type_from_to",
            ),
        )
        
        op.create_index(
            "idx_periods_type",
            "periods",
            ["period_type"],
        )
        op.create_index(
            "idx_periods_dates",
            "periods",
            ["date_from", "date_to"],
        )


def downgrade() -> None:
    op.drop_index("idx_periods_dates", table_name="periods")
    op.drop_index("idx_periods_type", table_name="periods")
    op.drop_table("periods")
