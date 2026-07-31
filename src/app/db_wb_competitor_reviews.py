"""Persistence for manually collected competitor review data."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import bindparam, text

from app.db import engine


def add_targets(project_id: int, nm_ids: list[int]) -> dict[str, Any]:
    unique_ids = list(dict.fromkeys(int(value) for value in nm_ids))
    added = 0
    with engine.begin() as conn:
        for nm_id in unique_ids:
            result = conn.execute(
                text(
                    """
                    INSERT INTO wb_competitor_review_targets (project_id, nm_id)
                    VALUES (:project_id, :nm_id)
                    ON CONFLICT (project_id, nm_id) DO NOTHING
                    """
                ),
                {"project_id": int(project_id), "nm_id": nm_id},
            )
            added += int(result.rowcount or 0)
    return {
        "items": list_targets(project_id, nm_ids=unique_ids),
        "added_count": added,
        "existing_count": len(unique_ids) - added,
    }


def list_targets(project_id: int, *, nm_ids: list[int] | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT t.*,
               analysis.id AS analysis_id,
               analysis.status AS analysis_status,
               analysis.reviews_sent AS analysis_reviews_count,
               analysis.actual_cost_usd AS analysis_cost_usd,
               analysis.finished_at AS analysis_finished_at,
               analysis.error_message AS analysis_error,
               CASE
                   WHEN analysis.status = 'ready'
                    AND t.last_collected_at IS NOT NULL
                    AND (
                        analysis.source_last_collected_at IS NULL
                        OR analysis.source_last_collected_at < t.last_collected_at
                    )
                   THEN TRUE
                   ELSE FALSE
               END AS analysis_is_stale,
               COALESCE(review_stats.text_chars, 0)::int AS analysis_text_chars
        FROM wb_competitor_review_targets t
        LEFT JOIN LATERAL (
            SELECT a.*
            FROM wb_competitor_review_analyses a
            WHERE a.target_id = t.id
            ORDER BY a.created_at DESC
            LIMIT 1
        ) analysis ON TRUE
        LEFT JOIN LATERAL (
            SELECT SUM(LENGTH(CONCAT_WS(' ', r.text, r.pros, r.cons))) AS text_chars
            FROM wb_competitor_reviews r
            WHERE r.target_id = t.id
        ) review_stats ON TRUE
        WHERE t.project_id = :project_id
    """
    params: dict[str, Any] = {"project_id": int(project_id)}
    statement = text(sql)
    if nm_ids is not None:
        if not nm_ids:
            return []
        statement = text(sql + " AND t.nm_id IN :nm_ids ORDER BY t.updated_at DESC, t.nm_id")
        statement = statement.bindparams(bindparam("nm_ids", expanding=True))
        params["nm_ids"] = [int(value) for value in nm_ids]
    else:
        statement = text(sql + " ORDER BY t.updated_at DESC, t.nm_id")
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(statement, params).mappings().all()]


def get_target(project_id: int, nm_id: int) -> dict[str, Any] | None:
    rows = list_targets(project_id, nm_ids=[nm_id])
    return rows[0] if rows else None


def delete_targets(project_id: int, nm_ids: list[int]) -> list[int]:
    """Delete project-owned targets; dependent reviews and analyses cascade."""
    unique_ids = list(dict.fromkeys(int(value) for value in nm_ids))
    if not unique_ids:
        return []
    statement = text(
        """
        DELETE FROM wb_competitor_review_targets
        WHERE project_id = :project_id AND nm_id IN :nm_ids
        RETURNING nm_id
        """
    ).bindparams(bindparam("nm_ids", expanding=True))
    with engine.begin() as conn:
        rows = conn.execute(
            statement,
            {"project_id": int(project_id), "nm_ids": unique_ids},
        ).scalars().all()
    deleted = {int(value) for value in rows}
    return [nm_id for nm_id in unique_ids if nm_id in deleted]


