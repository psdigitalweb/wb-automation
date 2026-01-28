"""Add mapping_json column to internal_data_settings for Internal Data mappings.

Revision ID: add_internal_data_mapping_json
Revises: 82cafdd68654
Create Date: 2026-01-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_internal_data_mapping_json"
down_revision: Union[str, None] = "82cafdd68654"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "internal_data_settings",
        sa.Column(
            "mapping_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("internal_data_settings", "mapping_json")

