"""widen alembic_version.version_num to text

Revision ID: a9f3c1d0b2e4
Revises: add_params_json_to_ingest_runs
Create Date: 2026-01-27

PostgreSQL: widen alembic_version.version_num to TEXT so long revision ids work.
No data is dropped.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a9f3c1d0b2e4"
down_revision: Union[str, None] = "add_params_json_to_ingest_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # alembic_version is created by Alembic; be defensive for fresh DBs.
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    if "alembic_version" not in inspector.get_table_names():
        return

    # VARCHAR(N) -> TEXT is safe in Postgres and preserves existing value.
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE TEXT")


def downgrade() -> None:
    # Do not attempt to shrink the column (could truncate existing revision ids).
    pass

