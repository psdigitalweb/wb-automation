"""Evolve SEO query annotations for canonical pruning persistence.

Revision ID: 20260414_evolve_seo_query_annotations_for_canonical_pruning
Revises: 20260404_restore_remaining_seo_foundation_tables
Create Date: 2026-04-14
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "20260414_evolve_seo_query_annotations_for_canonical_pruning"
down_revision: Union[str, None] = "20260404_restore_remaining_seo_foundation_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "seo_query_annotations"
OLD_UNIQUE = "uq_seo_query_annotations_normalized_query_id"
NEW_UNIQUE = "uq_seo_query_annotations_scope_query"
NEW_FK = "fk_seo_query_annotations_normalized_query_id"
DOWNGRADE_FK = "fk_seo_query_annotations_normalized_query_id_cascade"
NEW_TEXT_INDEX = "idx_seo_query_annotations_normalized_query_text"


def _column_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {item["name"] for item in inspector.get_columns(table_name)}


def _index_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {item["name"] for item in inspector.get_indexes(table_name)}


def _unique_names(inspector: sa.Inspector, table_name: str) -> set[str]:
    return {item["name"] for item in inspector.get_unique_constraints(table_name)}


def _find_fk_name(inspector: sa.Inspector, table_name: str, constrained_column: str) -> str | None:
    for item in inspector.get_foreign_keys(table_name):
        if item.get("constrained_columns") == [constrained_column]:
            return item.get("name")
    return None


def _backfill_normalized_query_text(bind: sa.Connection) -> None:
    """Populate canonical text from normalized rows; use legacy fallback only for orphan rows."""

    bind.execute(
        sa.text(
            """
            UPDATE seo_query_annotations
            SET normalized_query_text = (
                SELECT n.normalized_query
                FROM seo_queries_normalized AS n
                WHERE n.id = seo_query_annotations.normalized_query_id
            )
            WHERE EXISTS (
                SELECT 1
                FROM seo_queries_normalized AS n
                WHERE n.id = seo_query_annotations.normalized_query_id
            )
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE seo_query_annotations
            SET normalized_query_text = ('legacy:' || CAST(id AS VARCHAR))
            WHERE (normalized_query_text IS NULL OR normalized_query_text = '')
              AND normalized_query_id IS NULL
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE seo_query_annotations
            SET normalized_query_text = ('legacy:' || CAST(id AS VARCHAR))
            WHERE (normalized_query_text IS NULL OR normalized_query_text = '')
              AND normalized_query_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM seo_queries_normalized AS n
                  WHERE n.id = seo_query_annotations.normalized_query_id
              )
            """
        )
    )


def _find_conflicting_future_canonical_keys(bind: sa.Connection, *, limit: int = 5) -> list[dict[str, object]]:
    """Return example rows that would violate future canonical uniqueness."""

    rows = bind.execute(
        sa.text(
            """
            WITH resolved AS (
                SELECT
                    a.project_id,
                    a.category_id,
                    COALESCE(NULLIF(a.normalized_query_text, ''), ('legacy:' || CAST(a.id AS VARCHAR))) AS future_key
                FROM seo_query_annotations AS a
            )
            SELECT
                project_id,
                category_id,
                future_key,
                COUNT(*) AS row_count
            FROM resolved
            GROUP BY project_id, category_id, future_key
            HAVING COUNT(*) > 1
            ORDER BY row_count DESC, project_id ASC, category_id ASC, future_key ASC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings().all()
    return [dict(row) for row in rows]


