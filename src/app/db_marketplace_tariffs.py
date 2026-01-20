"""Marketplace-level storage and service layer for WB tariffs snapshots.

This module stores raw API payloads in `marketplace_api_snapshots` table and
provides simple deduplicating `save_snapshot` and `get_latest_snapshot` helpers.
"""

import json
import hashlib
from datetime import date, datetime
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.db import engine


def _compute_payload_hash(payload: Any) -> str:
    """Compute deterministic SHA256 hash of JSON payload for deduplication."""
    # Normalize JSON: sort keys, no extra whitespace, keep non-ASCII as-is
    normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def save_snapshot(
    *,
    marketplace_code: str,
    data_domain: str,
    data_type: str,
    as_of_date: Optional[date],
    locale: Optional[str],
    request_params: Dict[str, Any],
    payload: Any,
    http_status: int,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """Insert new snapshot if payload changed compared to latest one for same slice.

    Returns dict with keys:
      - inserted: bool
      - skipped_reason: Optional[str]
      - snapshot_id: Optional[int]
    """
    payload_hash = _compute_payload_hash(payload) if payload is not None else ""

    key_params = {
        "marketplace_code": marketplace_code,
        "data_domain": data_domain,
        "data_type": data_type,
        "as_of_date": as_of_date,
        "locale": locale,
    }

    with engine.begin() as conn:
        # Fetch latest snapshot for this logical slice
        latest_row = conn.execute(
            text(
                """
                SELECT id, payload_hash
                FROM marketplace_api_snapshots
                WHERE marketplace_code = :marketplace_code
                  AND data_domain = :data_domain
                  AND data_type = :data_type
                  AND ((as_of_date IS NULL AND :as_of_date IS NULL)
                       OR (as_of_date = :as_of_date))
                  AND ((locale IS NULL AND :locale IS NULL)
                       OR (locale = :locale))
                ORDER BY fetched_at DESC
                LIMIT 1
                """
            ),
            key_params,
        ).mappings().first()

        if latest_row and latest_row.get("payload_hash") == payload_hash:
            print(
                "save_snapshot: skipped (same payload_hash) "
                f"marketplace={marketplace_code} domain={data_domain} "
                f"type={data_type} date={as_of_date} locale={locale}"
            )
            return {"inserted": False, "skipped_reason": "same_hash", "snapshot_id": latest_row["id"]}

        row = {
            **key_params,
            "request_params": json.dumps(request_params or {}, ensure_ascii=False),
            "payload": json.dumps(payload, ensure_ascii=False),
            "payload_hash": payload_hash,
            "http_status": http_status,
            "error": error,
        }

        result = conn.execute(
            text(
                """
                INSERT INTO marketplace_api_snapshots (
                    marketplace_code,
                    data_domain,
                    data_type,
                    as_of_date,
                    locale,
                    request_params,
                    payload,
                    payload_hash,
                    http_status,
                    error
                )
                VALUES (
                    :marketplace_code,
                    :data_domain,
                    :data_type,
                    :as_of_date,
                    :locale,
                    CAST(:request_params AS jsonb),
                    CAST(:payload AS jsonb),
                    :payload_hash,
                    :http_status,
                    :error
                )
                RETURNING id
                """
            ),
            row,
        )
        new_id = result.scalar_one()

    print(
        "save_snapshot: inserted id={id} marketplace={marketplace} domain={domain} "
        "type={type} date={date} locale={locale}".format(
            id=new_id,
            marketplace=marketplace_code,
            domain=data_domain,
            type=data_type,
            date=as_of_date,
            locale=locale,
        )
    )

    return {"inserted": True, "skipped_reason": None, "snapshot_id": new_id}


def get_latest_snapshot(
    *,
    marketplace_code: str,
    data_domain: str,
    data_type: str,
    as_of_date: Optional[date] = None,
    locale: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Get latest snapshot for given slice (marketplace, type, date, locale)."""
    params = {
        "marketplace_code": marketplace_code,
        "data_domain": data_domain,
        "data_type": data_type,
        "as_of_date": as_of_date,
        "locale": locale,
    }

    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    id,
                    marketplace_code,
                    data_domain,
                    data_type,
                    as_of_date,
                    locale,
                    request_params,
                    payload,
                    payload_hash,
                    fetched_at,
                    http_status,
                    error
                FROM marketplace_api_snapshots
                WHERE marketplace_code = :marketplace_code
                  AND data_domain = :data_domain
                  AND data_type = :data_type
                  AND ((as_of_date IS NULL AND :as_of_date IS NULL)
                       OR (as_of_date = :as_of_date))
                  AND ((locale IS NULL AND :locale IS NULL)
                       OR (locale = :locale))
                ORDER BY fetched_at DESC
                LIMIT 1
                """
            ),
            params,
        ).mappings().first()

    if not row:
        return None

    # request_params and payload are JSONB; depending on driver they may already be dicts
    result = dict(row)
    return result


