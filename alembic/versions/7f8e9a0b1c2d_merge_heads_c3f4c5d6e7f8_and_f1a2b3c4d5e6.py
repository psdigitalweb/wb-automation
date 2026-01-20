"""Merge heads: c3f4c5d6e7f8 and f1a2b3c4d5e6

Revision ID: 7f8e9a0b1c2d
Revises: c3f4c5d6e7f8, f1a2b3c4d5e6
Create Date: 2026-01-20 15:30:00.000000

This merge migration joins the branches that end at:
- c3f4c5d6e7f8: marketplace_api_snapshots table
- f1a2b3c4d5e6: articles_base indexes and vendor_code_norm

After this migration there will be a single linear HEAD.
"""

from typing import Sequence, Union

from alembic import op  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = "7f8e9a0b1c2d"
down_revision: Union[str, None, tuple] = ("c3f4c5d6e7f8", "f1a2b3c4d5e6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge migration; no schema changes required."""
    pass


def downgrade() -> None:
    """Split merge; no schema changes to revert."""
    pass

