"""add wb_current_metrics and history tables

Revision ID: add_wb_curr_hist
Revises: add_ingest_schedules_and_runs
Create Date: 2026-01-21 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "add_wb_curr_hist"
down_revision: Union[str, None] = "add_ingest_schedules_and_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # We rely on existing types from projects.id (INTEGER) and ingest_runs.id (INTEGER)
    # as defined in previous Alembic migrations.

    # Current metrics (one row per project_id + nm_id)
    op.create_table(
        "wb_current_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("current_qty_fbo", sa.Integer(), nullable=True),
        sa.Column("current_qty_fbs", sa.Integer(), nullable=True),
        sa.Column("current_price_showcase", sa.Numeric(12, 2), nullable=True),
        sa.Column("current_spp_percent", sa.Integer(), nullable=True),
        sa.Column("current_price_base", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_ingest_run_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_wb_current_metrics_project_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_ingest_run_id"],
            ["ingest_runs.id"],
            name="fk_wb_current_metrics_last_ingest_run_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "project_id",
            "nm_id",
            name="uq_wb_current_metrics_project_nm_id",
        ),
    )

    op.create_index(
        "idx_wb_current_metrics_project_id",
        "wb_current_metrics",
        ["project_id"],
    )
    op.create_index(
        "idx_wb_current_metrics_project_nm_id",
        "wb_current_metrics",
        ["project_id", "nm_id"],
    )

    # Hourly showcase price snapshots
    op.create_table(
        "wb_showcase_price_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("price_showcase", sa.Numeric(12, 2), nullable=True),
        sa.Column("spp_percent", sa.Integer(), nullable=True),
        sa.Column(
            "snapshot_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column("ingest_run_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_wb_showcase_price_snapshots_project_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ingest_run_id"],
            ["ingest_runs.id"],
            name="fk_wb_showcase_price_snapshots_ingest_run_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "project_id",
            "nm_id",
            "snapshot_at",
            name="uq_wb_showcase_price_snapshots_project_nm_snapshot",
        ),
    )

    op.create_index(
        "idx_wb_showcase_snapshots_project_id",
        "wb_showcase_price_snapshots",
        ["project_id"],
    )
    # For queries like \"последние N часов по проекту\"
    # Simple composite index; PostgreSQL can use it for ORDER BY snapshot_at DESC.
    op.create_index(
        "idx_wb_showcase_snapshots_project_snapshot_at",
        "wb_showcase_price_snapshots",
        ["project_id", "snapshot_at"],
    )

    # Daily FBO stock snapshots
    op.create_table(
        "wb_fbo_stock_daily_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("qty_fbo", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("ingest_run_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_wb_fbo_stock_daily_snapshots_project_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ingest_run_id"],
            ["ingest_runs.id"],
            name="fk_wb_fbo_stock_daily_snapshots_ingest_run_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "project_id",
            "nm_id",
            "snapshot_date",
            name="uq_wb_fbo_stock_daily_snapshots_project_nm_date",
        ),
    )

    op.create_index(
        "idx_wb_fbo_daily_snapshots_project_id",
        "wb_fbo_stock_daily_snapshots",
        ["project_id"],
    )
    op.create_index(
        "idx_wb_fbo_daily_snapshots_project_snapshot_date",
        "wb_fbo_stock_daily_snapshots",
        ["project_id", "snapshot_date"],
    )

    # SPP change events
    op.create_table(
        "wb_spp_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("prev_spp_percent", sa.Integer(), nullable=True),
        sa.Column("spp_percent", sa.Integer(), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("ingest_run_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_wb_spp_events_project_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ingest_run_id"],
            ["ingest_runs.id"],
            name="fk_wb_spp_events_ingest_run_id",
            ondelete="SET NULL",
        ),
    )

    op.create_index(
        "idx_wb_spp_events_project_id",
        "wb_spp_events",
        ["project_id"],
    )
    op.create_index(
        "idx_wb_spp_events_project_changed_at",
        "wb_spp_events",
        ["project_id", "changed_at"],
    )
    op.create_index(
        "idx_wb_spp_events_project_nm_changed_at",
        "wb_spp_events",
        ["project_id", "nm_id", "changed_at"],
    )


def downgrade() -> None:
    # Drop history / events first (no dependencies from current)
    op.drop_index(
        "idx_wb_spp_events_project_nm_changed_at",
        table_name="wb_spp_events",
    )
    op.drop_index(
        "idx_wb_spp_events_project_changed_at",
        table_name="wb_spp_events",
    )
    op.drop_index(
        "idx_wb_spp_events_project_id",
        table_name="wb_spp_events",
    )
    op.drop_table("wb_spp_events")

    op.drop_index(
        "idx_wb_fbo_daily_snapshots_project_snapshot_date",
        table_name="wb_fbo_stock_daily_snapshots",
    )
    op.drop_index(
        "idx_wb_fbo_daily_snapshots_project_id",
        table_name="wb_fbo_stock_daily_snapshots",
    )
    op.drop_table("wb_fbo_stock_daily_snapshots")

    op.drop_index(
        "idx_wb_showcase_snapshots_project_snapshot_at",
        table_name="wb_showcase_price_snapshots",
    )
    op.drop_index(
        "idx_wb_showcase_snapshots_project_id",
        table_name="wb_showcase_price_snapshots",
    )
    op.drop_table("wb_showcase_price_snapshots")

    op.drop_index(
        "idx_wb_current_metrics_project_nm_id",
        table_name="wb_current_metrics",
    )
    op.drop_index(
        "idx_wb_current_metrics_project_id",
        table_name="wb_current_metrics",
    )
    op.drop_table("wb_current_metrics")