def _raise_on_conflicting_future_keys(bind: sa.Connection) -> None:
    examples = _find_conflicting_future_canonical_keys(bind)
    if not examples:
        return
    formatted = "; ".join(
        f"(project_id={item['project_id']}, category_id={item['category_id']}, normalized_query_text={item['future_key']!r}, row_count={item['row_count']})"
        for item in examples
    )
    raise RuntimeError(
        "Migration 20260414_evolve_seo_query_annotations_for_canonical_pruning cannot continue because "
        "future canonical keys would collide in seo_query_annotations. "
        f"Examples: {formatted}"
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if TABLE_NAME not in existing_tables:
        return

    columns = _column_names(inspector, TABLE_NAME)
    if "normalized_query_text" not in columns:
        op.add_column(TABLE_NAME, sa.Column("normalized_query_text", sa.Text(), nullable=True))
    if "pruning_status" not in columns:
        op.add_column(TABLE_NAME, sa.Column("pruning_status", sa.String(length=32), nullable=False, server_default=sa.text("'review'")))
    if "pruning_reason_code" not in columns:
        op.add_column(TABLE_NAME, sa.Column("pruning_reason_code", sa.String(length=64), nullable=False, server_default=sa.text("'migrated_pending'")))
    if "is_kept_for_pipeline" not in columns:
        op.add_column(TABLE_NAME, sa.Column("is_kept_for_pipeline", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    if "query_type" not in columns:
        op.add_column(TABLE_NAME, sa.Column("query_type", sa.String(length=32), nullable=False, server_default=sa.text("'tail'")))
    if "intent_type" not in columns:
        op.add_column(TABLE_NAME, sa.Column("intent_type", sa.String(length=32), nullable=False, server_default=sa.text("'unknown'")))
    if "annotation_reason_code" not in columns:
        op.add_column(TABLE_NAME, sa.Column("annotation_reason_code", sa.String(length=64), nullable=False, server_default=sa.text("'migrated_pending'")))

    _backfill_normalized_query_text(bind)
    _raise_on_conflicting_future_keys(bind)

    inspector = inspect(bind)
    old_fk_name = _find_fk_name(inspector, TABLE_NAME, "normalized_query_id")
    old_uniques = _unique_names(inspector, TABLE_NAME)
    old_indexes = _index_names(inspector, TABLE_NAME)

    with op.batch_alter_table(TABLE_NAME) as batch_op:
        if old_fk_name:
            batch_op.drop_constraint(old_fk_name, type_="foreignkey")
        if OLD_UNIQUE in old_uniques:
            batch_op.drop_constraint(OLD_UNIQUE, type_="unique")
        batch_op.alter_column("normalized_query_id", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("normalized_query_text", existing_type=sa.Text(), nullable=False)
        if NEW_UNIQUE not in old_uniques:
            batch_op.create_unique_constraint(NEW_UNIQUE, ["project_id", "category_id", "normalized_query_text"])
        batch_op.create_foreign_key(
            NEW_FK,
            "seo_queries_normalized",
            ["normalized_query_id"],
            ["id"],
            ondelete="SET NULL",
        )

    if NEW_TEXT_INDEX not in old_indexes:
        op.create_index(NEW_TEXT_INDEX, TABLE_NAME, ["normalized_query_text"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if TABLE_NAME not in existing_tables:
        return

    # Downgrade cannot represent canonical rows that no longer have a normalized_query_id,
    # so delete those rows explicitly before restoring the old non-null + unique contract.
    bind.execute(
        sa.text(
            """
            DELETE FROM seo_query_annotation_versions
            WHERE annotation_id IN (
                SELECT id
                FROM seo_query_annotations
                WHERE normalized_query_id IS NULL
            )
            """
        )
    )
    bind.execute(sa.text("DELETE FROM seo_query_annotations WHERE normalized_query_id IS NULL"))

    inspector = inspect(bind)
    fk_name = _find_fk_name(inspector, TABLE_NAME, "normalized_query_id")
    unique_names = _unique_names(inspector, TABLE_NAME)
    index_names = _index_names(inspector, TABLE_NAME)

    with op.batch_alter_table(TABLE_NAME) as batch_op:
        if fk_name:
            batch_op.drop_constraint(fk_name, type_="foreignkey")
        if NEW_UNIQUE in unique_names:
            batch_op.drop_constraint(NEW_UNIQUE, type_="unique")
        batch_op.alter_column("normalized_query_id", existing_type=sa.Integer(), nullable=False)
        if OLD_UNIQUE not in unique_names:
            batch_op.create_unique_constraint(OLD_UNIQUE, ["normalized_query_id"])
        batch_op.create_foreign_key(
            DOWNGRADE_FK,
            "seo_queries_normalized",
            ["normalized_query_id"],
            ["id"],
            ondelete="CASCADE",
        )

    if NEW_TEXT_INDEX in index_names:
        op.drop_index(NEW_TEXT_INDEX, table_name=TABLE_NAME)

    columns = _column_names(inspector, TABLE_NAME)
    for column_name in (
        "annotation_reason_code",
        "intent_type",
        "query_type",
        "is_kept_for_pipeline",
        "pruning_reason_code",
        "pruning_status",
        "normalized_query_text",
    ):
        if column_name in columns:
            op.drop_column(TABLE_NAME, column_name)
