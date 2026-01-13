"""add app_settings table for frontend prices config

Revision ID: a2b730f4e786
Revises: ea2d9ac02904
Create Date: 2026-01-13 19:28:25.796143

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a2b730f4e786'
down_revision: Union[str, None] = 'ea2d9ac02904'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
