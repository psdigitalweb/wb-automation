"""add marketplace-neutral product identity foundation

Revision ID: 20260731_marketplace_identity
Revises: 20260731_wb_competitor_analysis
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260731_marketplace_identity"
down_revision: Union[str, None] = "20260731_wb_competitor_analysis"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_project_marketplaces_project_id_id",
        "project_marketplaces",
        ["project_id", "id"],
    )
    op.create_table(
        "marketplace_products",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("project_marketplace_id", sa.Integer(), nullable=False),
        sa.Column("marketplace_item_id", sa.Text(), nullable=False),
        sa.Column("marketplace_sku", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("attributes", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "project_marketplace_id",
            "marketplace_item_id",
            name="uq_marketplace_products_connection_item",
        ),
        sa.UniqueConstraint(
            "project_id",
            "id",
            name="uq_marketplace_products_project_id_id",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "project_marketplace_id"],
            ["project_marketplaces.project_id", "project_marketplaces.id"],
            name="fk_marketplace_products_project_connection",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "btrim(marketplace_item_id) <> ''",
            name="ck_marketplace_products_item_not_blank",
        ),
    )
    op.create_index(
        "ix_marketplace_products_project",
        "marketplace_products",
        ["project_id"],
    )
    op.create_index(
        "ix_marketplace_products_connection_sku",
        "marketplace_products",
        ["project_marketplace_id", "marketplace_sku"],
        postgresql_where=sa.text("marketplace_sku IS NOT NULL"),
    )

    op.create_table(
        "internal_catalog_products",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("internal_sku", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("attributes", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "project_id",
            "internal_sku",
            name="uq_internal_catalog_products_project_sku",
        ),
        sa.UniqueConstraint(
            "project_id",
            "id",
            name="uq_internal_catalog_products_project_id_id",
        ),
        sa.CheckConstraint(
            "btrim(internal_sku) <> ''",
            name="ck_internal_catalog_products_sku_not_blank",
        ),
    )
    op.create_index(
        "ix_internal_catalog_products_project",
        "internal_catalog_products",
        ["project_id"],
    )

    op.create_table(
        "marketplace_product_mappings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("marketplace_product_id", sa.BigInteger(), nullable=False),
        sa.Column("internal_catalog_product_id", sa.BigInteger(), nullable=False),
        sa.Column("mapping_source", sa.String(32), nullable=False),
        sa.Column("mapping_status", sa.String(24), nullable=False, server_default="proposed"),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "marketplace_product_id",
            name="uq_marketplace_product_mappings_marketplace_product",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "marketplace_product_id"],
            ["marketplace_products.project_id", "marketplace_products.id"],
            name="fk_marketplace_product_mappings_project_marketplace_product",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "internal_catalog_product_id"],
            ["internal_catalog_products.project_id", "internal_catalog_products.id"],
            name="fk_marketplace_product_mappings_project_internal_product",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "mapping_status IN ('proposed','confirmed','rejected')",
            name="ck_marketplace_product_mappings_status",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_marketplace_product_mappings_confidence",
        ),
    )
    op.create_index(
        "ix_marketplace_product_mappings_project",
        "marketplace_product_mappings",
        ["project_id"],
    )
    op.create_index(
        "ix_marketplace_product_mappings_internal_product",
        "marketplace_product_mappings",
        ["internal_catalog_product_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_marketplace_product_mappings_internal_product",
        table_name="marketplace_product_mappings",
    )
    op.drop_index(
        "ix_marketplace_product_mappings_project",
        table_name="marketplace_product_mappings",
    )
    op.drop_table("marketplace_product_mappings")

    op.drop_index(
        "ix_internal_catalog_products_project",
        table_name="internal_catalog_products",
    )
    op.drop_table("internal_catalog_products")

    op.drop_index(
        "ix_marketplace_products_connection_sku",
        table_name="marketplace_products",
    )
    op.drop_index("ix_marketplace_products_project", table_name="marketplace_products")
    op.drop_table("marketplace_products")
    op.drop_constraint(
        "uq_project_marketplaces_project_id_id",
        "project_marketplaces",
        type_="unique",
    )
