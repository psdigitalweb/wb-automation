"""DAO for Hypothesis Lab MVP experiments, runs, and results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.db import engine

MIN_CONTROLS_FOR_MATCHED = 5


def count_controls_for_test_sku(project_id: int, test_nm_id: int) -> int:
    """Count products in the same subject within the project, excluding the test SKU."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT p.subject_id
                FROM products p
                WHERE p.project_id = :project_id AND p.nm_id = :nm_id
                """
            ),
            {"project_id": project_id, "nm_id": test_nm_id},
        ).fetchone()

    if not row or row[0] is None:
        return 0

    with engine.connect() as conn:
        return (
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM products p
                    WHERE p.project_id = :project_id
                      AND p.nm_id != :nm_id
                      AND p.subject_id = :subject_id
                      AND p.nm_id IS NOT NULL
                    """
                ),
                {
                    "project_id": project_id,
                    "nm_id": test_nm_id,
                    "subject_id": row[0],
                },
            ).scalar()
            or 0
        )


def create_hl_mvp_experiment(
    project_id: int,
    hypothesis_id: int,
    nm_id: int,
    change_type: str,
    change_note: str,
    metric: str,
) -> Dict[str, Any]:
    controls_count = count_controls_for_test_sku(project_id, nm_id)
    control_mode = "matched" if controls_count >= MIN_CONTROLS_FOR_MATCHED else "none"

    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO hl_mvp_experiments (
                    project_id,
                    hypothesis_id,
                    nm_id,
                    change_type,
                    change_note,
                    metric,
                    control_mode,
                    controls_count,
                    status
                )
                VALUES (
                    :project_id,
                    :hypothesis_id,
                    :nm_id,
                    :change_type,
                    :change_note,
                    :metric,
                    :control_mode,
                    :controls_count,
                    'draft'
                )
                RETURNING
                    id,
                    project_id,
                    hypothesis_id,
                    nm_id,
                    change_type,
                    change_note,
                    metric,
                    control_mode,
                    controls_count,
                    status,
                    period_start,
                    period_end,
                    created_at,
                    updated_at
                """
            ),
            {
                "project_id": project_id,
                "hypothesis_id": hypothesis_id,
                "nm_id": nm_id,
                "change_type": change_type,
                "change_note": change_note,
                "metric": metric,
                "control_mode": control_mode,
                "controls_count": controls_count,
            },
        ).fetchone()

    return {
        "id": row[0],
        "project_id": row[1],
        "hypothesis_id": row[2],
        "nm_id": row[3],
        "change_type": row[4],
        "change_note": row[5],
        "metric": row[6],
        "control_mode": row[7],
        "controls_count": row[8],
        "status": row[9],
        "period_start": row[10],
        "period_end": row[11],
        "created_at": row[12],
        "updated_at": row[13],
    }


def list_hl_mvp_experiments(
    project_id: int,
    status: Optional[str] = None,
    metric: Optional[str] = None,
    hypothesis_id: Optional[int] = None,
    nm_id: Optional[int] = None,
    query: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    sql = """
        SELECT
            e.id,
            e.project_id,
            e.hypothesis_id,
            e.nm_id,
            e.change_type,
            e.change_note,
            e.metric,
            e.control_mode,
            e.controls_count,
            e.status,
            e.period_start,
            e.period_end,
            e.created_at,
            e.updated_at,
            h.title AS hypothesis_title,
            p.title AS product_title
        FROM hl_mvp_experiments e
        JOIN hypotheses h ON h.id = e.hypothesis_id
        LEFT JOIN products p ON p.project_id = e.project_id AND p.nm_id = e.nm_id
        WHERE e.project_id = :project_id
    """
    params: Dict[str, Any] = {"project_id": project_id, "limit": limit}

    if status:
        sql += " AND e.status = :status"
        params["status"] = status
    if metric:
        sql += " AND e.metric = :metric"
        params["metric"] = metric
    if hypothesis_id is not None:
        sql += " AND e.hypothesis_id = :hypothesis_id"
        params["hypothesis_id"] = hypothesis_id
    if nm_id is not None:
        sql += " AND e.nm_id = :nm_id"
        params["nm_id"] = nm_id
    if query and query.strip():
        sql += " AND (h.title ILIKE :q OR p.title ILIKE :q OR CAST(e.nm_id AS TEXT) LIKE :q_nm)"
        params["q"] = f"%{query.strip()}%"
        params["q_nm"] = f"%{query.strip()}%"

    sql += " ORDER BY e.updated_at DESC LIMIT :limit"

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()

    return [
        {
            "id": row[0],
            "project_id": row[1],
            "hypothesis_id": row[2],
            "nm_id": row[3],
            "change_type": row[4],
            "change_note": row[5],
            "metric": row[6],
            "control_mode": row[7],
            "controls_count": row[8],
            "status": row[9],
            "period_start": row[10],
            "period_end": row[11],
            "created_at": row[12],
            "updated_at": row[13],
            "hypothesis_title": row[14],
            "product_title": row[15],
        }
        for row in rows
    ]


def get_hl_mvp_experiment(experiment_id: int, project_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    sql = """
        SELECT
            e.id,
            e.project_id,
            e.hypothesis_id,
            e.nm_id,
            e.change_type,
            e.change_note,
            e.metric,
            e.control_mode,
            e.controls_count,
            e.status,
            e.period_start,
            e.period_end,
            e.created_at,
            e.updated_at,
            h.title AS hypothesis_title,
            p.title AS product_title
        FROM hl_mvp_experiments e
        JOIN hypotheses h ON h.id = e.hypothesis_id
        LEFT JOIN products p ON p.project_id = e.project_id AND p.nm_id = e.nm_id
        WHERE e.id = :experiment_id
    """
    params: Dict[str, Any] = {"experiment_id": experiment_id}
    if project_id is not None:
        sql += " AND e.project_id = :project_id"
        params["project_id"] = project_id

    with engine.connect() as conn:
        row = conn.execute(text(sql), params).fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "project_id": row[1],
        "hypothesis_id": row[2],
        "nm_id": row[3],
        "change_type": row[4],
        "change_note": row[5],
        "metric": row[6],
        "control_mode": row[7],
        "controls_count": row[8],
        "status": row[9],
        "period_start": row[10],
        "period_end": row[11],
        "created_at": row[12],
        "updated_at": row[13],
        "hypothesis_title": row[14],
        "product_title": row[15],
    }


def nm_id_in_active_hl_mvp_test(
    project_id: int,
    nm_id: int,
    exclude_experiment_id: Optional[int] = None,
) -> bool:
    sql = """
        SELECT 1
        FROM hl_mvp_experiments e
        WHERE e.project_id = :project_id
          AND e.nm_id = :nm_id
          AND e.status IN ('draft', 'running')
    """
    params: Dict[str, Any] = {"project_id": project_id, "nm_id": nm_id}

    if exclude_experiment_id is not None:
        sql += " AND e.id != :exclude_experiment_id"
        params["exclude_experiment_id"] = exclude_experiment_id

    with engine.connect() as conn:
        return conn.execute(text(sql), params).fetchone() is not None


def start_hl_mvp_experiment(experiment_id: int, project_id: int) -> Optional[Dict[str, Any]]:
    experiment = get_hl_mvp_experiment(experiment_id, project_id)
    if not experiment or experiment["status"] != "draft":
        return None
    if nm_id_in_active_hl_mvp_test(project_id, experiment["nm_id"], exclude_experiment_id=experiment_id):
        return None

    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE hl_mvp_experiments
                SET status = 'running', updated_at = NOW(), period_start = COALESCE(period_start, :period_start)
                WHERE id = :experiment_id
                """
            ),
            {"experiment_id": experiment_id, "period_start": now.date()},
        )
        conn.execute(
            text(
                """
                INSERT INTO hl_mvp_runs (experiment_id, started_at, status)
                VALUES (:experiment_id, :started_at, 'running')
                """
            ),
            {"experiment_id": experiment_id, "started_at": now},
        )

    return get_hl_mvp_experiment(experiment_id, project_id)


