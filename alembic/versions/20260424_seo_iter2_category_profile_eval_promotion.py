"""SEO iteration 2 — category profile, eval-as-a-gate, generation promotion lifecycle, compare verdicts.

Revision ID: 20260424_seo_iter2_category_profile_eval_promotion
Revises: 20260423_seo_iter1_quality_mode_and_matcher_runs
Create Date: 2026-04-24

Additive-only migration. Adds:

* ``seo_category_profiles`` — versioned category-calibrated profile (WS-C).
* ``seo_eval_labels`` and ``seo_eval_runs`` — eval harness storage (WS-E).
* ``seo_generation_human_review`` — required artifact for promotion (WS-D).
* ``seo_compare_verdicts`` — operator verdicts captured from the compare layer.

It also adds new columns:

* ``SeoCategoryMatchingReadiness.eligibility_tier`` (single-writer = eval).
* ``SeoSkuQuerySet.approval_state`` / ``trust_state`` / ``category_profile_version``.
* ``SeoContentVersion.category_profile_version``.

The ``content_kind`` enum is widened informally (it remains a free string column);
the migration also rewrites historical ``llm_draft`` values to the iteration-2
``preview`` label so the lifecycle vocabulary is consistent.

No drops, no FK changes on existing rows. Legacy NULLs are preserved.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "20260424_seo_iter2_category_profile_eval_promotion"
down_revision: Union[str, None] = "20260423_seo_iter1_quality_mode_and_matcher_runs"
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


def _json_default_array() -> sa.TextClause:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return sa.text("'[]'::jsonb")
    return sa.text("'[]'")


def _existing_columns(inspector, table: str) -> set[str]:
    return {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    # ---- New tables ----

    if "seo_category_profiles" not in tables:
        op.create_table(
            "seo_category_profiles",
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
            sa.Column("version", sa.String(length=64), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false"), index=True),
            sa.Column("payload", _json_type(), nullable=False, server_default=_json_default_object()),
            sa.Column("source_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint(
                "project_id", "category_id", "version", name="uq_seo_category_profiles_scope_version"
            ),
        )

    if "seo_eval_labels" not in tables:
        op.create_table(
            "seo_eval_labels",
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
            sa.Column("label_set_id", sa.Integer(), nullable=False, index=True),
            sa.Column("query_text_normalized", sa.Text(), nullable=False),
            sa.Column("nm_id", sa.Integer(), nullable=True, index=True),
            sa.Column("expected_bucket", sa.String(length=32), nullable=False),
            sa.Column("expected_reason", sa.Text(), nullable=True),
            sa.Column(
                "source",
                sa.String(length=64),
                nullable=False,
                server_default="comparison_csv_812",
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint(
                "project_id",
                "category_id",
                "label_set_id",
                "query_text_normalized",
                "nm_id",
                name="uq_seo_eval_labels_scope_query_nm",
            ),
        )
        op.create_index(
            "ix_seo_eval_labels_set_query",
            "seo_eval_labels",
            ["label_set_id", "query_text_normalized"],
        )

    if "seo_eval_runs" not in tables:
        op.create_table(
            "seo_eval_runs",
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
            sa.Column("label_set_id", sa.Integer(), nullable=False, index=True),
            sa.Column("metrics", _json_type(), nullable=False, server_default=_json_default_object()),
            sa.Column("thresholds", _json_type(), nullable=False, server_default=_json_default_object()),
            sa.Column(
                "verdict",
                sa.String(length=32),
                nullable=False,
                server_default="preview_only",
            ),
            sa.Column(
                "matcher_run_ids",
                _json_type(),
                nullable=False,
                server_default=_json_default_array(),
            ),
            sa.Column("nm_ids", _json_type(), nullable=False, server_default=_json_default_array()),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=128), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_seo_eval_runs_scope",
            "seo_eval_runs",
            ["project_id", "category_id"],
        )

    if "seo_generation_human_review" not in tables:
        op.create_table(
            "seo_generation_human_review",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "content_version_id",
                sa.Integer(),
                sa.ForeignKey("seo_content_versions.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("reviewer", sa.String(length=128), nullable=True),
            sa.Column("rubric", _json_type(), nullable=False, server_default=_json_default_object()),
            sa.Column("verdict", sa.String(length=32), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_seo_generation_human_review_content",
            "seo_generation_human_review",
            ["content_version_id", "created_at"],
        )

    if "seo_compare_verdicts" not in tables:
        op.create_table(
            "seo_compare_verdicts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "project_id",
                sa.Integer(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("subject_type", sa.String(length=32), nullable=False),
            sa.Column("subject_id", sa.Integer(), nullable=False, index=True),
            sa.Column("related_id", sa.Integer(), nullable=True),
            sa.Column("verdict", sa.String(length=32), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=128), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "ix_seo_compare_verdicts_subject",
            "seo_compare_verdicts",
            ["subject_type", "subject_id", "created_at"],
        )

    # Refresh inspector after table creates.
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    # ---- Additive columns on existing tables ----

    if "seo_category_matching_readiness" in tables:
        cols = _existing_columns(inspector, "seo_category_matching_readiness")
        if "eligibility_tier" not in cols:
            op.add_column(
                "seo_category_matching_readiness",
                sa.Column(
                    "eligibility_tier",
                    sa.String(length=32),
                    nullable=False,
                    server_default="preview_only",
                ),
            )

    if "seo_sku_query_sets" in tables:
        cols = _existing_columns(inspector, "seo_sku_query_sets")
        if "approval_state" not in cols:
            op.add_column(
                "seo_sku_query_sets",
                sa.Column(
                    "approval_state",
                    sa.String(length=32),
                    nullable=False,
                    server_default="draft",
                ),
            )
        if "trust_state" not in cols:
            op.add_column(
                "seo_sku_query_sets",
                sa.Column(
                    "trust_state",
                    sa.String(length=32),
                    nullable=False,
                    server_default="unverified",
                ),
            )
        if "category_profile_version" not in cols:
            op.add_column(
                "seo_sku_query_sets",
                sa.Column("category_profile_version", sa.String(length=64), nullable=True),
            )
        # Backfill iteration-1 confirmed rows to ``approval_state='candidate'``
        # so the candidate path can read them as the implicit candidate set
        # without losing the historical "confirmed" semantic.
        op.execute(
            sa.text(
                "UPDATE seo_sku_query_sets "
                "SET approval_state = 'candidate' "
                "WHERE status = 'confirmed' AND approval_state = 'draft'"
            )
        )

    if "seo_content_versions" in tables:
        cols = _existing_columns(inspector, "seo_content_versions")
        if "category_profile_version" not in cols:
            op.add_column(
                "seo_content_versions",
                sa.Column("category_profile_version", sa.String(length=64), nullable=True),
            )
        # Iteration 2: rewrite the legacy ``llm_draft`` content_kind tag to
        # the new ``preview`` label so lifecycle queries are consistent.
        op.execute(
            sa.text(
                "UPDATE seo_content_versions "
                "SET content_kind = 'preview' "
                "WHERE content_kind = 'llm_draft'"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "seo_content_versions" in tables:
        cols = _existing_columns(inspector, "seo_content_versions")
        if "category_profile_version" in cols:
            op.drop_column("seo_content_versions", "category_profile_version")

    if "seo_sku_query_sets" in tables:
        cols = _existing_columns(inspector, "seo_sku_query_sets")
        if "category_profile_version" in cols:
            op.drop_column("seo_sku_query_sets", "category_profile_version")
        if "trust_state" in cols:
            op.drop_column("seo_sku_query_sets", "trust_state")
        if "approval_state" in cols:
            op.drop_column("seo_sku_query_sets", "approval_state")

    if "seo_category_matching_readiness" in tables:
        cols = _existing_columns(inspector, "seo_category_matching_readiness")
        if "eligibility_tier" in cols:
            op.drop_column("seo_category_matching_readiness", "eligibility_tier")

    if "seo_compare_verdicts" in tables:
        try:
            op.drop_index("ix_seo_compare_verdicts_subject", table_name="seo_compare_verdicts")
        except Exception:  # pragma: no cover - best effort
            pass
        op.drop_table("seo_compare_verdicts")

    if "seo_generation_human_review" in tables:
        try:
            op.drop_index(
                "ix_seo_generation_human_review_content",
                table_name="seo_generation_human_review",
            )
        except Exception:  # pragma: no cover
            pass
        op.drop_table("seo_generation_human_review")

    if "seo_eval_runs" in tables:
        try:
            op.drop_index("ix_seo_eval_runs_scope", table_name="seo_eval_runs")
        except Exception:  # pragma: no cover
            pass
        op.drop_table("seo_eval_runs")

    if "seo_eval_labels" in tables:
        try:
            op.drop_index("ix_seo_eval_labels_set_query", table_name="seo_eval_labels")
        except Exception:  # pragma: no cover
            pass
        op.drop_table("seo_eval_labels")

    if "seo_category_profiles" in tables:
        op.drop_table("seo_category_profiles")
