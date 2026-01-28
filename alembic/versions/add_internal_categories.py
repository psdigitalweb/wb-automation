"""Add internal categories support for Internal Data.

Revision ID: add_internal_categories
Revises: add_additional_cost_entries
Create Date: 2026-01-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_internal_categories"
down_revision: Union[str, None] = "add_additional_cost_entries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create internal_categories table
    op.create_table(
        "internal_categories",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "parent_id",
            sa.BigInteger(),
            sa.ForeignKey("internal_categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "meta_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    
    # Create indexes and unique constraint
    op.create_index(
        "ix_internal_categories_project_id",
        "internal_categories",
        ["project_id"],
    )
    op.create_index(
        "ix_internal_categories_project_parent",
        "internal_categories",
        ["project_id", "parent_id"],
    )
    op.create_unique_constraint(
        "uq_internal_categories_project_key",
        "internal_categories",
        ["project_id", "key"],
    )
    
    # Add internal_category_id column to internal_products
    op.add_column(
        "internal_products",
        sa.Column("internal_category_id", sa.BigInteger(), nullable=True),
    )
    
    # Create foreign key and index
    op.create_foreign_key(
        "fk_internal_products_category_id",
        "internal_products",
        "internal_categories",
        ["internal_category_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_internal_products_category_id",
        "internal_products",
        ["internal_category_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_internal_products_category_id", table_name="internal_products")
    op.drop_constraint(
        "fk_internal_products_category_id",
        "internal_products",
        type_="foreignkey",
    )
    op.drop_column("internal_products", "internal_category_id")
    
    op.drop_constraint(
        "uq_internal_categories_project_key",
        "internal_categories",
        type_="unique",
    )
    op.drop_index("ix_internal_categories_project_parent", table_name="internal_categories")
    op.drop_index("ix_internal_categories_project_id", table_name="internal_categories")
    op.drop_table("internal_categories")
