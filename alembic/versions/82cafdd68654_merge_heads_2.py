"""merge heads 2

Revision ID: 82cafdd68654
Revises: 1d906f443b16, add_wb_curr_hist
Create Date: 2026-01-21 13:07:45.223381

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82cafdd68654'
down_revision: Union[str, None] = ('1d906f443b16', 'add_wb_curr_hist')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
