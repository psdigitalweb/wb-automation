"""Add internal data tables for project-scoped internal product data.

Revision ID: add_internal_data_tables
Revises: a2b730f4e786
Create Date: 2026-01-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_internal_data_tables"
down_revision: Union[str, None] = "a2b730f4e786"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

"""Add internal data tables for project-scoped internal product data.

Revision ID: add_internal_data_tables
Revises: a2b730f4e786
Create Date: 2026-01-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "add_internal_data_tables"
down_revision: Union[str, None] = "a2b730f4e786"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Project-scoped settings for internal data
    op.create_table(
        "internal_data_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "source_mode",
            sa.Text(),
            nullable=True,
        ),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("file_storage_key", sa.Text(), nullable=True),
        sa.Column("file_original_name", sa.Text(), nullable=True),
        sa.Column("file_format", sa.Text(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.Text(), nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_status", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_internal_data_settings_project_id",
        "internal_data_settings",
        ["project_id"],
    )

    # Versioned snapshots
    op.create_table(
        "internal_data_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "settings_id",
            sa.Integer(),
            sa.ForeignKey("internal_data_settings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_mode", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("file_storage_key", sa.Text(), nullable=True),
        sa.Column("file_original_name", sa.Text(), nullable=True),
        sa.Column("file_format", sa.Text(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'success'")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_unique_constraint(
        "uq_internal_data_snapshots_project_version",
        "internal_data_snapshots",
        ["project_id", "version"],
    )
    op.create_index(
        "ix_internal_data_snapshots_project_imported_at",
        "internal_data_snapshots",
        ["project_id", "imported_at"],
    )
    op.create_index(
        "ix_internal_data_snapshots_settings_id",
        "internal_data_snapshots",
        ["settings_id"],
    )

    # Internal products
    op.create_table(
        "internal_products",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey("internal_data_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("internal_sku", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("lifecycle_status", sa.Text(), nullable=True),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_unique_constraint(
        "uq_internal_products_project_snapshot_sku",
        "internal_products",
        ["project_id", "snapshot_id", "internal_sku"],
    )
    op.create_index(
        "ix_internal_products_project_sku",
        "internal_products",
        ["project_id", "internal_sku"],
    )
    op.create_index(
        "ix_internal_products_snapshot_id",
        "internal_products",
        ["snapshot_id"],
    )

    # Internal product identifiers (marketplace mappings)
    op.create_table(
        "internal_product_identifiers",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey("internal_data_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "internal_product_id",
            sa.BigInteger(),
            sa.ForeignKey("internal_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("marketplace_code", sa.Text(), nullable=False),
        sa.Column("marketplace_sku", sa.Text(), nullable=True),
        sa.Column("marketplace_item_id", sa.Text(), nullable=True),
        sa.Column("extra_identifiers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "ix_internal_ident_project_mp",
        "internal_product_identifiers",
        ["project_id", "marketplace_code"],
    )
    op.create_index(
        "ix_internal_ident_snapshot",
        "internal_product_identifiers",
        ["snapshot_id"],
    )
    # Partial unique indexes to handle NULLs correctly
    op.execute(
        """
        CREATE UNIQUE INDEX uq_internal_ident_snapshot_mp_item
        ON internal_product_identifiers (snapshot_id, marketplace_code, marketplace_item_id)
        WHERE marketplace_item_id IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_internal_ident_snapshot_mp_sku
        ON internal_product_identifiers (snapshot_id, marketplace_code, marketplace_sku)
        WHERE marketplace_sku IS NOT NULL
        """
    )

    # Internal product prices (RRP)
    op.create_table(
        "internal_product_prices",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey("internal_data_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "internal_product_id",
            sa.BigInteger(),
            sa.ForeignKey("internal_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("rrp", sa.Numeric(12, 2), nullable=True),
        sa.Column("rrp_promo", sa.Numeric(12, 2), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_unique_constraint(
        "uq_internal_product_prices_snapshot_product",
        "internal_product_prices",
        ["snapshot_id", "internal_product_id"],
    )
    op.create_index(
        "ix_internal_product_prices_project",
        "internal_product_prices",
        ["project_id"],
    )
    op.create_index(
        "ix_internal_product_prices_snapshot",
        "internal_product_prices",
        ["snapshot_id"],
    )

    # Internal product costs (COGS)
    op.create_table(
        "internal_product_costs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey("internal_data_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "internal_product_id",
            sa.BigInteger(),
            sa.ForeignKey("internal_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("currency", sa.Text(), nullable=True),
        sa.Column("cost", sa.Numeric(12, 4), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_unique_constraint(
        "uq_internal_product_costs_snapshot_product",
        "internal_product_costs",
        ["snapshot_id", "internal_product_id"],
    )
    op.create_index(
        "ix_internal_product_costs_project",
        "internal_product_costs",
        ["project_id"],
    )
    op.create_index(
        "ix_internal_product_costs_snapshot",
        "internal_product_costs",
        ["snapshot_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_internal_product_costs_snapshot", table_name="internal_product_costs")
    op.drop_index("ix_internal_product_costs_project", table_name="internal_product_costs")
    op.drop_constraint(
        "uq_internal_product_costs_snapshot_product",
        "internal_product_costs",
        type_="unique",
    )
    op.drop_table("internal_product_costs")

    op.drop_index("ix_internal_product_prices_snapshot", table_name="internal_product_prices")
    op.drop_index("ix_internal_product_prices_project", table_name="internal_product_prices")
    op.drop_constraint(
        "uq_internal_product_prices_snapshot_product",
        "internal_product_prices",
        type_="unique",
    )
    op.drop_table("internal_product_prices")

    op.execute("DROP INDEX IF EXISTS uq_internal_ident_snapshot_mp_sku")
    op.execute("DROP INDEX IF EXISTS uq_internal_ident_snapshot_mp_item")
    op.drop_index("ix_internal_ident_snapshot", table_name="internal_product_identifiers")
    op.drop_index("ix_internal_ident_project_mp", table_name="internal_product_identifiers")
    op.drop_table("internal_product_identifiers")

    op.drop_index("ix_internal_products_snapshot_id", table_name="internal_products")
    op.drop_index("ix_internal_products_project_sku", table_name="internal_products")
    op.drop_constraint(
        "uq_internal_products_project_snapshot_sku",
        "internal_products",
        type_="unique",
    )
    op.drop_table("internal_products")

    op.drop_index("ix_internal_data_snapshots_settings_id", table_name="internal_data_snapshots")
    op.drop_index(
        "ix_internal_data_snapshots_project_imported_at",
        table_name="internal_data_snapshots",
    )
    op.drop_constraint(
        "uq_internal_data_snapshots_project_version",
        "internal_data_snapshots",
        type_="unique",
    )
    op.drop_table("internal_data_snapshots")

    op.drop_index("ix_internal_data_settings_project_id", table_name="internal_data_settings")
    op.drop_table("internal_data_settings")

