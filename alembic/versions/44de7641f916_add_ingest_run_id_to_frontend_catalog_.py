"""add ingest_run_id to frontend catalog price snapshots

Revision ID: 44de7641f916
Revises: 9c0d4e2c6a1f
Create Date: 2026-01-28 12:05:43.857048

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '44de7641f916'
down_revision: Union[str, None] = '9c0d4e2c6a1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "frontend_catalog_price_snapshots",
        sa.Column("ingest_run_id", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_front_price_snapshots_ingest_run_id",
        "frontend_catalog_price_snapshots",
        ["ingest_run_id"],
    )
    op.create_foreign_key(
        "fk_front_price_snapshots_ingest_run_id__ingest_runs",
        "frontend_catalog_price_snapshots",
        "ingest_runs",
        ["ingest_run_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_front_price_snapshots_ingest_run_id__ingest_runs",
        "frontend_catalog_price_snapshots",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_front_price_snapshots_ingest_run_id",
        table_name="frontend_catalog_price_snapshots",
    )
    op.drop_column("frontend_catalog_price_snapshots", "ingest_run_id")