def confirm_hl_mvp_run(run_id: int, project_id: int) -> bool:
    with engine.begin() as conn:
        run_row = conn.execute(
            text(
                """
                SELECT run.id
                FROM hl_mvp_runs run
                JOIN hl_mvp_experiments exp ON exp.id = run.experiment_id
                WHERE run.id = :run_id AND exp.project_id = :project_id
                """
            ),
            {"run_id": run_id, "project_id": project_id},
        ).fetchone()
        if run_row is None:
            return False

        row = conn.execute(
            text(
                """
                UPDATE hl_mvp_runs
                SET change_confirmed_at = :confirmed_at
                WHERE id = :run_id
                RETURNING id
                """
            ),
            {"run_id": run_id, "confirmed_at": datetime.now(timezone.utc)},
        ).fetchone()
    return row is not None


def stop_hl_mvp_experiment(experiment_id: int, project_id: int) -> Optional[Dict[str, Any]]:
    experiment = get_hl_mvp_experiment(experiment_id, project_id)
    if not experiment or experiment["status"] != "running":
        return None

    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        run_row = conn.execute(
            text(
                """
                UPDATE hl_mvp_runs
                SET ended_at = :ended_at, status = 'completed'
                WHERE experiment_id = :experiment_id AND status = 'running'
                RETURNING id
                """
            ),
            {"experiment_id": experiment_id, "ended_at": now},
        ).fetchone()
        if run_row is None:
            return None

        conn.execute(
            text(
                """
                UPDATE hl_mvp_experiments
                SET status = 'completed', updated_at = NOW(), period_end = :period_end
                WHERE id = :experiment_id
                """
            ),
            {"experiment_id": experiment_id, "period_end": now.date()},
        )
        conn.execute(
            text(
                """
                INSERT INTO hl_mvp_results (run_id, control_mode, computed_at)
                SELECT :run_id, e.control_mode, :computed_at
                FROM hl_mvp_experiments e
                WHERE e.id = :experiment_id
                """
            ),
            {
                "run_id": run_row[0],
                "computed_at": now,
                "experiment_id": experiment_id,
            },
        )

    return get_hl_mvp_experiment(experiment_id, project_id)


