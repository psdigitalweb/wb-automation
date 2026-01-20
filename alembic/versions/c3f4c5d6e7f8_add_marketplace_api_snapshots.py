"""add marketplace_api_snapshots table for marketplace-level API snapshots

Revision ID: c3f4c5d6e7f8
Revises: 6089711fc16b
Create Date: 2026-01-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c3f4c5d6e7f8"
down_revision: Union[str, None] = "6089711fc16b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "marketplace_api_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, nullable=False),
        sa.Column("marketplace_code", sa.Text(), nullable=False),
        sa.Column("data_domain", sa.Text(), nullable=False),
        sa.Column("data_type", sa.Text(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=True),
        sa.Column("locale", sa.Text(), nullable=True),
        sa.Column("request_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("http_status", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )

    # Unique constraint to avoid duplicates for same logical slice & payload
    op.create_index(
        "uq_marketplace_api_snapshots_latest",
        "marketplace_api_snapshots",
        [
            "marketplace_code",
            "data_domain",
            "data_type",
            "as_of_date",
            "locale",
            "payload_hash",
        ],
        unique=True,
    )

    # Index to efficiently fetch latest snapshot
    op.create_index(
        "ix_marketplace_api_snapshots_latest_lookup",
        "marketplace_api_snapshots",
        [
            "marketplace_code",
            "data_domain",
            "data_type",
            "as_of_date",
            "locale",
            sa.text("fetched_at DESC"),
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_marketplace_api_snapshots_latest_lookup",
        table_name="marketplace_api_snapshots",
    )
    op.drop_index(
        "uq_marketplace_api_snapshots_latest",
        table_name="marketplace_api_snapshots",
    )
    op.drop_table("marketplace_api_snapshots")

