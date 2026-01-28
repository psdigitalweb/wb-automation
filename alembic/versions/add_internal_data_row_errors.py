"""Add row errors tracking for Internal Data sync.

Revision ID: add_internal_data_row_errors
Revises: add_cogs_direct_rules
Create Date: 2026-01-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_internal_data_row_errors"
down_revision: Union[str, None] = "add_cogs_direct_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to internal_data_snapshots
    op.add_column(
        "internal_data_snapshots",
        sa.Column("rows_total", sa.Integer(), nullable=True),
    )
    op.add_column(
        "internal_data_snapshots",
        sa.Column("rows_imported", sa.Integer(), nullable=True),
    )
    op.add_column(
        "internal_data_snapshots",
        sa.Column("rows_failed", sa.Integer(), nullable=True),
    )

    # Create internal_data_row_errors table
    op.create_table(
        "internal_data_row_errors",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey("internal_data_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_index", sa.Integer(), nullable=False),
        sa.Column("source_key", sa.Text(), nullable=True),
        sa.Column("raw_row", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("transforms", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trace", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    
    # Create indexes
    op.create_index(
        "idx_internal_data_row_errors_snapshot",
        "internal_data_row_errors",
        ["snapshot_id"],
    )
    op.create_index(
        "idx_internal_data_row_errors_project_snapshot",
        "internal_data_row_errors",
        ["project_id", "snapshot_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_internal_data_row_errors_project_snapshot", "internal_data_row_errors")
    op.drop_index("idx_internal_data_row_errors_snapshot", "internal_data_row_errors")
    op.drop_table("internal_data_row_errors")
    op.drop_column("internal_data_snapshots", "rows_failed")
    op.drop_column("internal_data_snapshots", "rows_imported")
    op.drop_column("internal_data_snapshots", "rows_total")
