"""Synchronize the optional internal catalog with marketplace product identities."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.db import engine


def _sync_on_connection(
    conn: Connection,
    *,
    project_id: int,
    snapshot_id: Optional[int],
) -> dict[str, Any]:
    if snapshot_id is None:
        snapshot_id = conn.execute(
            text(
                """
                SELECT id
                FROM internal_data_snapshots
                WHERE project_id = :project_id
                  AND status IN ('success', 'partial')
                ORDER BY imported_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"project_id": int(project_id)},
        ).scalar()
    if snapshot_id is None:
        return {
            "status": "skipped_without_catalog",
            "snapshot_id": None,
            "catalog_products_upserted": 0,
            "confirmed_mappings_upserted": 0,
            "proposed_mappings_created": 0,
        }

    snapshot_id = int(snapshot_id)
    params = {"project_id": int(project_id), "snapshot_id": snapshot_id}
    snapshot_exists = conn.execute(
        text(
            """
            SELECT 1
            FROM internal_data_snapshots
            WHERE id = :snapshot_id AND project_id = :project_id
            """
        ),
        params,
    ).scalar()
    if snapshot_exists is None:
        raise ValueError(f"snapshot_id={snapshot_id} does not belong to project_id={project_id}")

    catalog_result = conn.execute(
        text(
            """
            MERGE INTO internal_catalog_products AS target
            USING (
                SELECT DISTINCT ON (ip.internal_sku)
                    ip.project_id,
                    btrim(ip.internal_sku) AS internal_sku,
                    ip.name,
                    ip.attributes
                FROM internal_products ip
                WHERE ip.project_id = :project_id
                  AND ip.snapshot_id = :snapshot_id
                  AND NULLIF(btrim(ip.internal_sku), '') IS NOT NULL
                ORDER BY ip.internal_sku, ip.id DESC
            ) AS source
            ON target.project_id = source.project_id
           AND target.internal_sku = source.internal_sku
            WHEN MATCHED AND (
                target.name IS DISTINCT FROM source.name
                OR target.attributes IS DISTINCT FROM source.attributes
            ) THEN UPDATE SET
                name = source.name,
                attributes = source.attributes,
                updated_at = now()
            WHEN NOT MATCHED THEN
                INSERT (project_id, internal_sku, name, attributes)
                VALUES (source.project_id, source.internal_sku, source.name, source.attributes)
            """
        ),
        params,
    )

    confirmed_result = conn.execute(
        text(
            """
            WITH explicit_candidates AS (
                SELECT DISTINCT
                    mp.id AS marketplace_product_id,
                    icp.id AS internal_catalog_product_id
                FROM internal_product_identifiers ipi
                JOIN internal_products ip
                  ON ip.id = ipi.internal_product_id
                 AND ip.snapshot_id = ipi.snapshot_id
                 AND ip.project_id = ipi.project_id
                JOIN internal_catalog_products icp
                  ON icp.project_id = ip.project_id
                 AND icp.internal_sku = btrim(ip.internal_sku)
                JOIN marketplaces m ON m.code = lower(btrim(ipi.marketplace_code))
                JOIN project_marketplaces pm
                  ON pm.project_id = ipi.project_id
                 AND pm.marketplace_id = m.id
                 AND pm.is_enabled = TRUE
                JOIN marketplace_products mp
                  ON mp.project_id = ipi.project_id
                 AND mp.project_marketplace_id = pm.id
                 AND (
                    ipi.marketplace_item_id IS NULL
                    OR mp.marketplace_item_id = btrim(ipi.marketplace_item_id)
                 )
                 AND (
                    ipi.marketplace_sku IS NULL
                    OR lower(NULLIF(
                        CASE COALESCE(
                            pm.settings_json #>> '{product_identity,sku_normalization}',
                            'exact'
                        )
                            WHEN 'strip_prefix_before_last_slash'
                                THEN regexp_replace(trim(both '/' from mp.marketplace_sku), '^.*/', '')
                            ELSE btrim(mp.marketplace_sku)
                        END,
                        ''
                    )) = lower(NULLIF(
                        CASE COALESCE(
                            pm.settings_json #>> '{product_identity,sku_normalization}',
                            'exact'
                        )
                            WHEN 'strip_prefix_before_last_slash'
                                THEN regexp_replace(trim(both '/' from ipi.marketplace_sku), '^.*/', '')
                            ELSE btrim(ipi.marketplace_sku)
                        END,
                        ''
                    ))
                 )
                WHERE ipi.project_id = :project_id
                  AND ipi.snapshot_id = :snapshot_id
                  AND (ipi.marketplace_item_id IS NOT NULL OR ipi.marketplace_sku IS NOT NULL)
            ), unambiguous AS (
                SELECT
                    marketplace_product_id,
                    MIN(internal_catalog_product_id) AS internal_catalog_product_id
                FROM explicit_candidates
                GROUP BY marketplace_product_id
                HAVING COUNT(DISTINCT internal_catalog_product_id) = 1
            )
            INSERT INTO marketplace_product_mappings (
                project_id,
                marketplace_product_id,
                internal_catalog_product_id,
                mapping_source,
                mapping_status,
                confidence,
                metadata
            )
            SELECT
                :project_id,
                u.marketplace_product_id,
                u.internal_catalog_product_id,
                'catalog_identifier',
                'confirmed',
                1.0,
                jsonb_build_object('snapshot_id', :snapshot_id)
            FROM unambiguous u
            ON CONFLICT (marketplace_product_id)
            DO UPDATE SET
                internal_catalog_product_id = EXCLUDED.internal_catalog_product_id,
                mapping_source = EXCLUDED.mapping_source,
                mapping_status = EXCLUDED.mapping_status,
                confidence = EXCLUDED.confidence,
                metadata = EXCLUDED.metadata,
                updated_at = now()
            WHERE marketplace_product_mappings.mapping_status = 'proposed'
              AND marketplace_product_mappings.mapping_source <> 'manual'
            """
        ),
        params,
    )

    proposed_result = conn.execute(
        text(
            """
            WITH catalog_scope AS MATERIALIZED (
                SELECT DISTINCT
                    icp.id,
                    lower(btrim(icp.internal_sku)) AS sku_key
                FROM internal_products ip
                JOIN internal_catalog_products icp
                  ON icp.project_id = ip.project_id
                 AND icp.internal_sku = btrim(ip.internal_sku)
                WHERE ip.project_id = :project_id
                  AND ip.snapshot_id = :snapshot_id
                  AND NULLIF(btrim(ip.internal_sku), '') IS NOT NULL
            ), unique_catalog AS MATERIALIZED (
                SELECT sku_key, MIN(id) AS internal_catalog_product_id
                FROM catalog_scope
                GROUP BY sku_key
                HAVING COUNT(DISTINCT id) = 1
            ), explicit_product_keys AS MATERIALIZED (
                SELECT DISTINCT
                    pm.id AS project_marketplace_id,
                    btrim(ipi.marketplace_item_id) AS marketplace_item_id,
                    lower(NULLIF(
                        CASE COALESCE(
                            pm.settings_json #>> '{product_identity,sku_normalization}',
                            'exact'
                        )
                            WHEN 'strip_prefix_before_last_slash'
                                THEN regexp_replace(trim(both '/' from ipi.marketplace_sku), '^.*/', '')
                            ELSE btrim(ipi.marketplace_sku)
                        END,
                        ''
                    )) AS marketplace_sku_key
                FROM internal_product_identifiers ipi
                JOIN marketplaces m ON m.code = lower(btrim(ipi.marketplace_code))
                JOIN project_marketplaces pm
                  ON pm.project_id = ipi.project_id
                 AND pm.marketplace_id = m.id
                WHERE ipi.project_id = :project_id
                  AND ipi.snapshot_id = :snapshot_id
                  AND (ipi.marketplace_item_id IS NOT NULL OR ipi.marketplace_sku IS NOT NULL)
            ), unmapped_products AS MATERIALIZED (
                SELECT
                    mp.id,
                    mp.project_marketplace_id,
                    mp.marketplace_item_id,
                    COALESCE(
                        pm.settings_json #>> '{product_identity,sku_normalization}',
                        'exact'
                    ) AS sku_normalization,
                    lower(NULLIF(
                        CASE COALESCE(
                            pm.settings_json #>> '{product_identity,sku_normalization}',
                            'exact'
                        )
                            WHEN 'strip_prefix_before_last_slash'
                                THEN regexp_replace(trim(both '/' from mp.marketplace_sku), '^.*/', '')
                            ELSE btrim(mp.marketplace_sku)
                        END,
                        ''
                    )) AS marketplace_sku_key
                FROM marketplace_products mp
                JOIN project_marketplaces pm
                  ON pm.id = mp.project_marketplace_id
                 AND pm.project_id = mp.project_id
                LEFT JOIN marketplace_product_mappings mapping
                  ON mapping.marketplace_product_id = mp.id
                WHERE mp.project_id = :project_id
                  AND NULLIF(btrim(mp.marketplace_sku), '') IS NOT NULL
                  AND mapping.id IS NULL
            ), candidates AS (
                SELECT
                    mp.id AS marketplace_product_id,
                    uc.internal_catalog_product_id,
                    mp.sku_normalization
                FROM unmapped_products mp
                JOIN unique_catalog uc
                  ON uc.sku_key = mp.marketplace_sku_key
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM explicit_product_keys explicit
                    WHERE explicit.project_marketplace_id = mp.project_marketplace_id
                      AND (
                        explicit.marketplace_item_id = mp.marketplace_item_id
                        OR explicit.marketplace_sku_key = mp.marketplace_sku_key
                      )
                  )
            )
            INSERT INTO marketplace_product_mappings (
                project_id,
                marketplace_product_id,
                internal_catalog_product_id,
                mapping_source,
                mapping_status,
                confidence,
                metadata
            )
            SELECT
                :project_id,
                marketplace_product_id,
                internal_catalog_product_id,
                'marketplace_sku_rule',
                'proposed',
                0.9000,
                jsonb_build_object(
                    'snapshot_id', :snapshot_id,
                    'sku_normalization', sku_normalization
                )
            FROM candidates
            ON CONFLICT (marketplace_product_id) DO NOTHING
            """
        ),
        params,
    )

    return {
        "status": "ok",
        "snapshot_id": snapshot_id,
        "catalog_products_upserted": int(catalog_result.rowcount or 0),
        "confirmed_mappings_upserted": int(confirmed_result.rowcount or 0),
        "proposed_mappings_created": int(proposed_result.rowcount or 0),
    }


