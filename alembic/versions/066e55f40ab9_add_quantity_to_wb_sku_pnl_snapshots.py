"""add_quantity_to_wb_sku_pnl_snapshots

Revision ID: 066e55f40ab9
Revises: add_wb_sku_pnl_001
Create Date: 2026-02-01 22:15:23.198809

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '066e55f40ab9'
down_revision: Union[str, None] = 'add_wb_sku_pnl_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'wb_sku_pnl_snapshots',
        sa.Column('quantity_sold', sa.Integer(), nullable=False, server_default='0')
    )
    op.alter_column('wb_sku_pnl_snapshots', 'quantity_sold', server_default=None)


def downgrade() -> None:
    op.drop_column('wb_sku_pnl_snapshots', 'quantity_sold')
