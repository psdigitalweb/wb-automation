"""add project_frontend_brand_pool table

Revision ID: a1b2c3d4e5f6
Revises: 87cbcbbc8c60
Create Date: 2026-02-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "87cbcbbc8c60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_frontend_brand_pool",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id", "brand_id"),
    )
    op.create_index(
        "ix_project_frontend_brand_pool_project_id",
        "project_frontend_brand_pool",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_frontend_brand_pool_project_id",
        table_name="project_frontend_brand_pool",
    )
    op.drop_table("project_frontend_brand_pool")