def reconcile_project_product_mappings(
    *,
    project_id: int,
    snapshot_id: Optional[int] = None,
    connection: Optional[Connection] = None,
) -> dict[str, Any]:
    """Upsert stable catalog products and safe product mappings for one project."""

    if connection is not None:
        return _sync_on_connection(
            connection,
            project_id=int(project_id),
            snapshot_id=snapshot_id,
        )
    with engine.begin() as conn:
        return _sync_on_connection(
            conn,
            project_id=int(project_id),
            snapshot_id=snapshot_id,
        )


def reconcile_all_project_product_mappings(connection: Connection) -> dict[str, int]:
    project_ids = connection.execute(
        text(
            """
            SELECT DISTINCT project_id
            FROM internal_data_snapshots
            WHERE status IN ('success', 'partial')
            ORDER BY project_id
            """
        )
    ).scalars().all()
    completed = 0
    for project_id in project_ids:
        result = _sync_on_connection(connection, project_id=int(project_id), snapshot_id=None)
        if result["status"] == "ok":
            completed += 1
    return {"projects_seen": len(project_ids), "projects_reconciled": completed}


def get_product_mapping_diagnostics(
    *,
    project_id: int,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    allowed_statuses = {"confirmed", "proposed", "rejected", "conflict", "unmatched"}
    if status is not None and status not in allowed_statuses:
        raise ValueError("invalid_mapping_status")

    params = {
        "project_id": int(project_id),
        "status": status,
        "limit": max(1, min(int(limit), 500)),
        "offset": max(0, int(offset)),
    }
    base_cte = """
        WITH latest_snapshot AS (
            SELECT id
            FROM internal_data_snapshots
            WHERE project_id = :project_id
              AND status IN ('success', 'partial')
            ORDER BY imported_at DESC, id DESC
            LIMIT 1
        ), explicit_candidates AS (
            SELECT DISTINCT
                mp.id AS marketplace_product_id,
                icp.internal_sku
            FROM latest_snapshot ls
            JOIN internal_product_identifiers ipi ON ipi.snapshot_id = ls.id
            JOIN internal_products ip
              ON ip.id = ipi.internal_product_id
             AND ip.snapshot_id = ipi.snapshot_id
            JOIN internal_catalog_products icp
              ON icp.project_id = ip.project_id
             AND icp.internal_sku = btrim(ip.internal_sku)
            JOIN marketplaces m ON m.code = lower(btrim(ipi.marketplace_code))
            JOIN project_marketplaces pm
              ON pm.project_id = ipi.project_id
             AND pm.marketplace_id = m.id
            JOIN marketplace_products mp
              ON mp.project_id = ipi.project_id
             AND mp.project_marketplace_id = pm.id
             AND (ipi.marketplace_item_id IS NULL OR mp.marketplace_item_id = btrim(ipi.marketplace_item_id))
             AND (
                ipi.marketplace_sku IS NULL
                OR lower(NULLIF(
                    CASE COALESCE(
                        pm.settings_json #>> '{product_identity,sku_normalization}',
                        'exact'
                    )
                        WHEN 'strip_prefix_before_last_slash'
                            THEN regexp_replace(trim(both '/' from mp.marketplace_sku), '^.*/', '')
                        ELSE btrim(mp.marketplace_sku)
                    END,
                    ''
                )) = lower(NULLIF(
                    CASE COALESCE(
                        pm.settings_json #>> '{product_identity,sku_normalization}',
                        'exact'
                    )
                        WHEN 'strip_prefix_before_last_slash'
                            THEN regexp_replace(trim(both '/' from ipi.marketplace_sku), '^.*/', '')
                        ELSE btrim(ipi.marketplace_sku)
                    END,
                    ''
                ))
             )
            WHERE ipi.project_id = :project_id
        ), explicit_conflicts AS (
            SELECT
                marketplace_product_id,
                array_agg(DISTINCT internal_sku ORDER BY internal_sku) AS candidate_internal_skus
            FROM explicit_candidates
            GROUP BY marketplace_product_id
            HAVING COUNT(DISTINCT internal_sku) > 1
        ), catalog_sku_conflicts AS (
            SELECT
                lower(btrim(icp.internal_sku)) AS sku_key,
                array_agg(DISTINCT icp.internal_sku ORDER BY icp.internal_sku) AS candidate_internal_skus
            FROM latest_snapshot ls
            JOIN internal_products ip ON ip.snapshot_id = ls.id AND ip.project_id = :project_id
            JOIN internal_catalog_products icp
              ON icp.project_id = ip.project_id
             AND icp.internal_sku = btrim(ip.internal_sku)
            WHERE NULLIF(btrim(icp.internal_sku), '') IS NOT NULL
            GROUP BY lower(btrim(icp.internal_sku))
            HAVING COUNT(DISTINCT icp.id) > 1
        ), exact_conflicts AS (
            SELECT
                mp.id AS marketplace_product_id,
                conflict.candidate_internal_skus
            FROM marketplace_products mp
            JOIN project_marketplaces pm
              ON pm.id = mp.project_marketplace_id
             AND pm.project_id = mp.project_id
            JOIN catalog_sku_conflicts conflict
              ON conflict.sku_key = lower(NULLIF(
                  CASE COALESCE(
                      pm.settings_json #>> '{product_identity,sku_normalization}',
                      'exact'
                  )
                      WHEN 'strip_prefix_before_last_slash'
                          THEN regexp_replace(trim(both '/' from mp.marketplace_sku), '^.*/', '')
                      ELSE btrim(mp.marketplace_sku)
                  END,
                  ''
              ))
            WHERE mp.project_id = :project_id
        ), conflicts AS (
            SELECT
                marketplace_product_id,
                array_agg(DISTINCT candidate_internal_sku ORDER BY candidate_internal_sku) AS candidate_internal_skus
            FROM (
                SELECT marketplace_product_id, unnest(candidate_internal_skus) AS candidate_internal_sku
                FROM explicit_conflicts
                UNION ALL
                SELECT marketplace_product_id, unnest(candidate_internal_skus) AS candidate_internal_sku
                FROM exact_conflicts
            ) candidates
            GROUP BY marketplace_product_id
        ), rows AS (
            SELECT
                mp.id AS marketplace_product_id,
                m.code AS marketplace_code,
                mp.marketplace_item_id,
                mp.marketplace_sku,
                mp.title,
                mapping.id AS mapping_id,
                icp.id AS internal_catalog_product_id,
                icp.internal_sku,
                mapping.mapping_source,
                mapping.mapping_status,
                mapping.confidence,
                conflict.candidate_internal_skus,
                CASE
                    WHEN mapping.mapping_status IS NOT NULL THEN mapping.mapping_status
                    WHEN conflict.marketplace_product_id IS NOT NULL THEN 'conflict'
                    ELSE 'unmatched'
                END AS effective_status
            FROM marketplace_products mp
            JOIN project_marketplaces pm
              ON pm.id = mp.project_marketplace_id
             AND pm.project_id = mp.project_id
            JOIN marketplaces m ON m.id = pm.marketplace_id
            LEFT JOIN marketplace_product_mappings mapping
              ON mapping.marketplace_product_id = mp.id
             AND mapping.project_id = mp.project_id
            LEFT JOIN internal_catalog_products icp
              ON icp.id = mapping.internal_catalog_product_id
             AND icp.project_id = mapping.project_id
            LEFT JOIN conflicts conflict ON conflict.marketplace_product_id = mp.id
            WHERE mp.project_id = :project_id
        )
    """
    with engine.connect() as conn:
        counts = conn.execute(
            text(
                base_cte
                + """
                SELECT
                    COUNT(*)::bigint AS total_marketplace_products,
                    COUNT(*) FILTER (WHERE effective_status = 'confirmed')::bigint AS confirmed,
                    COUNT(*) FILTER (WHERE effective_status = 'proposed')::bigint AS proposed,
                    COUNT(*) FILTER (WHERE effective_status = 'rejected')::bigint AS rejected,
                    COUNT(*) FILTER (WHERE effective_status = 'conflict')::bigint AS conflict,
                    COUNT(*) FILTER (WHERE effective_status = 'unmatched')::bigint AS unmatched
                FROM rows
                """
            ),
            params,
        ).mappings().one()
        items = conn.execute(
            text(
                base_cte
                + """
                SELECT *
                FROM rows
                WHERE (:status IS NULL OR effective_status = :status)
                ORDER BY marketplace_code, marketplace_sku NULLS LAST, marketplace_item_id
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        ).mappings().all()
        internal_count = conn.execute(
            text("SELECT COUNT(*) FROM internal_catalog_products WHERE project_id = :project_id"),
            params,
        ).scalar_one()
    return {
        "project_id": int(project_id),
        "internal_catalog_products": int(internal_count or 0),
        **{key: int(value or 0) for key, value in counts.items()},
        "items": [dict(item) for item in items],
        "limit": params["limit"],
        "offset": params["offset"],
    }


def update_product_mapping_status(
    *,
    project_id: int,
    mapping_id: int,
    status: str,
) -> dict[str, Any]:
    if status not in {"confirmed", "rejected"}:
        raise ValueError("invalid_mapping_status")
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                UPDATE marketplace_product_mappings
                SET mapping_status = :status,
                    mapping_source = CASE WHEN :status = 'confirmed' THEN 'manual' ELSE mapping_source END,
                    updated_at = now()
                WHERE id = :mapping_id AND project_id = :project_id
                RETURNING id, project_id, marketplace_product_id, internal_catalog_product_id,
                          mapping_source, mapping_status, confidence, metadata, created_at, updated_at
                """
            ),
            {"project_id": int(project_id), "mapping_id": int(mapping_id), "status": status},
        ).mappings().first()
    if row is None:
        raise ValueError("mapping_not_found")
    return dict(row)
