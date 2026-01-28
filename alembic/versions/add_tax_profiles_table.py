"""add tax_profiles table

Revision ID: add_tax_profiles_table
Revises: add_params_json_to_ingest_runs
Create Date: 2026-01-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_tax_profiles_table"
down_revision: Union[str, None] = "add_params_json_to_ingest_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if table exists
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()
    
    if "tax_profiles" not in existing_tables:
        op.create_table(
            "tax_profiles",
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("model_code", sa.String(length=64), nullable=False),
            sa.Column(
                "params_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["project_id"],
                ["projects.id"],
                name="fk_tax_profiles_project_id",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("project_id"),
        )
        
        op.create_index(
            "idx_tax_profiles_project_id",
            "tax_profiles",
            ["project_id"],
        )


def downgrade() -> None:
    op.drop_index("idx_tax_profiles_project_id", table_name="tax_profiles")
    op.drop_table("tax_profiles")
