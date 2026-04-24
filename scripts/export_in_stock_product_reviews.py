#!/usr/bin/env python3
"""Export JSONL of in-stock products with all WB reviews from DB.

Default behavior (matches plan): project_id=1, stock_type=any, min_qty=1,
only products that have at least 1 review (wb_feedback_snapshots).

Usage examples:
  python scripts/export_in_stock_product_reviews.py
  python scripts/export_in_stock_product_reviews.py --project-id 2 --stock-type fbs
  python scripts/export_in_stock_product_reviews.py --out outputs/reviews.jsonl

In Docker:
  docker compose -f infra/docker/docker-compose.yml exec api \
    python /app/scripts/export_in_stock_product_reviews.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402

from app.db import engine  # noqa: E402
from app import settings as app_settings  # noqa: E402


def _clean_optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _photo_urls_from_raw(raw: Any) -> List[str]:
    if raw is None:
        return []
    try:
        if isinstance(raw, str):
            raw = json.loads(raw)
        photo_links = raw.get("photoLinks") if isinstance(raw, dict) else None
        if not isinstance(photo_links, list):
            return []
        urls: List[str] = []
        for item in photo_links:
            if isinstance(item, str):
                candidate = item.strip()
            elif isinstance(item, dict):
                candidate = (
                    item.get("fullSize")
                    or item.get("big")
                    or item.get("miniSize")
                    or item.get("url")
                )
                candidate = str(candidate).strip() if candidate is not None else ""
            else:
                candidate = ""
            if candidate and candidate not in urls:
                urls.append(candidate)
        return urls
    except Exception:
        return []


def _answer_text_from_raw(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    try:
        if isinstance(raw, str):
            raw = json.loads(raw)
        answer = raw.get("answer") if isinstance(raw, dict) else None
        if isinstance(answer, dict):
            return _clean_optional_text(answer.get("text"))
        return _clean_optional_text(answer)
    except Exception:
        return None


def _review_from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row.get("raw")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = None

    return {
        "external_id": str(row.get("external_id") or ""),
        "nm_id": int(row["nm_id"]),
        "created_date": (
            row.get("created_date").isoformat()
            if getattr(row.get("created_date"), "isoformat", None)
            else None
        ),
        "rating": int(row["product_valuation"]) if row.get("product_valuation") is not None else None,
        "user_name": _clean_optional_text((raw or {}).get("userName") if isinstance(raw, dict) else None),
        "text": _clean_optional_text((raw or {}).get("text") if isinstance(raw, dict) else None),
        "pros": _clean_optional_text((raw or {}).get("pros") if isinstance(raw, dict) else None),
        "cons": _clean_optional_text((raw or {}).get("cons") if isinstance(raw, dict) else None),
        "answer_text": _answer_text_from_raw(raw),
        "photo_urls": _photo_urls_from_raw(raw),
        "video_url": _clean_optional_text(
            ((raw or {}).get("video") or {}).get("link")
            if isinstance((raw or {}).get("video"), dict)
            else None
        ),
        "is_answered": bool(row.get("is_answered")),
        "has_media": bool(row.get("has_media")),
        "is_archived": bool(row.get("is_archived")),
        "source_endpoint": _clean_optional_text(row.get("source_endpoint")),
    }


def export_jsonl(
    *,
    project_id: int,
    stock_type: str,
    min_qty: int,
    out_path: Path,
    only_with_reviews: bool,
) -> Dict[str, Any]:
    if not only_with_reviews:
        raise ValueError(
            "only_with_reviews=false is not supported by this exporter (requested output is only products with reviews)"
        )
    if stock_type not in ("any", "fbs", "fbo"):
        raise ValueError("stock_type must be one of: any, fbs, fbo")
    if min_qty <= 0:
        raise ValueError("min_qty must be >= 1")

    sql = text(
        """
        WITH
        prod_nm_ids AS (
            SELECT DISTINCT p.nm_id::bigint AS nm_id
            FROM products p
            WHERE p.project_id = :project_id
              AND p.nm_id IS NOT NULL
        ),
        fbs_run AS (
            SELECT MAX(snapshot_at) AS run_at
            FROM stock_snapshots
            WHERE project_id = :project_id
        ),
        fbs_totals AS (
            SELECT
                ss.nm_id::bigint AS nm_id,
                SUM(COALESCE(ss.quantity, 0))::bigint AS fbs_qty
            FROM stock_snapshots ss
            JOIN fbs_run r ON ss.snapshot_at = r.run_at
            WHERE ss.project_id = :project_id
              AND ss.nm_id IS NOT NULL
            GROUP BY ss.nm_id
        ),
        fbo_wh_latest AS (
            SELECT DISTINCT ON (s.nm_id, s.warehouse_name)
                s.nm_id::bigint AS nm_id,
                s.warehouse_name,
                COALESCE(s.quantity, 0)::bigint AS quantity,
                COALESCE(s.last_change_date, s.snapshot_at) AS updated_at
            FROM supplier_stock_snapshots s
            JOIN prod_nm_ids pn ON pn.nm_id = s.nm_id
            WHERE s.nm_id IS NOT NULL
            ORDER BY s.nm_id, s.warehouse_name, COALESCE(s.last_change_date, s.snapshot_at) DESC
        ),
        fbo_totals AS (
            SELECT
                nm_id,
                SUM(quantity)::bigint AS fbo_qty,
                MAX(updated_at) AS fbo_updated_at
            FROM fbo_wh_latest
            GROUP BY nm_id
        ),
        in_stock AS (
            SELECT
                pn.nm_id,
                COALESCE(ft.fbs_qty, 0)::bigint AS fbs_qty,
                fr.run_at AS fbs_run_at,
                COALESCE(fo.fbo_qty, 0)::bigint AS fbo_qty,
                fo.fbo_updated_at AS fbo_updated_at
            FROM prod_nm_ids pn
            LEFT JOIN fbs_totals ft ON ft.nm_id = pn.nm_id
            LEFT JOIN fbs_run fr ON TRUE
            LEFT JOIN fbo_totals fo ON fo.nm_id = pn.nm_id
            WHERE (
                (:stock_type = 'any' AND (COALESCE(ft.fbs_qty, 0) >= :min_qty OR COALESCE(fo.fbo_qty, 0) >= :min_qty))
                OR (:stock_type = 'fbs' AND COALESCE(ft.fbs_qty, 0) >= :min_qty)
                OR (:stock_type = 'fbo' AND COALESCE(fo.fbo_qty, 0) >= :min_qty)
            )
        )
        SELECT
            s.nm_id,
            p.vendor_code,
            p.title,
            p.subject_name AS wb_category,
            s.fbs_qty,
            s.fbs_run_at,
            s.fbo_qty,
            s.fbo_updated_at,
            fs.external_id,
            fs.created_date,
            fs.product_valuation,
            fs.is_answered,
            fs.has_media,
            fs.is_archived,
            fs.source_endpoint,
            fs.raw
        FROM in_stock s
        JOIN products p
          ON p.project_id = :project_id
         AND p.nm_id = s.nm_id
        JOIN wb_feedback_snapshots fs
          ON fs.project_id = :project_id
         AND fs.nm_id = s.nm_id
        ORDER BY s.nm_id ASC, fs.created_date DESC NULLS LAST, fs.id DESC
        """
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)

    exported_products = 0
    exported_reviews = 0

    current_nm_id: Optional[int] = None
    current_product: Optional[Dict[str, Any]] = None
    current_reviews: List[Dict[str, Any]] = []

    def _flush(handle) -> None:
        nonlocal exported_products, exported_reviews, current_product, current_reviews
        if current_product is None:
            return
        current_product["reviews"] = current_reviews
        current_product["reviews_count"] = len(current_reviews)
        handle.write(json.dumps(current_product, ensure_ascii=False) + "\n")
        exported_products += 1
        exported_reviews += len(current_reviews)
        current_product = None
        current_reviews = []

    params = {
        "project_id": project_id,
        "stock_type": stock_type,
        "min_qty": int(min_qty),
        "only_with_reviews": bool(only_with_reviews),
    }

    # Best-effort streaming: fetch in batches to avoid holding everything in memory.
    with engine.connect() as conn, out_path.open("w", encoding="utf-8") as f:
        result = conn.execute(sql, params)
        while True:
            batch = result.mappings().fetchmany(5000)
            if not batch:
                break
            for row in batch:
                nm_id = int(row["nm_id"])
                if current_nm_id is None:
                    current_nm_id = nm_id

                if nm_id != current_nm_id:
                    _flush(f)
                    current_nm_id = nm_id

                if current_product is None:
                    current_product = {
                        "project_id": project_id,
                        "nm_id": nm_id,
                        "vendor_code": row.get("vendor_code"),
                        "title": row.get("title"),
                        "wb_category": row.get("wb_category"),
                        "stock_type": stock_type,
                        "stock": {
                            "fbs_qty": int(row.get("fbs_qty") or 0),
                            "fbs_run_at": (
                                row.get("fbs_run_at").isoformat()
                                if getattr(row.get("fbs_run_at"), "isoformat", None)
                                else None
                            ),
                            "fbo_qty": int(row.get("fbo_qty") or 0),
                            "fbo_updated_at": (
                                row.get("fbo_updated_at").isoformat()
                                if getattr(row.get("fbo_updated_at"), "isoformat", None)
                                else None
                            ),
                        },
                    }

                current_reviews.append(_review_from_row(dict(row)))

        _flush(f)

    return {
        "out": str(out_path),
        "project_id": project_id,
        "stock_type": stock_type,
        "min_qty": min_qty,
        "only_with_reviews": only_with_reviews,
        "exported_products": exported_products,
        "exported_reviews": exported_reviews,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export JSONL of in-stock products with all WB reviews from DB"
    )
    parser.add_argument("--project-id", type=int, default=1, help="Project ID")
    parser.add_argument(
        "--stock-type",
        type=str,
        choices=["any", "fbs", "fbo"],
        default="any",
        help="Which stock definition to use for in-stock filter",
    )
    parser.add_argument("--min-qty", type=int, default=1, help="Min qty to treat as in-stock (>=1)")
    parser.add_argument(
        "--out",
        type=str,
        default="outputs/in_stock_reviews_project1.jsonl",
        help="Output JSONL path",
    )
    parser.add_argument(
        "--only-with-reviews",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Only include products that have at least one review",
    )
    args = parser.parse_args()

    out_path = Path(args.out)
    try:
        summary = export_jsonl(
            project_id=int(args.project_id),
            stock_type=str(args.stock_type),
            min_qty=int(args.min_qty),
            out_path=out_path,
            only_with_reviews=bool(args.only_with_reviews),
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    except OperationalError as e:
        host = getattr(app_settings, "POSTGRES_HOST", None)
        port = getattr(app_settings, "POSTGRES_PORT", None)
        db = getattr(app_settings, "POSTGRES_DB", None)
        user = getattr(app_settings, "POSTGRES_USER", None)
        print("ERROR: cannot connect to Postgres via app settings.")
        print(f"Current env-based target: host={host!r} port={port!r} db={db!r} user={user!r}")
        print()
        print("Fix options:")
        print("  1) Run inside Docker (recommended):")
        print("     docker compose -f infra/docker/docker-compose.yml exec api python /app/scripts/export_in_stock_product_reviews.py")
        print("  2) Or run locally against forwarded DB port:")
        print("     # PowerShell")
        print("     $env:POSTGRES_HOST='localhost'")
        print("     $env:POSTGRES_PORT='5432'")
        print("     # cmd.exe")
        print("     set POSTGRES_HOST=localhost")
        print("     set POSTGRES_PORT=5432")
        print("     python scripts/export_in_stock_product_reviews.py")
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
