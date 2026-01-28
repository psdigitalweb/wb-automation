"""merge heads

Revision ID: bc36e17d99c1
Revises: add_system_marketplace_settings, fix_wb_finances_grouping_001
Create Date: 2026-01-20 18:32:15.527668

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bc36e17d99c1'
down_revision: Union[str, None] = ('add_system_marketplace_settings', 'fix_wb_finances_grouping_001')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
