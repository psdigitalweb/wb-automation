"""make marketplace SKU normalization connection-specific

Revision ID: 20260731_sku_norm_policy
Revises: 20260731_product_mapping_sync
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260731_sku_norm_policy"
down_revision: Union[str, None] = "20260731_product_mapping_sync"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The default product identity policy is exact SKU matching. Project 1 is
    # the known legacy WB connection whose seller SKU has an account prefix
    # such as ``103/ZKNS-0079``. Store that exception as connection data rather
    # than applying the transformation to every project and marketplace.
    op.execute(
        """
        UPDATE project_marketplaces pm
        SET settings_json = jsonb_set(
                COALESCE(pm.settings_json, '{}'::jsonb),
                '{product_identity}',
                COALESCE(pm.settings_json->'product_identity', '{}'::jsonb)
                    || '{"sku_normalization":"strip_prefix_before_last_slash"}'::jsonb,
                TRUE
            ),
            updated_at = now()
        FROM marketplaces m
        WHERE pm.marketplace_id = m.id
          AND pm.project_id = 1
          AND m.code = 'wildberries'
          AND pm.settings_json #> '{product_identity,sku_normalization}' IS NULL
        """
    )

    op.drop_index(
        "ix_marketplace_products_project_sku_normalized",
        table_name="marketplace_products",
    )
    op.execute(
        """
        CREATE INDEX ix_marketplace_products_project_sku_normalized
        ON marketplace_products (project_id, lower(btrim(marketplace_sku)))
        WHERE marketplace_sku IS NOT NULL
        """
    )

    from app.services.product_mapping_sync import reconcile_all_project_product_mappings

    reconcile_all_project_product_mappings(op.get_bind())
    op.execute(
        """
        UPDATE marketplace_product_mappings mapping
        SET mapping_source = 'marketplace_sku_rule',
            metadata = COALESCE(mapping.metadata, '{}'::jsonb)
                || '{"sku_normalization":"strip_prefix_before_last_slash"}'::jsonb,
            updated_at = now()
        FROM marketplace_products mp
        JOIN project_marketplaces pm
          ON pm.id = mp.project_marketplace_id
         AND pm.project_id = mp.project_id
        JOIN marketplaces m ON m.id = pm.marketplace_id
        WHERE mapping.marketplace_product_id = mp.id
          AND mapping.project_id = 1
          AND mapping.mapping_status = 'proposed'
          AND mapping.mapping_source = 'exact_marketplace_sku'
          AND m.code = 'wildberries'
        """
    )


def downgrade() -> None:
    # Connection settings and mapping rows are business data, so they are
    # intentionally preserved. Only restore the previous index definition.
    op.drop_index(
        "ix_marketplace_products_project_sku_normalized",
        table_name="marketplace_products",
    )
    op.execute(
        """
        CREATE INDEX ix_marketplace_products_project_sku_normalized
        ON marketplace_products (
            project_id,
            lower(NULLIF(regexp_replace(trim(both '/' from marketplace_sku), '^.*/', ''), ''))
        )
        WHERE marketplace_sku IS NOT NULL
        """
    )
