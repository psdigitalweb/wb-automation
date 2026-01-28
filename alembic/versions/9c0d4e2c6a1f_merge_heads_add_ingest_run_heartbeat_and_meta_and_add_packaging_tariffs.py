"""merge heads: add_ingest_run_heartbeat_and_meta and add_packaging_tariffs

Revision ID: 9c0d4e2c6a1f
Revises: add_ingest_run_heartbeat_and_meta, add_packaging_tariffs
Create Date: 2026-01-27

This is a merge migration to resolve multiple-head Alembic graph.
It contains no schema changes and is safe (no drops).
"""

from typing import Sequence, Union

from alembic import op  # noqa: F401


# revision identifiers, used by Alembic.
revision: str = "9c0d4e2c6a1f"
down_revision: Union[str, None, tuple] = ("add_ingest_run_heartbeat_and_meta", "add_packaging_tariffs")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