def list_hl_mvp_runs(experiment_id: int) -> List[Dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, experiment_id, started_at, change_confirmed_at, ended_at, status
                FROM hl_mvp_runs
                WHERE experiment_id = :experiment_id
                ORDER BY id
                """
            ),
            {"experiment_id": experiment_id},
        ).fetchall()

    return [
        {
            "id": row[0],
            "experiment_id": row[1],
            "started_at": row[2],
            "change_confirmed_at": row[3],
            "ended_at": row[4],
            "status": row[5],
        }
        for row in rows
    ]


def get_latest_result_for_experiment(experiment_id: int) -> Optional[Dict[str, Any]]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    res.id,
                    res.run_id,
                    res.control_mode,
                    res.did_effect,
                    res.p_value,
                    res.ci_low,
                    res.ci_high,
                    res.pretrend_pass,
                    res.before_after_delta,
                    res.computed_at
                FROM hl_mvp_results res
                JOIN hl_mvp_runs run ON run.id = res.run_id
                WHERE run.experiment_id = :experiment_id
                ORDER BY res.computed_at DESC
                LIMIT 1
                """
            ),
            {"experiment_id": experiment_id},
        ).fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "run_id": row[1],
        "control_mode": row[2],
        "did_effect": float(row[3]) if row[3] is not None else None,
        "p_value": float(row[4]) if row[4] is not None else None,
        "ci_low": float(row[5]) if row[5] is not None else None,
        "ci_high": float(row[6]) if row[6] is not None else None,
        "pretrend_pass": row[7],
        "before_after_delta": float(row[8]) if row[8] is not None else None,
        "computed_at": row[9],
    }
