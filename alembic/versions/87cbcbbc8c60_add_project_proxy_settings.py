"""add_project_proxy_settings

Revision ID: 87cbcbbc8c60
Revises: 44de7641f916
Create Date: 2026-01-30 17:30:12.988637

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '87cbcbbc8c60'
down_revision: Union[str, None] = '44de7641f916'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_proxy_settings",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("scheme", sa.Text(), server_default=sa.text("'http'"), nullable=False),
        sa.Column("host", sa.Text(), server_default=sa.text("''"), nullable=False),
        sa.Column("port", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("rotate_mode", sa.Text(), server_default=sa.text("'fixed'"), nullable=False),
        sa.Column(
            "test_url",
            sa.Text(),
            server_default=sa.text("'https://www.wildberries.ru'"),
            nullable=False,
        ),
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("last_test_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("project_id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("project_proxy_settings")
