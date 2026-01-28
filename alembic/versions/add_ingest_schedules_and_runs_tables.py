"""add ingest_schedules and ingest_runs tables

Revision ID: add_ingest_schedules_and_runs
Revises: bc36e17d99c1
Create Date: 2026-01-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_ingest_schedules_and_runs"
down_revision: Union[str, None] = "bc36e17d99c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use inspector to make migration idempotent in case of partially applied schema
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    if "ingest_schedules" not in existing_tables:
        op.create_table(
            "ingest_schedules",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("marketplace_code", sa.String(length=50), nullable=False),
            sa.Column("job_code", sa.String(length=64), nullable=False),
            sa.Column("cron_expr", sa.Text(), nullable=False),
            sa.Column("timezone", sa.String(length=255), nullable=False),
            sa.Column(
                "is_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("TRUE"),
            ),
            sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
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
                name="fk_ingest_schedules_project_id",
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "project_id",
                "marketplace_code",
                "job_code",
                name="uq_ingest_schedules_project_marketplace_job",
            ),
        )

        op.create_index(
            "idx_ingest_schedules_project_id",
            "ingest_schedules",
            ["project_id"],
        )
        op.create_index(
            "idx_ingest_schedules_marketplace_code",
            "ingest_schedules",
            ["marketplace_code"],
        )
        op.create_index(
            "idx_ingest_schedules_job_code",
            "ingest_schedules",
            ["job_code"],
        )
        op.create_index(
            "idx_ingest_schedules_next_run_at",
            "ingest_schedules",
            ["next_run_at"],
        )

    if "ingest_runs" not in existing_tables:
        op.create_table(
            "ingest_runs",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column("schedule_id", sa.Integer(), nullable=True),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("marketplace_code", sa.String(length=50), nullable=False),
            sa.Column("job_code", sa.String(length=64), nullable=False),
            sa.Column("triggered_by", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("error_trace", sa.Text(), nullable=True),
            sa.Column(
                "stats_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["schedule_id"],
                ["ingest_schedules.id"],
                name="fk_ingest_runs_schedule_id",
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["project_id"],
                ["projects.id"],
                name="fk_ingest_runs_project_id",
                ondelete="CASCADE",
            ),
        )

        op.create_index(
            "idx_ingest_runs_schedule_id",
            "ingest_runs",
            ["schedule_id"],
        )
        op.create_index(
            "idx_ingest_runs_project_id",
            "ingest_runs",
            ["project_id"],
        )
        op.create_index(
            "idx_ingest_runs_marketplace_code",
            "ingest_runs",
            ["marketplace_code"],
        )
        op.create_index(
            "idx_ingest_runs_job_code",
            "ingest_runs",
            ["job_code"],
        )
        op.create_index(
            "idx_ingest_runs_started_at",
            "ingest_runs",
            ["started_at"],
        )
        op.create_index(
            "idx_ingest_runs_finished_at",
            "ingest_runs",
            ["finished_at"],
        )

        # Partial unique index to prevent concurrent running jobs for same (project, marketplace, job)
        op.create_index(
            "uq_ingest_runs_running_unique",
            "ingest_runs",
            ["project_id", "marketplace_code", "job_code"],
            unique=True,
            postgresql_where=sa.text("status = 'running'"),
        )


def downgrade() -> None:
    # Drop indexes and tables in reverse order
    op.drop_index(
        "uq_ingest_runs_running_unique",
        table_name="ingest_runs",
        if_exists=True,
    )
    op.drop_index(
        "idx_ingest_runs_finished_at",
        table_name="ingest_runs",
        if_exists=True,
    )
    op.drop_index(
        "idx_ingest_runs_started_at",
        table_name="ingest_runs",
        if_exists=True,
    )
    op.drop_index(
        "idx_ingest_runs_job_code",
        table_name="ingest_runs",
        if_exists=True,
    )
    op.drop_index(
        "idx_ingest_runs_marketplace_code",
        table_name="ingest_runs",
        if_exists=True,
    )
    op.drop_index(
        "idx_ingest_runs_project_id",
        table_name="ingest_runs",
        if_exists=True,
    )
    op.drop_index(
        "idx_ingest_runs_schedule_id",
        table_name="ingest_runs",
        if_exists=True,
    )
    op.drop_table("ingest_runs")

    op.drop_index(
        "idx_ingest_schedules_next_run_at",
        table_name="ingest_schedules",
        if_exists=True,
    )
    op.drop_index(
        "idx_ingest_schedules_job_code",
        table_name="ingest_schedules",
        if_exists=True,
    )
    op.drop_index(
        "idx_ingest_schedules_marketplace_code",
        table_name="ingest_schedules",
        if_exists=True,
    )
    op.drop_index(
        "idx_ingest_schedules_project_id",
        table_name="ingest_schedules",
        if_exists=True,
    )
    op.drop_table("ingest_schedules")