def create_run(
    project_id: int,
    *,
    requested_by_user_id: int | None,
    nm_ids: list[int],
) -> dict[str, Any]:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO wb_competitor_review_runs (
                    project_id, requested_by_user_id, status, requested_nm_ids
                )
                VALUES (
                    :project_id, :requested_by_user_id, 'queued',
                    CAST(:requested_nm_ids AS jsonb)
                )
                RETURNING *
                """
            ),
            {
                "project_id": int(project_id),
                "requested_by_user_id": requested_by_user_id,
                "requested_nm_ids": json.dumps(nm_ids),
            },
        ).mappings().one()
        queue_statement = text(
                """
                UPDATE wb_competitor_review_targets
                SET status = 'queued', last_error = NULL, updated_at = now()
                WHERE project_id = :project_id AND nm_id IN :nm_ids
                """
            ).bindparams(bindparam("nm_ids", expanding=True))
        conn.execute(
            queue_statement,
            {"project_id": int(project_id), "nm_ids": nm_ids},
        )
    return dict(row)


def get_active_run(project_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT * FROM wb_competitor_review_runs
                WHERE project_id = :project_id AND status IN ('queued','running')
                ORDER BY created_at DESC LIMIT 1
                """
            ),
            {"project_id": int(project_id)},
        ).mappings().first()
    return dict(row) if row else None


def get_run(project_id: int, run_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT * FROM wb_competitor_review_runs
                WHERE project_id = :project_id AND id = :run_id
                """
            ),
            {"project_id": int(project_id), "run_id": int(run_id)},
        ).mappings().first()
    return dict(row) if row else None


def mark_run_running(run_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE wb_competitor_review_runs
                SET status = 'running', started_at = COALESCE(started_at, now())
                WHERE id = :run_id AND status = 'queued'
                """
            ),
            {"run_id": int(run_id)},
        )


def finish_run(
    run_id: int,
    *,
    completed_nm_ids: list[int],
    failed_nm_ids: list[int],
    error_message: str | None = None,
    failed: bool = False,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE wb_competitor_review_runs
                SET status = :status,
                    completed_nm_ids = CAST(:completed AS jsonb),
                    failed_nm_ids = CAST(:failed_ids AS jsonb),
                    error_message = :error_message,
                    finished_at = now()
                WHERE id = :run_id
                """
            ),
            {
                "run_id": int(run_id),
                "status": "failed" if failed else "completed",
                "completed": json.dumps(completed_nm_ids),
                "failed_ids": json.dumps(failed_nm_ids),
                "error_message": error_message[:2000] if error_message else None,
            },
        )


def mark_target_collecting(project_id: int, nm_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE wb_competitor_review_targets
                SET status = 'collecting', last_error = NULL, updated_at = now()
                WHERE project_id = :project_id AND nm_id = :nm_id
                """
            ),
            {"project_id": int(project_id), "nm_id": int(nm_id)},
        )


