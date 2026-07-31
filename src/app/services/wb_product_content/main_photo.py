"""Prepare local archives for current main photos before DB history persistence."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Iterable, Mapping, Optional

from sqlalchemy import text

from app import settings
from app.db import engine
from app.services.wb_product_content.file_storage import LocalMainPhotoStorage
from app.services.wb_product_content.normalization import (
    main_photo_url,
    normalize_wb_card_content,
    parse_card_payload,
)
from app.services.wb_product_content.history import source_updated_at


def _candidate_state(project_id: int, nm_ids: Iterable[int]) -> Dict[int, Dict[str, Any]]:
    values = sorted({int(value) for value in nm_ids})
    if not values:
        return {}
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT source_nm.nm_id,
                       p.wb_content_updated_at,
                       p.main_photo_asset_hash,
                       COALESCE(sp.is_active, FALSE) AS is_active,
                       mp.source_url AS period_source_url,
                       mp.archive_status
                FROM unnest(CAST(:nm_ids AS bigint[])) AS source_nm(nm_id)
                LEFT JOIN products p
                  ON p.project_id = :project_id AND p.nm_id = source_nm.nm_id
                LEFT JOIN wb_showcase_product_presence sp
                  ON sp.project_id = :project_id AND sp.nm_id = source_nm.nm_id
                LEFT JOIN wb_product_main_photo_periods mp
                  ON mp.project_id = :project_id
                 AND mp.nm_id = source_nm.nm_id
                 AND mp.observed_to IS NULL
                """
            ),
            {"project_id": int(project_id), "nm_ids": values},
        ).mappings().all()
    return {int(row["nm_id"]): dict(row) for row in rows}


async def prepare_main_photo_attempts(
    *,
    project_id: int,
    rows: Iterable[Mapping[str, Any]],
) -> Dict[int, Dict[str, Any]]:
    row_list = list(rows)
    states = _candidate_state(
        project_id,
        [int(row["nm_id"]) for row in row_list if row.get("nm_id") is not None],
    )
    storage = LocalMainPhotoStorage()
    semaphore = asyncio.Semaphore(5)

    async def prepare(row: Mapping[str, Any]) -> tuple[int, Optional[Dict[str, Any]]]:
        nm_id = int(row["nm_id"])
        payload = parse_card_payload(row.get("raw"))
        url = main_photo_url(normalize_wb_card_content(payload))
        if not url:
            return nm_id, None
        state = states.get(nm_id, {})
        if not state.get("is_active"):
            return nm_id, {
                "status": "skipped_inactive",
                "source_url": url,
            }
        if not settings.WB_MAIN_PHOTO_ARCHIVE_ENABLED:
            return nm_id, {"status": "pending", "source_url": url}

        new_source_at = source_updated_at(payload)
        previous_source_at = state.get("wb_content_updated_at")
        already_stored = (
            state.get("archive_status") == "stored"
            and state.get("period_source_url") == url
            and state.get("main_photo_asset_hash")
        )
        if already_stored and new_source_at is not None and new_source_at == previous_source_at:
            return nm_id, None

        try:
            async with semaphore:
                archived = await storage.archive(
                    project_id=int(project_id),
                    nm_id=nm_id,
                    source_url=url,
                )
            return nm_id, {
                "status": "stored",
                "sha256": archived.sha256,
                "storage_path": archived.storage_path,
                "source_url": archived.source_url,
                "content_type": archived.content_type,
                "file_size": archived.file_size,
                "reused": archived.reused,
            }
        except Exception as exc:
            return nm_id, {
                "status": "failed",
                "source_url": url,
                "error": f"{type(exc).__name__}: {exc}"[:1000],
            }

    prepared = await asyncio.gather(*(prepare(row) for row in row_list))
    return {nm_id: attempt for nm_id, attempt in prepared if attempt is not None}
