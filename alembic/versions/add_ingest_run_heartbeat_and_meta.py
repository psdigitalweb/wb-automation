"""add heartbeat_at, celery_task_id, meta_json to ingest_runs

Revision ID: add_ingest_run_heartbeat_and_meta
Revises: add_params_json_to_ingest_runs
Create Date: 2026-01-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_ingest_run_heartbeat_and_meta"
down_revision: Union[str, None] = "add_params_json_to_ingest_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)

    if "ingest_runs" not in inspector.get_table_names():
        return

    existing_columns = {col["name"] for col in inspector.get_columns("ingest_runs")}

    if "heartbeat_at" not in existing_columns:
        op.add_column(
            "ingest_runs",
            sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "celery_task_id" not in existing_columns:
        op.add_column(
            "ingest_runs",
            sa.Column("celery_task_id", sa.Text(), nullable=True),
        )

    if "meta_json" not in existing_columns:
        op.add_column(
            "ingest_runs",
            sa.Column(
                "meta_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )

        # Ensure existing rows get the default value, then remove server_default if desired later.
        op.execute("UPDATE ingest_runs SET meta_json = '{}'::jsonb WHERE meta_json IS NULL")

    # Indexes
    # Requirement: (project_id, marketplace_code, job_code, status, created_at DESC)
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingest_runs_project_marketplace_job_status_created_at_desc
        ON ingest_runs (project_id, marketplace_code, job_code, status, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ingest_runs_project_id_status
        ON ingest_runs (project_id, status)
        """
    )


def downgrade() -> None:
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)

    if "ingest_runs" not in inspector.get_table_names():
        return

    # Drop indexes first
    op.execute("DROP INDEX IF EXISTS idx_ingest_runs_project_marketplace_job_status_created_at_desc")
    op.execute("DROP INDEX IF EXISTS idx_ingest_runs_project_id_status")

    existing_columns = {col["name"] for col in inspector.get_columns("ingest_runs")}

    if "meta_json" in existing_columns:
        op.drop_column("ingest_runs", "meta_json")
    if "celery_task_id" in existing_columns:
        op.drop_column("ingest_runs", "celery_task_id")
    if "heartbeat_at" in existing_columns:
        op.drop_column("ingest_runs", "heartbeat_at")