def save_collection(project_id: int, nm_id: int, collection: Any) -> None:
    with engine.begin() as conn:
        target = conn.execute(
            text(
                """
                SELECT id FROM wb_competitor_review_targets
                WHERE project_id = :project_id AND nm_id = :nm_id
                FOR UPDATE
                """
            ),
            {"project_id": int(project_id), "nm_id": int(nm_id)},
        ).mappings().one()
        target_id = int(target["id"])
        for review in collection.reviews:
            conn.execute(
                text(
                    """
                    INSERT INTO wb_competitor_reviews (
                        target_id, external_id, rating, review_created_at,
                        text, pros, cons
                    )
                    VALUES (
                        :target_id, :external_id, :rating, :review_created_at,
                        :text, :pros, :cons
                    )
                    ON CONFLICT (target_id, external_id) DO UPDATE SET
                        rating = EXCLUDED.rating,
                        review_created_at = EXCLUDED.review_created_at,
                        text = EXCLUDED.text,
                        pros = EXCLUDED.pros,
                        cons = EXCLUDED.cons,
                        last_seen_at = now()
                    """
                ),
                {
                    "target_id": target_id,
                    "external_id": review.external_id,
                    "rating": review.rating,
                    "review_created_at": review.created_at,
                    "text": review.text,
                    "pros": review.pros,
                    "cons": review.cons,
                },
            )
        aggregate = conn.execute(
            text(
                """
                SELECT COUNT(*)::int AS text_reviews_count,
                       AVG(rating)::numeric(5, 2) AS calculated_avg_rating
                FROM wb_competitor_reviews
                WHERE target_id = :target_id
                """
            ),
            {"target_id": target_id},
        ).mappings().one()
        conn.execute(
            text(
                """
                UPDATE wb_competitor_review_targets
                SET root_id = :root_id,
                    title = :title,
                    brand = :brand,
                    subject_id = :subject_id,
                    category_name = :category_name,
                    wb_review_rating = :wb_review_rating,
                    wb_feedback_count = :wb_feedback_count,
                    collected_reviews_count = :collected_reviews_count,
                    text_reviews_count = :text_reviews_count,
                    calculated_avg_rating = :calculated_avg_rating,
                    status = 'ready',
                    last_error = NULL,
                    last_collected_at = now(),
                    updated_at = now()
                WHERE id = :target_id
                """
            ),
            {
                "target_id": target_id,
                "root_id": collection.root_id,
                "title": collection.title,
                "brand": collection.brand,
                "subject_id": collection.subject_id,
                "category_name": collection.category_name,
                "wb_review_rating": collection.wb_review_rating,
                "wb_feedback_count": collection.wb_feedback_count,
                "collected_reviews_count": collection.collected_reviews_count,
                "text_reviews_count": int(aggregate["text_reviews_count"] or 0),
                "calculated_avg_rating": aggregate["calculated_avg_rating"],
            },
        )


def mark_target_failed(project_id: int, nm_id: int, *, code: str, message: str) -> None:
    status = "not_found" if code == "product_not_found" else "failed"
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE wb_competitor_review_targets
                SET status = :status, last_error = :last_error, updated_at = now()
                WHERE project_id = :project_id AND nm_id = :nm_id
                """
            ),
            {
                "project_id": int(project_id),
                "nm_id": int(nm_id),
                "status": status,
                "last_error": f"{code}: {message}"[:1000],
            },
        )


def list_reviews(project_id: int, nm_id: int, *, limit: int, offset: int) -> dict[str, Any] | None:
    target = get_target(project_id, nm_id)
    if target is None:
        return None
    with engine.connect() as conn:
        total = int(
            conn.execute(
                text("SELECT COUNT(*) FROM wb_competitor_reviews WHERE target_id = :target_id"),
                {"target_id": int(target["id"])},
            ).scalar_one()
        )
        rows = conn.execute(
            text(
                """
                SELECT id, rating, review_created_at AS created_at,
                       text, pros, cons
                FROM wb_competitor_reviews
                WHERE target_id = :target_id
                ORDER BY review_created_at DESC NULLS LAST, id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"target_id": int(target["id"]), "limit": int(limit), "offset": int(offset)},
        ).mappings().all()
    return {
        "items": [dict(row) for row in rows],
        "total": total,
        "has_more": offset + len(rows) < total,
    }


def get_competitor_analysis_run(run_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT a.*, t.project_id, t.nm_id, t.title, t.category_name
                FROM wb_competitor_review_analyses a
                JOIN wb_competitor_review_targets t ON t.id = a.target_id
                WHERE a.id = :run_id
                """
            ),
            {"run_id": int(run_id)},
        ).mappings().first()
    return dict(row) if row else None


def get_competitor_analysis_state(project_id: int, nm_id: int) -> dict[str, Any] | None:
    target = get_target(project_id, nm_id)
    if target is None:
        return None
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT *
                FROM wb_competitor_review_analyses
                WHERE target_id = :target_id
                ORDER BY created_at DESC
                """
            ),
            {"target_id": int(target["id"])},
        ).mappings().all()
    latest = dict(rows[0]) if rows else None
    latest_ready = next(
        (dict(row) for row in rows if row["status"] == "ready"),
        None,
    )
    return {
        "target": target,
        "latest": latest,
        "latest_ready": latest_ready,
    }


