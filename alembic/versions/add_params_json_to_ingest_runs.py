"""add params_json column to ingest_runs

Revision ID: add_params_json_to_ingest_runs
Revises: add_periods_table
Create Date: 2026-01-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_params_json_to_ingest_runs"
down_revision: Union[str, None] = "add_periods_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if column exists
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    
    if "ingest_runs" in inspector.get_table_names():
        existing_columns = {col["name"] for col in inspector.get_columns("ingest_runs")}
        
        if "params_json" not in existing_columns:
            op.add_column(
                "ingest_runs",
                sa.Column(
                    "params_json",
                    postgresql.JSONB(astext_type=sa.Text()),
                    nullable=True,
                ),
            )


def downgrade() -> None:
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    
    if "ingest_runs" in inspector.get_table_names():
        existing_columns = {col["name"] for col in inspector.get_columns("ingest_runs")}
        
        if "params_json" in existing_columns:
            op.drop_column("ingest_runs", "params_json")
