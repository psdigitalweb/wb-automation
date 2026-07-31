"""Manual orchestration for collecting reviews of arbitrary WB products."""

from __future__ import annotations

from typing import Any

from app.db_wb_competitor_reviews import (
    finish_run,
    get_run,
    mark_run_running,
    mark_target_collecting,
    mark_target_failed,
    save_collection,
)
from app.wb.competitor_reviews_client import (
    WBCompetitorReviewsClient,
    WBCompetitorReviewsError,
)


async def collect_competitor_review_run(
    run_id: int,
    *,
    client: WBCompetitorReviewsClient | None = None,
) -> dict[str, Any]:
    run = get_run_by_id(int(run_id))
    if run is None:
        raise LookupError("competitor_review_run_not_found")
    if run.get("status") not in {"queued", "running"}:
        return {"run_id": int(run_id), "status": str(run.get("status"))}

    project_id = int(run["project_id"])
    requested = run.get("requested_nm_ids") or []
    if isinstance(requested, str):
        import json

        requested = json.loads(requested)
    nm_ids = [int(value) for value in requested]
    resolved_client = client
    if resolved_client is None:
        from app.tasks.ingestion import _get_frontend_prices_proxy_config

        proxy_url, _proxy_scheme = _get_frontend_prices_proxy_config(project_id)
        resolved_client = WBCompetitorReviewsClient(proxy_url=proxy_url)

    mark_run_running(int(run_id))
    completed: list[int] = []
    failed: list[int] = []
    try:
        for nm_id in nm_ids:
            mark_target_collecting(project_id, nm_id)
            try:
                collection = await resolved_client.collect(nm_id)
                save_collection(project_id, nm_id, collection)
                completed.append(nm_id)
            except WBCompetitorReviewsError as exc:
                mark_target_failed(
                    project_id,
                    nm_id,
                    code=exc.code,
                    message=str(exc),
                )
                failed.append(nm_id)
            except Exception as exc:  # noqa: BLE001
                mark_target_failed(
                    project_id,
                    nm_id,
                    code=type(exc).__name__,
                    message="Unexpected collection error",
                )
                failed.append(nm_id)
        finish_run(
            int(run_id),
            completed_nm_ids=completed,
            failed_nm_ids=failed,
        )
        return {
            "run_id": int(run_id),
            "status": "completed",
            "completed_nm_ids": completed,
            "failed_nm_ids": failed,
        }
    except Exception as exc:  # noqa: BLE001
        finish_run(
            int(run_id),
            completed_nm_ids=completed,
            failed_nm_ids=list(dict.fromkeys(failed + [value for value in nm_ids if value not in completed])),
            error_message="Collection run failed unexpectedly",
            failed=True,
        )
        raise RuntimeError("competitor_review_collection_failed") from exc


def get_run_by_id(run_id: int) -> dict[str, Any] | None:
    """Read a run without requiring its project id inside the worker."""

    from sqlalchemy import text

    from app.db import engine

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM wb_competitor_review_runs WHERE id = :run_id"),
            {"run_id": int(run_id)},
        ).mappings().first()
    return dict(row) if row else None
