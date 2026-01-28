"""merge heads

Revision ID: 1d906f443b16
Revises: add_ingest_schedules_and_runs, add_internal_data_tables
Create Date: 2026-01-21 11:37:33.219134

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1d906f443b16'
down_revision: Union[str, None] = ('add_ingest_schedules_and_runs', 'add_internal_data_tables')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
