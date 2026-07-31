"""DAO for global hypotheses and hypothesis_versions."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import text

from app.db import engine


def list_hypotheses_with_latest_version(
    query: Optional[str] = None,
    limit: int = 50,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    with engine.connect() as conn:
        sql = """
            SELECT
                h.id,
                h.key,
                h.title,
                h.description,
                h.domain,
                h.hypothesis_type,
                h.status,
                h.created_at,
                h.updated_at,
                lv.id AS lv_id,
                lv.version AS lv_version,
                lv.primary_metric_key AS lv_primary_metric_key
            FROM hypotheses h
            LEFT JOIN LATERAL (
                SELECT id, version, primary_metric_key
                FROM hypothesis_versions
                WHERE hypothesis_id = h.id
                ORDER BY version DESC
                LIMIT 1
            ) lv ON true
            WHERE 1=1
        """
        params: Dict[str, Any] = {"limit": limit}
        if query and query.strip():
            sql += " AND (h.title ILIKE :pattern OR h.key ILIKE :pattern)"
            params["pattern"] = f"%{query.strip()}%"
        if status and status.strip():
            sql += " AND h.status = :status"
            params["status"] = status.strip()
        sql += " ORDER BY h.updated_at DESC NULLS LAST, h.id DESC LIMIT :limit"
        rows = conn.execute(text(sql), params).fetchall()

    return [
        {
            "id": row[0],
            "key": row[1],
            "title": row[2],
            "description": row[3],
            "domain": row[4],
            "hypothesis_type": row[5],
            "status": row[6],
            "created_at": row[7],
            "updated_at": row[8],
            "latest_version": {
                "id": row[9],
                "version": row[10],
                "primary_metric_key": row[11],
            } if row[9] is not None else None,
        }
        for row in rows
    ]


def get_hypothesis_by_id(hypothesis_id: int) -> Optional[Dict[str, Any]]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    h.id,
                    h.key,
                    h.title,
                    h.description,
                    h.domain,
                    h.hypothesis_type,
                    h.status,
                    h.created_at,
                    h.updated_at,
                    lv.id AS lv_id,
                    lv.version AS lv_version,
                    lv.primary_metric_key AS lv_primary_metric_key
                FROM hypotheses h
                LEFT JOIN LATERAL (
                    SELECT id, version, primary_metric_key
                    FROM hypothesis_versions
                    WHERE hypothesis_id = h.id
                    ORDER BY version DESC
                    LIMIT 1
                ) lv ON true
                WHERE h.id = :hypothesis_id
                """
            ),
            {"hypothesis_id": hypothesis_id},
        ).fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "key": row[1],
        "title": row[2],
        "description": row[3],
        "domain": row[4],
        "hypothesis_type": row[5],
        "status": row[6],
        "created_at": row[7],
        "updated_at": row[8],
        "latest_version": {
            "id": row[9],
            "version": row[10],
            "primary_metric_key": row[11],
        } if row[9] is not None else None,
    }


def create_hypothesis_with_version(
    key: str,
    title: str,
    *,
    description: Optional[str] = None,
    domain: Optional[str] = None,
    hypothesis_type: Optional[str] = None,
    hypothesis_text: Optional[str] = None,
    primary_metric_key: Optional[str] = None,
) -> Dict[str, Any]:
    key_clean = key.strip()

    with engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id FROM hypotheses WHERE key = :key"),
            {"key": key_clean},
        ).fetchone()
    if existing:
        raise ValueError("Hypothesis with this key already exists")

    with engine.begin() as conn:
        created = conn.execute(
            text(
                """
                INSERT INTO hypotheses (key, title, description, domain, hypothesis_type, status)
                VALUES (:key, :title, :description, :domain, :hypothesis_type, 'draft')
                RETURNING id, key, title, description, domain, hypothesis_type, status, created_at, updated_at
                """
            ),
            {
                "key": key_clean,
                "title": title.strip(),
                "description": description.strip() if description else None,
                "domain": domain.strip() if domain else None,
                "hypothesis_type": hypothesis_type.strip() if hypothesis_type else None,
            },
        ).fetchone()

        version = conn.execute(
            text(
                """
                INSERT INTO hypothesis_versions (
                    hypothesis_id,
                    version,
                    hypothesis_text,
                    primary_metric_key,
                    guardrails_jsonb,
                    action_washout_policy_jsonb,
                    requirements_jsonb
                )
                VALUES (
                    :hypothesis_id,
                    1,
                    :hypothesis_text,
                    :primary_metric_key,
                    '{}'::jsonb,
                    '{}'::jsonb,
                    '{}'::jsonb
                )
                RETURNING id, version, primary_metric_key
                """
            ),
            {
                "hypothesis_id": created[0],
                "hypothesis_text": hypothesis_text.strip() if hypothesis_text else None,
                "primary_metric_key": primary_metric_key.strip() if primary_metric_key else None,
            },
        ).fetchone()

    return {
        "id": created[0],
        "key": created[1],
        "title": created[2],
        "description": created[3],
        "domain": created[4],
        "hypothesis_type": created[5],
        "status": created[6],
        "created_at": created[7],
        "updated_at": created[8],
        "latest_version": {
            "id": version[0],
            "version": version[1],
            "primary_metric_key": version[2],
        },
    }


def update_hypothesis(
    hypothesis_id: int,
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    domain: Optional[str] = None,
    hypothesis_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    updates = ["updated_at = now()"]
    params: Dict[str, Any] = {"hypothesis_id": hypothesis_id}

    if title is not None:
        updates.append("title = :title")
        params["title"] = title.strip()
    if description is not None:
        updates.append("description = :description")
        params["description"] = description.strip() if description else None
    if status is not None:
        updates.append("status = :status")
        params["status"] = status.strip()
    if domain is not None:
        updates.append("domain = :domain")
        params["domain"] = domain.strip() if domain else None
    if hypothesis_type is not None:
        updates.append("hypothesis_type = :hypothesis_type")
        params["hypothesis_type"] = hypothesis_type.strip() if hypothesis_type else None

    with engine.begin() as conn:
        conn.execute(
            text(f"UPDATE hypotheses SET {', '.join(updates)} WHERE id = :hypothesis_id"),
            params,
        )

    return get_hypothesis_by_id(hypothesis_id)
