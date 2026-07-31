"""add WB product content history and main photo archive metadata

Revision ID: 20260727_wb_content_history
Revises: 20260727_wb_product_groups
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260727_wb_content_history"
down_revision: Union[str, None] = "20260727_wb_product_groups"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("products", sa.Column("content_hash", sa.String(64), nullable=True))
    op.add_column("products", sa.Column("content_version", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("content_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("products", sa.Column("content_last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("products", sa.Column("wb_content_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("products", sa.Column("main_photo_asset_hash", sa.String(64), nullable=True))
    op.create_index(
        "ix_products_project_content_changed_at",
        "products",
        ["project_id", "content_changed_at"],
    )

    op.create_table(
        "wb_product_content_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("normalization_version", sa.String(32), nullable=False),
        sa.Column("content_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "changed_fields",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "change_types",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingest_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ingest_run_id"], ["ingest_runs.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "project_id",
            "nm_id",
            "version_no",
            name="uq_wb_product_content_versions_project_nm_version",
        ),
        sa.CheckConstraint("version_no > 0", name="ck_wb_product_content_versions_version_positive"),
        sa.CheckConstraint(
            "event_type IN ('initial', 'changed')",
            name="ck_wb_product_content_versions_event_type",
        ),
    )
    op.create_index(
        "uq_wb_product_content_versions_run_nm",
        "wb_product_content_versions",
        ["ingest_run_id", "project_id", "nm_id"],
        unique=True,
        postgresql_where=sa.text("ingest_run_id IS NOT NULL"),
    )
    op.create_index(
        "ix_wb_product_content_versions_project_nm_observed",
        "wb_product_content_versions",
        ["project_id", "nm_id", sa.text("observed_at DESC")],
    )
    op.create_index(
        "ix_wb_product_content_versions_project_observed",
        "wb_product_content_versions",
        ["project_id", sa.text("observed_at DESC")],
    )
    op.create_index(
        "ix_wb_product_content_versions_content_hash",
        "wb_product_content_versions",
        ["content_hash"],
    )

    op.create_table(
        "wb_product_main_photo_assets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("content_type", sa.String(128), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "project_id",
            "nm_id",
            "sha256",
            name="uq_wb_product_main_photo_assets_project_nm_hash",
        ),
        sa.CheckConstraint("file_size >= 0", name="ck_wb_product_main_photo_assets_file_size"),
    )
    op.create_index(
        "ix_wb_product_main_photo_assets_project_nm",
        "wb_product_main_photo_assets",
        ["project_id", "nm_id"],
    )

    op.create_table(
        "wb_product_main_photo_periods",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("content_version_id", sa.BigInteger(), nullable=True),
        sa.Column("asset_id", sa.BigInteger(), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("observed_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ingest_run_id", sa.Integer(), nullable=True),
        sa.Column("archive_status", sa.String(32), nullable=False),
        sa.Column("archive_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["content_version_id"],
            ["wb_product_content_versions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["wb_product_main_photo_assets.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["ingest_run_id"], ["ingest_runs.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "archive_status IN ('pending', 'stored', 'failed', 'skipped_inactive')",
            name="ck_wb_product_main_photo_periods_archive_status",
        ),
    )
    op.create_index(
        "uq_wb_product_main_photo_periods_open",
        "wb_product_main_photo_periods",
        ["project_id", "nm_id"],
        unique=True,
        postgresql_where=sa.text("observed_to IS NULL"),
    )
    op.create_index(
        "ix_wb_product_main_photo_periods_project_nm_from",
        "wb_product_main_photo_periods",
        ["project_id", "nm_id", sa.text("observed_from DESC")],
    )

    op.create_table(
        "wb_showcase_product_presence",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("showcase_brand_id", sa.BigInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_run_id", sa.Integer(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consecutive_missing_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_seen_run_id"], ["ingest_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("project_id", "nm_id"),
        sa.CheckConstraint(
            "consecutive_missing_runs >= 0",
            name="ck_wb_showcase_product_presence_missing_nonnegative",
        ),
    )
    op.create_index(
        "ix_wb_showcase_product_presence_project_active",
        "wb_showcase_product_presence",
        ["project_id", "is_active", "nm_id"],
    )
    op.create_index(
        "ix_wb_showcase_product_presence_project_brand",
        "wb_showcase_product_presence",
        ["project_id", "showcase_brand_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_wb_showcase_product_presence_project_brand",
        table_name="wb_showcase_product_presence",
    )
    op.drop_index(
        "ix_wb_showcase_product_presence_project_active",
        table_name="wb_showcase_product_presence",
    )
    op.drop_table("wb_showcase_product_presence")

    op.drop_index(
        "ix_wb_product_main_photo_periods_project_nm_from",
        table_name="wb_product_main_photo_periods",
    )
    op.drop_index(
        "uq_wb_product_main_photo_periods_open",
        table_name="wb_product_main_photo_periods",
    )
    op.drop_table("wb_product_main_photo_periods")

    op.drop_index(
        "ix_wb_product_main_photo_assets_project_nm",
        table_name="wb_product_main_photo_assets",
    )
    op.drop_table("wb_product_main_photo_assets")

    op.drop_index(
        "ix_wb_product_content_versions_content_hash",
        table_name="wb_product_content_versions",
    )
    op.drop_index(
        "ix_wb_product_content_versions_project_observed",
        table_name="wb_product_content_versions",
    )
    op.drop_index(
        "ix_wb_product_content_versions_project_nm_observed",
        table_name="wb_product_content_versions",
    )
    op.drop_index(
        "uq_wb_product_content_versions_run_nm",
        table_name="wb_product_content_versions",
    )
    op.drop_table("wb_product_content_versions")

    op.drop_index("ix_products_project_content_changed_at", table_name="products")
    op.drop_column("products", "main_photo_asset_hash")
    op.drop_column("products", "wb_content_updated_at")
    op.drop_column("products", "content_last_seen_at")
    op.drop_column("products", "content_changed_at")
    op.drop_column("products", "content_version")
    op.drop_column("products", "content_hash")
