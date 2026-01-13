"""add raw jsonb column to price_snapshots

Revision ID: 213c70612608
Revises: fc62982c8480
Create Date: 2026-01-13 18:44:52.430849

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '213c70612608'
down_revision: Union[str, None] = 'fc62982c8480'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add raw JSONB column to price_snapshots for storing full API response
    op.add_column('price_snapshots', sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    # Remove raw column from price_snapshots
    op.drop_column('price_snapshots', 'raw')