def find_active_competitor_analysis(target_id: int) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM wb_competitor_review_analyses
                WHERE target_id = :target_id AND status IN ('queued','running')
                ORDER BY created_at DESC LIMIT 1
                """
            ),
            {"target_id": int(target_id)},
        ).mappings().first()
    return dict(row) if row else None


def find_cached_competitor_analysis(
    target_id: int,
    *,
    input_hash: str,
    pipeline_version: str,
) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM wb_competitor_review_analyses
                WHERE target_id = :target_id
                  AND status = 'ready'
                  AND input_hash = :input_hash
                  AND pipeline_version = :pipeline_version
                ORDER BY finished_at DESC NULLS LAST
                LIMIT 1
                """
            ),
            {
                "target_id": int(target_id),
                "input_hash": input_hash,
                "pipeline_version": pipeline_version,
            },
        ).mappings().first()
    return dict(row) if row else None


def create_competitor_analysis(
    *,
    target_id: int,
    requested_by_user_id: int | None,
    input_hash: str,
    pipeline_version: str,
    schema_version: str,
    reviews_sent: int,
    source_last_collected_at: Any,
    estimated_cost_usd: float,
    max_cost_usd: float,
) -> dict[str, Any]:
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO wb_competitor_review_analyses (
                    target_id, requested_by_user_id, status, input_hash,
                    pipeline_version, schema_version, reviews_sent,
                    source_last_collected_at, estimated_cost_usd, max_cost_usd
                )
                VALUES (
                    :target_id, :requested_by_user_id, 'queued', :input_hash,
                    :pipeline_version, :schema_version, :reviews_sent,
                    :source_last_collected_at, :estimated_cost_usd, :max_cost_usd
                )
                RETURNING *
                """
            ),
            {
                "target_id": int(target_id),
                "requested_by_user_id": requested_by_user_id,
                "input_hash": input_hash,
                "pipeline_version": pipeline_version,
                "schema_version": schema_version,
                "reviews_sent": int(reviews_sent),
                "source_last_collected_at": source_last_collected_at,
                "estimated_cost_usd": float(estimated_cost_usd),
                "max_cost_usd": float(max_cost_usd),
            },
        ).mappings().one()
    return dict(row)


def mark_competitor_analysis_running(run_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE wb_competitor_review_analyses
                SET status = 'running', started_at = COALESCE(started_at, now()),
                    error_code = NULL, error_message = NULL
                WHERE id = :run_id AND status = 'queued'
                """
            ),
            {"run_id": int(run_id)},
        )


def finish_competitor_analysis_ready(
    run_id: int,
    *,
    result: dict[str, Any],
    validation: dict[str, Any],
    usage: dict[str, Any],
    actual_cost_usd: float,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE wb_competitor_review_analyses
                SET status = 'ready',
                    result_json = CAST(:result_json AS jsonb),
                    validation_json = CAST(:validation_json AS jsonb),
                    usage_json = CAST(:usage_json AS jsonb),
                    actual_cost_usd = :actual_cost_usd,
                    error_code = NULL,
                    error_message = NULL,
                    finished_at = now()
                WHERE id = :run_id
                """
            ),
            {
                "run_id": int(run_id),
                "result_json": json.dumps(result, ensure_ascii=False),
                "validation_json": json.dumps(validation, ensure_ascii=False),
                "usage_json": json.dumps(usage, ensure_ascii=False),
                "actual_cost_usd": float(actual_cost_usd),
            },
        )


def finish_competitor_analysis_failed(
    run_id: int,
    *,
    error_code: str,
    error_message: str,
    usage: dict[str, Any] | None = None,
    actual_cost_usd: float = 0.0,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE wb_competitor_review_analyses
                SET status = 'failed',
                    usage_json = CAST(:usage_json AS jsonb),
                    actual_cost_usd = :actual_cost_usd,
                    error_code = :error_code,
                    error_message = :error_message,
                    finished_at = now()
                WHERE id = :run_id
                """
            ),
            {
                "run_id": int(run_id),
                "usage_json": json.dumps(usage or {}, ensure_ascii=False),
                "actual_cost_usd": float(actual_cost_usd),
                "error_code": error_code[:64],
                "error_message": error_message[:2000],
            },
        )
