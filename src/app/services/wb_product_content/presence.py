"""Current WB storefront presence derived from complete frontend catalog runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import text

from app import settings
from app.db import engine
from app.services.product_identity import (
    resolve_marketplace_product_id,
    resolve_marketplace_product_ids,
)


def is_showcase_active(project_id: int, nm_id: int) -> bool:
    with engine.connect() as conn:
        marketplace_product_id = resolve_marketplace_product_id(
            project_id=project_id,
            marketplace_code="wildberries",
            marketplace_item_id=nm_id,
            connection=conn,
        )
        value = conn.execute(
            text(
                """
                SELECT is_active
                FROM wb_showcase_product_presence
                WHERE project_id = :project_id
                  AND (
                      marketplace_product_id = :marketplace_product_id
                      OR (marketplace_product_id IS NULL AND nm_id = :nm_id)
                  )
                """
            ),
            {
                "project_id": int(project_id),
                "marketplace_product_id": marketplace_product_id,
                "nm_id": int(nm_id),
            },
        ).scalar_one_or_none()
    return value is True


def active_nm_ids(project_id: int, nm_ids: Iterable[int]) -> set[int]:
    values = sorted({int(value) for value in nm_ids})
    if not values:
        return set()
    with engine.connect() as conn:
        product_ids = resolve_marketplace_product_ids(
            project_id=project_id,
            marketplace_code="wildberries",
            marketplace_item_ids=values,
            connection=conn,
        )
        rows = conn.execute(
            text(
                """
                SELECT nm_id
                FROM wb_showcase_product_presence
                WHERE project_id = :project_id
                  AND (
                      marketplace_product_id = ANY(:marketplace_product_ids)
                      OR (marketplace_product_id IS NULL AND nm_id = ANY(:nm_ids))
                  )
                  AND is_active = TRUE
                """
            ),
            {
                "project_id": int(project_id),
                "marketplace_product_ids": list(product_ids.values()),
                "nm_ids": values,
            },
        ).fetchall()
    return {int(row[0]) for row in rows}


def apply_complete_showcase_run(
    *,
    project_id: int,
    brand_id: int,
    seen_nm_ids: Iterable[int],
    ingest_run_id: Optional[int],
    observed_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Apply one complete brand crawl; callers must reject partial runs first."""
    now = observed_at or datetime.now(timezone.utc)
    seen = sorted({int(value) for value in seen_nm_ids})
    threshold = max(1, int(settings.WB_SHOWCASE_INACTIVE_AFTER_MISSING_RUNS))
    activated_nm_ids: List[int] = []
    deactivated = 0

    with engine.begin() as conn:
        if seen:
            product_ids = resolve_marketplace_product_ids(
                project_id=project_id,
                marketplace_code="wildberries",
                marketplace_item_ids=seen,
                connection=conn,
            )
            previous = conn.execute(
                text(
                    """
                    SELECT nm_id, is_active
                    FROM wb_showcase_product_presence
                    WHERE project_id = :project_id
                      AND nm_id = ANY(:nm_ids)
                    """
                ),
                {"project_id": int(project_id), "nm_ids": seen},
            ).fetchall()
            previous_state = {int(row[0]): bool(row[1]) for row in previous}
            activated_nm_ids = [
                nm_id for nm_id in seen if previous_state.get(nm_id) is not True
            ]
            conn.execute(
                text(
                    """
                    INSERT INTO wb_showcase_product_presence (
                        project_id, marketplace_product_id, nm_id,
                        showcase_brand_id, is_active,
                        last_seen_at, last_seen_run_id, last_checked_at,
                        consecutive_missing_runs, updated_at
                    )
                    VALUES (
                        :project_id, :marketplace_product_id, :nm_id,
                        :brand_id, TRUE, :observed_at, :ingest_run_id,
                        :observed_at, 0, :observed_at
                    )
                    ON CONFLICT (project_id, nm_id) DO UPDATE SET
                        marketplace_product_id = COALESCE(
                            EXCLUDED.marketplace_product_id,
                            wb_showcase_product_presence.marketplace_product_id
                        ),
                        showcase_brand_id = EXCLUDED.showcase_brand_id,
                        is_active = TRUE,
                        last_seen_at = EXCLUDED.last_seen_at,
                        last_seen_run_id = EXCLUDED.last_seen_run_id,
                        last_checked_at = EXCLUDED.last_checked_at,
                        consecutive_missing_runs = 0,
                        updated_at = EXCLUDED.updated_at
                    """
                ),
                [
                    {
                        "project_id": int(project_id),
                        "marketplace_product_id": product_ids.get(str(nm_id)),
                        "nm_id": nm_id,
                        "brand_id": int(brand_id),
                        "observed_at": now,
                        "ingest_run_id": int(ingest_run_id) if ingest_run_id is not None else None,
                    }
                    for nm_id in seen
                ],
            )

        missing_result = conn.execute(
            text(
                """
                UPDATE wb_showcase_product_presence
                SET consecutive_missing_runs = consecutive_missing_runs + 1,
                    is_active = CASE
                        WHEN consecutive_missing_runs + 1 >= :threshold THEN FALSE
                        ELSE is_active
                    END,
                    last_checked_at = :observed_at,
                    updated_at = :observed_at
                WHERE project_id = :project_id
                  AND showcase_brand_id = :brand_id
                  AND NOT (nm_id = ANY(CAST(:nm_ids AS bigint[])))
                RETURNING is_active
                """
            ),
            {
                "project_id": int(project_id),
                "brand_id": int(brand_id),
                "nm_ids": seen,
                "threshold": threshold,
                "observed_at": now,
            },
        ).fetchall()
        deactivated = sum(1 for row in missing_result if row[0] is False)

    return {
        "seen": len(seen),
        "activated": len(activated_nm_ids),
        "deactivated_or_still_inactive": deactivated,
        "missing_threshold": threshold,
    }
