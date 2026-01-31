"""add wb_financial_events, wb_financial_reconciliations, wb_financial_allocations tables

Revision ID: add_wb_financial_events_001
Revises: 87cbcbbc8c60
Create Date: 2026-01-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "add_wb_financial_events_001"
down_revision: Union[str, None] = "87cbcbbc8c60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A) wb_financial_events
    op.create_table(
        "wb_financial_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("marketplace_code", sa.Text(), nullable=False, server_default="wildberries"),
        sa.Column("report_id", sa.BigInteger(), nullable=True),
        sa.Column("line_id", sa.BigInteger(), nullable=True),
        sa.Column("line_uid_surrogate", sa.Text(), nullable=True),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("event_date_quality", sa.Text(), nullable=False, server_default="fallback"),
        sa.Column("period_from", sa.Date(), nullable=True),
        sa.Column("period_to", sa.Date(), nullable=True),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("vendor_code", sa.Text(), nullable=True),
        sa.Column("internal_sku", sa.Text(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=20, scale=2), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default="RUB"),
        sa.Column("source_field", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_foreign_key(
        "fk_wb_financial_events_project_id",
        "wb_financial_events",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "uq_wb_financial_events_project_report_line",
        "wb_financial_events",
        ["project_id", "report_id", "line_id", "event_type", "source_field"],
        unique=True,
        postgresql_where=sa.text("line_id IS NOT NULL"),
    )
    op.create_index(
        "uq_wb_financial_events_project_report_surrogate",
        "wb_financial_events",
        ["project_id", "report_id", "line_uid_surrogate", "event_type", "source_field"],
        unique=True,
        postgresql_where=sa.text("line_id IS NULL AND line_uid_surrogate IS NOT NULL"),
    )
    op.create_index(
        "ix_wb_financial_events_project_sku_date",
        "wb_financial_events",
        ["project_id", "internal_sku", "event_date"],
        postgresql_where=sa.text("internal_sku IS NOT NULL"),
    )
    op.create_index(
        "ix_wb_financial_events_project_period_type",
        "wb_financial_events",
        ["project_id", "period_from", "period_to", "event_type"],
    )
    op.create_index(
        "ix_wb_financial_events_project_report_line_id",
        "wb_financial_events",
        ["project_id", "report_id", "line_id"],
    )

    # B) wb_financial_reconciliations
    op.create_table(
        "wb_financial_reconciliations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=True),
        sa.Column("period_to", sa.Date(), nullable=True),
        sa.Column("report_id", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("metric", sa.Text(), nullable=True),
        sa.Column("value", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_foreign_key(
        "fk_wb_financial_reconciliations_project_id",
        "wb_financial_reconciliations",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # C) wb_financial_allocations (foundation v2)
    op.create_table(
        "wb_financial_allocations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("period_from", sa.Date(), nullable=True),
        sa.Column("period_to", sa.Date(), nullable=True),
        sa.Column("allocation_type", sa.Text(), nullable=True),
        sa.Column("method", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("internal_sku", sa.Text(), nullable=True),
        sa.Column("allocated_amount", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("params_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_foreign_key(
        "fk_wb_financial_allocations_project_id",
        "wb_financial_allocations",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "uq_wb_financial_allocations_project_period_type_method_version_sku",
        "wb_financial_allocations",
        ["project_id", "period_from", "period_to", "allocation_type", "method", "version", "internal_sku"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_wb_financial_allocations_project_period_type_method_version_sku",
        table_name="wb_financial_allocations",
    )
    op.drop_table("wb_financial_allocations")

    op.drop_table("wb_financial_reconciliations")

    op.drop_index("ix_wb_financial_events_project_report_line_id", table_name="wb_financial_events")
    op.drop_index("ix_wb_financial_events_project_period_type", table_name="wb_financial_events")
    op.drop_index("ix_wb_financial_events_project_sku_date", table_name="wb_financial_events")
    op.drop_index("uq_wb_financial_events_project_report_surrogate", table_name="wb_financial_events")
    op.drop_index("uq_wb_financial_events_project_report_line", table_name="wb_financial_events")
    op.drop_table("wb_financial_events")
