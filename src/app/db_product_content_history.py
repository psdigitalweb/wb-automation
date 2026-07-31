"""Read-side queries for WB product content history."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.db import engine


def list_content_versions(
    *,
    project_id: int,
    nm_id: int,
    marketplace_product_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, project_id, nm_id, version_no, event_type,
                       content_hash, normalization_version, changed_fields,
                       change_types, observed_at, source_updated_at,
                       ingest_run_id, created_at
                FROM wb_product_content_versions
                WHERE project_id = :project_id
                  AND (
                      marketplace_product_id = :marketplace_product_id
                      OR (marketplace_product_id IS NULL AND nm_id = :nm_id)
                  )
                ORDER BY version_no DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {
                "project_id": int(project_id),
                "marketplace_product_id": marketplace_product_id,
                "nm_id": int(nm_id),
                "limit": max(1, min(int(limit), 200)),
                "offset": max(0, int(offset)),
            },
        ).mappings().all()
    return [dict(row) for row in rows]


def get_content_version(
    *,
    project_id: int,
    nm_id: int,
    version_id: int,
    marketplace_product_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, project_id, nm_id, version_no, event_type,
                       content_hash, normalization_version, content_snapshot,
                       changed_fields, change_types, observed_at,
                       source_updated_at, ingest_run_id, created_at
                FROM wb_product_content_versions
                WHERE id = :version_id
                  AND project_id = :project_id
                  AND (
                      marketplace_product_id = :marketplace_product_id
                      OR (marketplace_product_id IS NULL AND nm_id = :nm_id)
                  )
                """
            ),
            {
                "version_id": int(version_id),
                "project_id": int(project_id),
                "marketplace_product_id": marketplace_product_id,
                "nm_id": int(nm_id),
            },
        ).mappings().first()
    return dict(row) if row else None

def list_main_photo_periods(
    *,
    project_id: int,
    nm_id: int,
    marketplace_product_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT p.id, p.project_id, p.nm_id, p.content_version_id,
                       p.asset_id, p.source_url, p.observed_from, p.observed_to,
                       p.source_updated_at, p.ingest_run_id, p.archive_status,
                       p.archive_error, p.created_at, p.updated_at,
                       a.sha256 AS asset_sha256,
                       a.content_type AS asset_content_type,
                       a.file_size AS asset_file_size
                FROM wb_product_main_photo_periods p
                LEFT JOIN wb_product_main_photo_assets a ON a.id = p.asset_id
                WHERE p.project_id = :project_id
                  AND (
                      p.marketplace_product_id = :marketplace_product_id
                      OR (p.marketplace_product_id IS NULL AND p.nm_id = :nm_id)
                  )
                ORDER BY p.observed_from DESC
                """
            ),
            {
                "project_id": int(project_id),
                "marketplace_product_id": marketplace_product_id,
                "nm_id": int(nm_id),
            },
        ).mappings().all()
    return [dict(row) for row in rows]


def get_main_photo_asset(
    *,
    project_id: int,
    nm_id: int,
    asset_id: int,
    marketplace_product_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, project_id, nm_id, sha256, storage_path,
                       source_url, content_type, file_size, downloaded_at
                FROM wb_product_main_photo_assets
                WHERE id = :asset_id
                  AND project_id = :project_id
                  AND (
                      marketplace_product_id = :marketplace_product_id
                      OR (marketplace_product_id IS NULL AND nm_id = :nm_id)
                  )
                """
            ),
            {
                "asset_id": int(asset_id),
                "project_id": int(project_id),
                "marketplace_product_id": marketplace_product_id,
                "nm_id": int(nm_id),
            },
        ).mappings().first()
    return dict(row) if row else None
