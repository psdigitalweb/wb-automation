"""Transactional persistence for WB card content versions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from sqlalchemy import text

from app import settings
from app.db import engine
from app.services.wb_product_content.normalization import (
    NORMALIZATION_VERSION,
    build_content_diff,
    content_hash,
    main_photo_url,
    normalize_wb_card_content,
    parse_card_payload,
)
from app.services.product_identity import resolve_marketplace_product_id


def history_enabled_for_project(project_id: int) -> bool:
    if not settings.WB_CONTENT_HISTORY_ENABLED:
        return False
    allowlist = settings.WB_CONTENT_HISTORY_PROJECT_ALLOWLIST
    return not allowlist or int(project_id) in allowlist


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def source_updated_at(payload: Mapping[str, Any]) -> Optional[datetime]:
    return _parse_datetime(
        payload.get("updatedAt")
        or payload.get("updated_at")
        or payload.get("updateAt")
    )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_param(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return _json(value)
    return value


def _product_params(row: Mapping[str, Any], project_id: int) -> Dict[str, Any]:
    return {
        "project_id": int(project_id),
        "nm_id": int(row["nm_id"]),
        "vendor_code": row.get("vendor_code"),
        "title": row.get("title"),
        "brand": row.get("brand"),
        "subject_id": row.get("subject_id"),
        "subject_name": row.get("subject_name"),
        "description": row.get("description"),
        "price_u": row.get("price_u"),
        "sale_price_u": row.get("sale_price_u"),
        "rating": row.get("rating"),
        "feedbacks": row.get("feedbacks"),
        "sizes": _json_param(row.get("sizes")),
        "colors": _json_param(row.get("colors")),
        "pics": _json_param(row.get("pics")),
        "dimensions": _json_param(row.get("dimensions")),
        "characteristics": _json_param(row.get("characteristics")),
        "created_at_api": row.get("created_at_api"),
        "need_kiz": row.get("need_kiz"),
        "raw": _json_param(row.get("raw")),
    }


_INSERT_PRODUCT_SQL = text(
    """
    INSERT INTO products (
        project_id, nm_id, vendor_code, title, brand, subject_id, subject_name,
        description, price_u, sale_price_u, rating, feedbacks, sizes, colors,
        pics, dimensions, characteristics, created_at_api, need_kiz, raw,
        updated_at, first_seen_at
    ) VALUES (
        :project_id, :nm_id, :vendor_code, :title, :brand, :subject_id, :subject_name,
        :description, :price_u, :sale_price_u, :rating, :feedbacks,
        CAST(:sizes AS jsonb), CAST(:colors AS jsonb), CAST(:pics AS jsonb),
        CAST(:dimensions AS jsonb), CAST(:characteristics AS jsonb),
        :created_at_api, :need_kiz, CAST(:raw AS jsonb), now(), now()
    )
    ON CONFLICT (project_id, nm_id) DO NOTHING
    """
)


_UPDATE_PRODUCT_SQL = text(
    """
    UPDATE products
    SET vendor_code = :vendor_code,
        title = :title,
        brand = :brand,
        subject_id = :subject_id,
        subject_name = :subject_name,
        description = :description,
        price_u = :price_u,
        sale_price_u = :sale_price_u,
        rating = :rating,
        feedbacks = :feedbacks,
        sizes = CAST(:sizes AS jsonb),
        colors = CAST(:colors AS jsonb),
        pics = CAST(:pics AS jsonb),
        dimensions = CAST(:dimensions AS jsonb),
        characteristics = CAST(:characteristics AS jsonb),
        created_at_api = :created_at_api,
        need_kiz = :need_kiz,
        raw = CAST(:raw AS jsonb),
        content_hash = :content_hash,
        content_version = :content_version,
        content_changed_at = CASE WHEN :content_changed THEN :observed_at ELSE content_changed_at END,
        content_last_seen_at = :observed_at,
        wb_content_updated_at = :source_updated_at,
        main_photo_asset_hash = CASE
            WHEN :clear_main_photo_asset_hash THEN NULL
            ELSE COALESCE(:main_photo_asset_hash, main_photo_asset_hash)
        END,
        updated_at = now()
    WHERE project_id = :project_id AND nm_id = :nm_id
    """
)


def persist_product_content(
    *,
    row: Mapping[str, Any],
    project_id: int,
    ingest_run_id: Optional[int],
    observed_at: Optional[datetime] = None,
    photo_attempt: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Persist current product, append a version on change, and rotate main-photo periods."""
    now = observed_at or datetime.now(timezone.utc)
    payload = parse_card_payload(row.get("raw"))
    content = normalize_wb_card_content(payload)
    new_hash = content_hash(content)
    source_at = source_updated_at(payload)
    nm_id = int(row["nm_id"])
    params = _product_params(row, project_id)

    with engine.begin() as conn:
        marketplace_product_id = resolve_marketplace_product_id(
            project_id=project_id,
            marketplace_code="wildberries",
            marketplace_item_id=nm_id,
            connection=conn,
        )
        conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"wb-product-content:{int(project_id)}:{nm_id}"},
        )
        current = conn.execute(
            text(
                """
                SELECT content_hash, content_version, main_photo_asset_hash,
                       wb_content_updated_at
                FROM products
                WHERE project_id = :project_id AND nm_id = :nm_id
                FOR UPDATE
                """
            ),
            {"project_id": int(project_id), "nm_id": nm_id},
        ).mappings().first()
        was_new = current is None
        if was_new:
            conn.execute(_INSERT_PRODUCT_SQL, params)
            current = {
                "content_hash": None,
                "content_version": None,
                "main_photo_asset_hash": None,
                "wb_content_updated_at": None,
            }

        old_version = int(current.get("content_version") or 0)
        old_snapshot = None
        if old_version > 0:
            old_snapshot = conn.execute(
                text(
                    """
                    SELECT content_snapshot
                    FROM wb_product_content_versions
                    WHERE project_id = :project_id
                      AND (
                          marketplace_product_id = :marketplace_product_id
                          OR (marketplace_product_id IS NULL AND nm_id = :nm_id)
                      )
                      AND version_no = :version_no
                    """
                ),
                {
                    "project_id": int(project_id),
                    "marketplace_product_id": marketplace_product_id,
                    "nm_id": nm_id,
                    "version_no": old_version,
                },
            ).scalar_one_or_none()

        attempt_hash = photo_attempt.get("sha256") if photo_attempt else None
        binary_photo_changed = bool(
            attempt_hash
            and current.get("main_photo_asset_hash")
            and attempt_hash != current.get("main_photo_asset_hash")
        )
        changed = current.get("content_hash") != new_hash or binary_photo_changed
        version_no = old_version + 1 if changed else old_version
        version_id: Optional[int] = None
        changes: Dict[str, Any] = {}
        change_types: list[str] = []

        if changed:
            changes, change_types = build_content_diff(old_snapshot, content)
            if binary_photo_changed:
                changes["mainPhotoFile"] = {
                    "oldSha256": current.get("main_photo_asset_hash"),
                    "newSha256": attempt_hash,
                }
                if "media" not in change_types:
                    change_types.append("media")
            version_id = conn.execute(
                text(
                    """
                    INSERT INTO wb_product_content_versions (
                        project_id, marketplace_product_id, nm_id,
                        version_no, event_type, content_hash,
                        normalization_version, content_snapshot, changed_fields,
                        change_types, observed_at, source_updated_at, ingest_run_id
                    ) VALUES (
                        :project_id, :marketplace_product_id, :nm_id,
                        :version_no, :event_type, :content_hash,
                        :normalization_version, CAST(:content_snapshot AS jsonb),
                        CAST(:changed_fields AS jsonb), CAST(:change_types AS jsonb),
                        :observed_at, :source_updated_at, :ingest_run_id
                    )
                    RETURNING id
                    """
                ),
                {
                    "project_id": int(project_id),
                    "marketplace_product_id": marketplace_product_id,
                    "nm_id": nm_id,
                    "version_no": version_no,
                    "event_type": "initial" if old_version == 0 else "changed",
                    "content_hash": new_hash,
                    "normalization_version": NORMALIZATION_VERSION,
                    "content_snapshot": _json(content),
                    "changed_fields": _json(changes),
                    "change_types": _json(change_types),
                    "observed_at": now,
                    "source_updated_at": source_at,
                    "ingest_run_id": int(ingest_run_id) if ingest_run_id is not None else None,
                },
            ).scalar_one()

        asset_id: Optional[int] = None
        if photo_attempt and photo_attempt.get("status") == "stored":
            asset_id = conn.execute(
                text(
                    """
                    INSERT INTO wb_product_main_photo_assets (
                        project_id, marketplace_product_id, nm_id,
                        sha256, storage_path, source_url,
                        content_type, file_size, downloaded_at
                    ) VALUES (
                        :project_id, :marketplace_product_id, :nm_id,
                        :sha256, :storage_path, :source_url,
                        :content_type, :file_size, :downloaded_at
                    )
                    ON CONFLICT (project_id, nm_id, sha256) DO UPDATE SET
                        source_url = EXCLUDED.source_url
                    RETURNING id
                    """
                ),
                {
                    "project_id": int(project_id),
                    "marketplace_product_id": marketplace_product_id,
                    "nm_id": nm_id,
                    "sha256": photo_attempt["sha256"],
                    "storage_path": photo_attempt["storage_path"],
                    "source_url": photo_attempt.get("source_url"),
                    "content_type": photo_attempt.get("content_type"),
                    "file_size": int(photo_attempt.get("file_size") or 0),
                    "downloaded_at": now,
                },
            ).scalar_one()

        new_main_url = main_photo_url(content)
        open_period = conn.execute(
            text(
                """
                SELECT id, source_url, asset_id, archive_status,
                       (SELECT sha256 FROM wb_product_main_photo_assets a WHERE a.id = p.asset_id) AS asset_hash
                FROM wb_product_main_photo_periods p
                WHERE project_id = :project_id
                  AND (
                      marketplace_product_id = :marketplace_product_id
                      OR (marketplace_product_id IS NULL AND nm_id = :nm_id)
                  )
                  AND observed_to IS NULL
                FOR UPDATE
                """
            ),
            {
                "project_id": int(project_id),
                "marketplace_product_id": marketplace_product_id,
                "nm_id": nm_id,
            },
        ).mappings().first()
        effective_asset_hash = photo_attempt.get("sha256") if photo_attempt else None
        rotate_period = bool(
            new_main_url
            and (
                open_period is None
                or open_period.get("source_url") != new_main_url
                or (
                    effective_asset_hash
                    and open_period.get("asset_hash")
                    and effective_asset_hash != open_period.get("asset_hash")
                )
                or (
                    effective_asset_hash
                    and open_period.get("archive_status") != "stored"
                )
            )
        )
        if open_period and new_main_url is None:
            conn.execute(
                text(
                    """
                    UPDATE wb_product_main_photo_periods
                    SET observed_to = :observed_at, updated_at = :observed_at
                    WHERE id = :id
                    """
                ),
                {"id": open_period["id"], "observed_at": now},
            )
        elif rotate_period:
            if open_period:
                conn.execute(
                    text(
                        """
                        UPDATE wb_product_main_photo_periods
                        SET observed_to = :observed_at, updated_at = :observed_at
                        WHERE id = :id
                        """
                    ),
                    {"id": open_period["id"], "observed_at": now},
                )
            attempt_status = photo_attempt.get("status") if photo_attempt else "pending"
            conn.execute(
                text(
                    """
                    INSERT INTO wb_product_main_photo_periods (
                        project_id, marketplace_product_id, nm_id,
                        content_version_id, asset_id, source_url,
                        observed_from, source_updated_at, ingest_run_id,
                        archive_status, archive_error, updated_at
                    ) VALUES (
                        :project_id, :marketplace_product_id, :nm_id,
                        :content_version_id, :asset_id, :source_url,
                        :observed_from, :source_updated_at, :ingest_run_id,
                        :archive_status, :archive_error, :observed_from
                    )
                    """
                ),
                {
                    "project_id": int(project_id),
                    "marketplace_product_id": marketplace_product_id,
                    "nm_id": nm_id,
                    "content_version_id": version_id,
                    "asset_id": asset_id,
                    "source_url": new_main_url,
                    "observed_from": now,
                    "source_updated_at": source_at,
                    "ingest_run_id": int(ingest_run_id) if ingest_run_id is not None else None,
                    "archive_status": attempt_status,
                    "archive_error": (photo_attempt or {}).get("error"),
                },
            )
        elif open_period and photo_attempt and photo_attempt.get("status") == "failed":
            conn.execute(
                text(
                    """
                    UPDATE wb_product_main_photo_periods
                    SET archive_status = 'failed',
                        archive_error = :archive_error,
                        updated_at = :observed_at
                    WHERE id = :id AND archive_status != 'stored'
                    """
                ),
                {
                    "id": open_period["id"],
                    "archive_error": photo_attempt.get("error"),
                    "observed_at": now,
                },
            )

        update_params = {
            **params,
            "content_hash": new_hash,
            "content_version": version_no,
            "content_changed": changed,
            "observed_at": now,
            "source_updated_at": source_at,
            "main_photo_asset_hash": attempt_hash,
            "clear_main_photo_asset_hash": bool(
                main_photo_url(old_snapshot or {}) != new_main_url
                and attempt_hash is None
            ),
        }
        conn.execute(_UPDATE_PRODUCT_SQL, update_params)

    return {
        "nm_id": nm_id,
        "marketplace_product_id": marketplace_product_id,
        "initial": changed and old_version == 0,
        "changed": changed,
        "version_no": version_no,
        "change_types": change_types,
        "photo_status": (photo_attempt or {}).get("status"),
        "photo_reused": bool((photo_attempt or {}).get("reused")),
    }