def get_tariffs_status(
    marketplace_code: str = "wildberries",
    data_domain: str = "tariffs",
) -> Dict[str, Any]:
    """Aggregate latest tariffs snapshots per type for given marketplace.

    Always returns a dictionary with per-type info. If there are no snapshots at all,
    all fields will be None and no exceptions are raised.
    """
    with engine.connect() as conn:
        def _latest_for_type(data_type: str, locale_filter: Optional[str] = None) -> Dict[str, Any]:
            if locale_filter is not None:
                row = conn.execute(
                    text(
                        """
                        SELECT
                            fetched_at,
                            as_of_date,
                            locale
                        FROM marketplace_api_snapshots
                        WHERE marketplace_code = :marketplace_code
                          AND data_domain = :data_domain
                          AND data_type = :data_type
                          AND locale = :locale_filter
                        ORDER BY fetched_at DESC
                        LIMIT 1
                        """
                    ),
                    {
                        "marketplace_code": marketplace_code,
                        "data_domain": data_domain,
                        "data_type": data_type,
                        "locale_filter": locale_filter,
                    },
                ).mappings().first()
            else:
                row = conn.execute(
                    text(
                        """
                        SELECT
                            fetched_at,
                            as_of_date,
                            locale
                        FROM marketplace_api_snapshots
                        WHERE marketplace_code = :marketplace_code
                          AND data_domain = :data_domain
                          AND data_type = :data_type
                        ORDER BY fetched_at DESC
                        LIMIT 1
                        """
                    ),
                    {
                        "marketplace_code": marketplace_code,
                        "data_domain": data_domain,
                        "data_type": data_type,
                    },
                ).mappings().first()

            if not row:
                # No snapshots for this type (and locale, if applicable)
                return {
                    "latest_fetched_at": None,
                    "latest_as_of_date": None,
                    "locale": None,
                }

            latest_fetched_at = row.get("fetched_at")
            latest_as_of_date = row.get("as_of_date")
            locale = row.get("locale")

            # For commission we prefer explicit 'ru' locale when data exists
            if data_type == "commission" and locale_filter == "ru":
                locale = "ru"

            return {
                "latest_fetched_at": latest_fetched_at,
                "latest_as_of_date": latest_as_of_date,
                "locale": locale,
            }

        types: Dict[str, Dict[str, Any]] = {
            "commission": _latest_for_type("commission", locale_filter="ru"),
            "acceptance_coefficients": _latest_for_type("acceptance_coefficients"),
            "box": _latest_for_type("box"),
            "pallet": _latest_for_type("pallet"),
            "return": _latest_for_type("return"),
        }

    # Compute overall latest_fetched_at across all types
    latest_overall: Optional[datetime] = None
    for t in types.values():
        ts = t.get("latest_fetched_at")
        if ts is not None and (latest_overall is None or ts > latest_overall):
            latest_overall = ts

    return {
        "marketplace_code": marketplace_code,
        "data_domain": data_domain,
        "latest_fetched_at": latest_overall,
        "types": types,
    }


__all__ = ["save_snapshot", "get_latest_snapshot", "get_tariffs_status", "_compute_payload_hash"]

