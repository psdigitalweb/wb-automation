"""SEO iteration 1 — quality mode framework + candidate matcher trace tables.

Revision ID: 20260423_seo_iter1_quality_mode_and_matcher_runs
Revises: 20260422_add_seo_atoms_and_query_sets
Create Date: 2026-04-23

Additive-only migration. Adds ``quality_mode`` / ``degraded_reasons`` (and a
small handful of related columns) to the decision-carrying SEO tables, and
creates two new candidate-path tables (``seo_matcher_runs``,
``seo_matcher_results``) plus a nullable FK on ``seo_sku_query_sets`` pointing
at the new matcher runs table.

No data backfill, no drops, no behavior change on the current path. Legacy
rows keep ``quality_mode = NULL`` and ``matcher_run_id = NULL``.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "20260423_seo_iter1_quality_mode_and_matcher_runs"
down_revision: Union[str, None] = "20260422_add_seo_atoms_and_query_sets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CATEGORY_SCOPE_COMMENT = (
    "WB category scope for SEO pipeline (Wildberries subject_id/category scope), "
    "not a foreign key to internal_categories.id."
)


def _json_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB()
    return sa.JSON()


def _json_default_object() -> sa.TextClause:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.text("'{}'::jsonb")
    return sa.text("'{}'")


def _existing_columns(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def _add_quality_columns(inspector, table: str) -> None:
    columns = _existing_columns(inspector, table)
    if "quality_mode" not in columns:
        op.add_column(
            table,
            sa.Column("quality_mode", sa.String(length=16), nullable=True),
        )
    if "degraded_reasons" not in columns:
        op.add_column(
            table,
            sa.Column("degraded_reasons", _json_type(), nullable=True),
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    # ---- Create seo_matcher_runs first (FKs from other tables reference it) ----
    if "seo_matcher_runs" not in tables:
        op.create_table(
            "seo_matcher_runs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "project_id",
                sa.Integer(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "category_id",
                sa.Integer(),
                nullable=False,
                index=True,
                comment=CATEGORY_SCOPE_COMMENT,
            ),
            sa.Column("nm_id", sa.Integer(), nullable=False, index=True),
            sa.Column("matcher_version", sa.String(length=64), nullable=False),
            sa.Column("policy_version", sa.String(length=64), nullable=False),
            sa.Column("category_profile_version", sa.String(length=64), nullable=False),
            sa.Column(
                "sku_atoms_id",
                sa.Integer(),
                sa.ForeignKey("seo_meaning_atoms.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
            sa.Column(
                "vision_atoms_id",
                sa.Integer(),
                sa.ForeignKey("seo_meaning_atoms.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
            sa.Column("query_atoms_version", sa.String(length=64), nullable=True),
            sa.Column("embedding_model", sa.String(length=128), nullable=True),
            sa.Column("readiness_snapshot", _json_type(), nullable=False, server_default=_json_default_object()),
            sa.Column("quality_mode", sa.String(length=16), nullable=True),
            sa.Column("degraded_reasons", _json_type(), nullable=True),
            sa.Column("metrics", _json_type(), nullable=False, server_default=_json_default_object()),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error", _json_type(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_seo_matcher_runs_scope",
            "seo_matcher_runs",
            ["project_id", "category_id", "nm_id"],
        )

    if "seo_matcher_results" not in tables:
        op.create_table(
            "seo_matcher_results",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "run_id",
                sa.Integer(),
                sa.ForeignKey("seo_matcher_runs.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("cluster_key", sa.String(length=128), nullable=True, index=True),
            sa.Column(
                "query_meaning_id",
                sa.Integer(),
                sa.ForeignKey("seo_query_meanings.id", ondelete="SET NULL"),
                nullable=True,
                index=True,
            ),
            sa.Column("query_display", sa.Text(), nullable=False),
            sa.Column("normalized_query_text", sa.Text(), nullable=False),
            sa.Column("bucket", sa.String(length=32), nullable=False, index=True),
            sa.Column("eligibility_verdict", sa.String(length=40), nullable=False),
            sa.Column("score", sa.Numeric(12, 4), nullable=False, server_default="0"),
            sa.Column("score_components", _json_type(), nullable=False, server_default=_json_default_object()),
            sa.Column("matched_atoms", _json_type(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("missing_atoms", _json_type(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("conflict_atoms", _json_type(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("reasons", _json_type(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("ranking_value_used", sa.Numeric(14, 4), nullable=True),
            sa.Column("semantic_similarity", sa.Numeric(12, 6), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    # Refresh inspector after create_table calls.
    inspector = inspect(bind)

    # ---- Additive columns on existing SEO tables ----

    if "seo_sku_query_sets" in tables:
        _add_quality_columns(inspector, "seo_sku_query_sets")
        columns = _existing_columns(inspector, "seo_sku_query_sets")
        if "matcher_run_id" not in columns:
            op.add_column(
                "seo_sku_query_sets",
                sa.Column("matcher_run_id", sa.Integer(), nullable=True),
            )
            op.create_foreign_key(
                "fk_seo_sku_query_sets_matcher_run_id",
                "seo_sku_query_sets",
                "seo_matcher_runs",
                ["matcher_run_id"],
                ["id"],
                ondelete="SET NULL",
            )
            op.create_index(
                "ix_seo_sku_query_sets_matcher_run_id",
                "seo_sku_query_sets",
                ["matcher_run_id"],
            )

    if "seo_sku_meaning_annotations" in tables:
        _add_quality_columns(inspector, "seo_sku_meaning_annotations")

    if "seo_content_versions" in tables:
        _add_quality_columns(inspector, "seo_content_versions")
        columns = _existing_columns(inspector, "seo_content_versions")
        if "mode_used" not in columns:
            op.add_column(
                "seo_content_versions",
                sa.Column(
                    "mode_used",
                    sa.String(length=16),
                    nullable=False,
                    server_default="current",
                ),
            )
        if "publishable" not in columns:
            op.add_column(
                "seo_content_versions",
                sa.Column(
                    "publishable",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.text("false"),
                ),
            )
        if "matcher_run_id" not in columns:
            op.add_column(
                "seo_content_versions",
                sa.Column("matcher_run_id", sa.Integer(), nullable=True),
            )
            op.create_foreign_key(
                "fk_seo_content_versions_matcher_run_id",
                "seo_content_versions",
                "seo_matcher_runs",
                ["matcher_run_id"],
                ["id"],
                ondelete="SET NULL",
            )
            op.create_index(
                "ix_seo_content_versions_matcher_run_id",
                "seo_content_versions",
                ["matcher_run_id"],
            )

    if "seo_generation_runs" in tables:
        _add_quality_columns(inspector, "seo_generation_runs")
        columns = _existing_columns(inspector, "seo_generation_runs")
        if "matcher_run_id" not in columns:
            op.add_column(
                "seo_generation_runs",
                sa.Column("matcher_run_id", sa.Integer(), nullable=True),
            )
            op.create_foreign_key(
                "fk_seo_generation_runs_matcher_run_id",
                "seo_generation_runs",
                "seo_matcher_runs",
                ["matcher_run_id"],
                ["id"],
                ondelete="SET NULL",
            )
            op.create_index(
                "ix_seo_generation_runs_matcher_run_id",
                "seo_generation_runs",
                ["matcher_run_id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "seo_generation_runs" in tables:
        columns = _existing_columns(inspector, "seo_generation_runs")
        if "matcher_run_id" in columns:
            try:
                op.drop_index("ix_seo_generation_runs_matcher_run_id", table_name="seo_generation_runs")
            except Exception:  # pragma: no cover - best effort
                pass
            try:
                op.drop_constraint(
                    "fk_seo_generation_runs_matcher_run_id",
                    "seo_generation_runs",
                    type_="foreignkey",
                )
            except Exception:  # pragma: no cover - best effort
                pass
            op.drop_column("seo_generation_runs", "matcher_run_id")
        if "degraded_reasons" in columns:
            op.drop_column("seo_generation_runs", "degraded_reasons")
        if "quality_mode" in columns:
            op.drop_column("seo_generation_runs", "quality_mode")

    if "seo_content_versions" in tables:
        columns = _existing_columns(inspector, "seo_content_versions")
        if "matcher_run_id" in columns:
            try:
                op.drop_index("ix_seo_content_versions_matcher_run_id", table_name="seo_content_versions")
            except Exception:  # pragma: no cover
                pass
            try:
                op.drop_constraint(
                    "fk_seo_content_versions_matcher_run_id",
                    "seo_content_versions",
                    type_="foreignkey",
                )
            except Exception:  # pragma: no cover
                pass
            op.drop_column("seo_content_versions", "matcher_run_id")
        if "publishable" in columns:
            op.drop_column("seo_content_versions", "publishable")
        if "mode_used" in columns:
            op.drop_column("seo_content_versions", "mode_used")
        if "degraded_reasons" in columns:
            op.drop_column("seo_content_versions", "degraded_reasons")
        if "quality_mode" in columns:
            op.drop_column("seo_content_versions", "quality_mode")

    if "seo_sku_meaning_annotations" in tables:
        columns = _existing_columns(inspector, "seo_sku_meaning_annotations")
        if "degraded_reasons" in columns:
            op.drop_column("seo_sku_meaning_annotations", "degraded_reasons")
        if "quality_mode" in columns:
            op.drop_column("seo_sku_meaning_annotations", "quality_mode")

    if "seo_sku_query_sets" in tables:
        columns = _existing_columns(inspector, "seo_sku_query_sets")
        if "matcher_run_id" in columns:
            try:
                op.drop_index("ix_seo_sku_query_sets_matcher_run_id", table_name="seo_sku_query_sets")
            except Exception:  # pragma: no cover
                pass
            try:
                op.drop_constraint(
                    "fk_seo_sku_query_sets_matcher_run_id",
                    "seo_sku_query_sets",
                    type_="foreignkey",
                )
            except Exception:  # pragma: no cover
                pass
            op.drop_column("seo_sku_query_sets", "matcher_run_id")
        if "degraded_reasons" in columns:
            op.drop_column("seo_sku_query_sets", "degraded_reasons")
        if "quality_mode" in columns:
            op.drop_column("seo_sku_query_sets", "quality_mode")

    if "seo_matcher_results" in tables:
        op.drop_table("seo_matcher_results")
    if "seo_matcher_runs" in tables:
        try:
            op.drop_index("ix_seo_matcher_runs_scope", table_name="seo_matcher_runs")
        except Exception:  # pragma: no cover
            pass
        op.drop_table("seo_matcher_runs")
