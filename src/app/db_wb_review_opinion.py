"""Persistence helpers for manual customer-opinion analysis runs."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.db import engine


def _json(value: Any) -> str | None:
    return json.dumps(value, ensure_ascii=False) if value is not None else None


def _row(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def get_review_opinion_run(run_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM wb_review_opinion_runs WHERE id = :run_id"),
            {"run_id": int(run_id)},
        ).mappings().first()
    return _row(row)


def find_active_review_opinion_run(project_id: int, nm_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM wb_review_opinion_runs
                WHERE project_id = :project_id
                  AND nm_id = :nm_id
                  AND status IN ('queued', 'running')
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"project_id": int(project_id), "nm_id": int(nm_id)},
        ).mappings().first()
    return _row(row)


def find_cached_review_opinion_run(
    project_id: int,
    nm_id: int,
    *,
    input_hash: str,
    prompt_version: str,
    model: str,
) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM wb_review_opinion_runs
                WHERE project_id = :project_id
                  AND nm_id = :nm_id
                  AND status = 'ready'
                  AND input_hash = :input_hash
                  AND prompt_version = :prompt_version
                  AND model = :model
                ORDER BY finished_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {
                "project_id": int(project_id),
                "nm_id": int(nm_id),
                "input_hash": input_hash,
                "prompt_version": prompt_version,
                "model": model,
            },
        ).mappings().first()
    return _row(row)


def get_latest_review_opinion_runs(project_id: int, nm_id: int) -> dict[str, Any]:
    params = {"project_id": int(project_id), "nm_id": int(nm_id)}
    with engine.connect() as conn:
        latest = conn.execute(
            text(
                """
                SELECT *
                FROM wb_review_opinion_runs
                WHERE project_id = :project_id AND nm_id = :nm_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            params,
        ).mappings().first()
        latest_ready = conn.execute(
            text(
                """
                SELECT *
                FROM wb_review_opinion_runs
                WHERE project_id = :project_id
                  AND nm_id = :nm_id
                  AND status = 'ready'
                ORDER BY finished_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            params,
        ).mappings().first()
    return {"latest": _row(latest), "latest_ready": _row(latest_ready)}


def create_review_opinion_run(
    *,
    project_id: int,
    requested_by_user_id: int | None,
    nm_id: int,
    input_hash: str,
    prompt_version: str,
    schema_version: str,
    model: str,
    reasoning_effort: str,
    reviews_total: int,
    reviews_with_text: int,
    reviews_sent: int,
) -> dict[str, Any]:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO wb_review_opinion_runs (
                    project_id, requested_by_user_id, nm_id, scope_type, status, input_hash,
                    prompt_version, schema_version, model, reasoning_effort,
                    reviews_total, reviews_with_text, reviews_sent
                )
                VALUES (
                    :project_id, :requested_by_user_id, :nm_id, 'all_time', 'queued', :input_hash,
                    :prompt_version, :schema_version, :model, :reasoning_effort,
                    :reviews_total, :reviews_with_text, :reviews_sent
                )
                RETURNING *
                """
            ),
            {
                "project_id": int(project_id),
                "requested_by_user_id": (
                    int(requested_by_user_id)
                    if requested_by_user_id is not None
                    else None
                ),
                "nm_id": int(nm_id),
                "input_hash": input_hash,
                "prompt_version": prompt_version,
                "schema_version": schema_version,
                "model": model,
                "reasoning_effort": reasoning_effort,
                "reviews_total": int(reviews_total),
                "reviews_with_text": int(reviews_with_text),
                "reviews_sent": int(reviews_sent),
            },
        ).mappings().one()
    return dict(row)


def mark_review_opinion_running(run_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE wb_review_opinion_runs
                SET status = 'running',
                    started_at = COALESCE(started_at, now()),
                    attempt_count = attempt_count + 1,
                    error_code = NULL,
                    error_message = NULL
                WHERE id = :run_id
                """
            ),
            {"run_id": int(run_id)},
        )


def update_review_opinion_input(run_id: int, analysis_input: Any) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE wb_review_opinion_runs
                SET input_hash = :input_hash,
                    reviews_total = :reviews_total,
                    reviews_with_text = :reviews_with_text,
                    reviews_sent = :reviews_sent
                WHERE id = :run_id
                """
            ),
            {
                "run_id": int(run_id),
                "input_hash": analysis_input.input_hash,
                "reviews_total": int(analysis_input.reviews_total),
                "reviews_with_text": int(analysis_input.reviews_with_text),
                "reviews_sent": int(analysis_input.reviews_sent),
            },
        )


def finish_review_opinion_ready(
    run_id: int,
    *,
    model: str,
    result: dict[str, Any],
    validation: dict[str, Any],
    usage: dict[str, Any],
    provider_request_id: str | None,
    raw_output_text: str,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE wb_review_opinion_runs
                SET status = 'ready',
                    model = :model,
                    result_json = CAST(:result_json AS jsonb),
                    validation_json = CAST(:validation_json AS jsonb),
                    usage_json = CAST(:usage_json AS jsonb),
                    provider_request_id = :provider_request_id,
                    raw_output_text = :raw_output_text,
                    error_code = NULL,
                    error_message = NULL,
                    finished_at = now()
                WHERE id = :run_id
                """
            ),
            {
                "run_id": int(run_id),
                "model": model,
                "result_json": _json(result),
                "validation_json": _json(validation),
                "usage_json": _json(usage),
                "provider_request_id": provider_request_id,
                "raw_output_text": raw_output_text,
            },
        )


def finish_review_opinion_failed(
    run_id: int,
    *,
    error_code: str,
    error_message: str,
    raw_output_text: str | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE wb_review_opinion_runs
                SET status = 'failed',
                    error_code = :error_code,
                    error_message = :error_message,
                    raw_output_text = COALESCE(:raw_output_text, raw_output_text),
                    finished_at = now()
                WHERE id = :run_id
                """
            ),
            {
                "run_id": int(run_id),
                "error_code": error_code[:64],
                "error_message": error_message[:2000],
                "raw_output_text": raw_output_text,
            },
        )
