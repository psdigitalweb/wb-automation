"""merge_heads_084c9172e403_and_a1b2c3d4e5f6

Revision ID: d112ea543439
Revises: 084c9172e403, a1b2c3d4e5f6
Create Date: 2026-02-09 17:06:52.728349

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd112ea543439'
down_revision: Union[str, None] = ('084c9172e403', 'a1b2c3d4e5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
