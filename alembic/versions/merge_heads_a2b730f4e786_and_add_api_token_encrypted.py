"""merge heads: a2b730f4e786 and e373f63d276a

Revision ID: 670ed0736bfa
Revises: a2b730f4e786, e373f63d276a
Create Date: 2026-01-16 19:00:00.000000

This is a merge migration that combines two branches:
- a2b730f4e786: app_settings table (from ea2d9ac02904 branch)
- e373f63d276a: api_token_encrypted field (from 946d21840243 branch)

After this merge, there will be a single linear HEAD.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '670ed0736bfa'
down_revision: Union[str, None, tuple] = ('a2b730f4e786', 'e373f63d276a')  # Merge two heads
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Merge migration: no schema changes needed
    # Both branches are already applied independently
    # This migration just creates a single linear history
    pass


def downgrade() -> None:
    # Merge migration: no schema changes to revert
    pass

