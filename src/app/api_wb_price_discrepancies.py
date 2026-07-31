"""Project-scoped Wildberries price discrepancies endpoints.

This module exposes:
- GET /api/v1/projects/{project_id}/wildberries/price-discrepancies
- GET /api/v1/projects/{project_id}/wildberries/price-discrepancies/export.csv
- GET /api/v1/projects/{project_id}/wildberries/categories

Data is aggregated from:
- products (article, nm_id, title, category, photos)
- rrp_snapshots (RRP price + stock from XML/1C)
- price_snapshots (WB admin price + WB discount)
- frontend_catalog_price_snapshots (showcase_price + spp from WB frontend)
- stock_snapshots (WB stock quantities)

All heavy joins and computations (diff_rub/diff_percent/is_below_rrp) are done
in SQL so that filtering and sorting are correct at the database layer.
"""

from __future__ import annotations

import logging
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.db import engine
from app.services.product_identity import resolve_marketplace_product_id
from app.deps import allow_client_portal_read, get_current_active_user, get_project_membership, require_project_admin
from app.services.wb_storefront_brands import get_project_frontend_brand_id_strings
from app.utils.get_project_marketplace_token import get_wb_token_for_project
from app.wb.client import WBClient

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/v1/projects", tags=["wb-price-discrepancies"])


SortKey = Literal[
    "diff_rub_desc",
    "diff_rub_asc",
    "diff_percent_desc",
    "diff_percent_asc",
    "rrp_price_desc",
    "rrp_price_asc",
    "showcase_price_desc",
    "showcase_price_asc",
    "nm_id_desc",
    "nm_id_asc",
]

PriceApplyMode = Literal["base", "size"]


class WbPriceApplySizeInput(BaseModel):
    size_id: int = Field(..., gt=0)
    price: int = Field(..., gt=0)


class WbPriceApplyRequest(BaseModel):
    pricing_mode: PriceApplyMode
    price: Optional[int] = Field(None, gt=0)
    discount: Optional[int] = Field(None, ge=0, le=99)
    sizes: List[WbPriceApplySizeInput] = Field(default_factory=list)


class WbBulkPriceApplyRequest(BaseModel):
    nm_ids: List[int] = Field(..., min_length=1, max_length=1000)


def _parse_sort(sort: Optional[str]) -> SortKey:
    """Parse sort string into an internal sort key with sane default."""
    default: SortKey = "diff_percent_desc"
    if not sort:
        return default
    sort_normalized = sort.strip().lower()
    mapping: Dict[str, SortKey] = {
        "diff_rub_desc": "diff_rub_desc",
        "diff_rub_asc": "diff_rub_asc",
        "diff_percent_desc": "diff_percent_desc",
        "diff_percent_asc": "diff_percent_asc",
        "rrp_price_desc": "rrp_price_desc",
        "rrp_price_asc": "rrp_price_asc",
        "showcase_price_desc": "showcase_price_desc",
        "showcase_price_asc": "showcase_price_asc",
        "nm_id_desc": "nm_id_desc",
        "nm_id_asc": "nm_id_asc",
    }
    return mapping.get(sort_normalized, default)


def _sort_to_order_clause(sort: SortKey) -> str:
    """Map internal sort key to SQL ORDER BY clause (without 'ORDER BY')."""
    if sort == "diff_rub_desc":
        return "diff_rub DESC NULLS LAST, nm_id"
    if sort == "diff_rub_asc":
        return "diff_rub ASC NULLS LAST, nm_id"
    if sort == "diff_percent_desc":
        return "diff_percent DESC NULLS LAST, nm_id"
    if sort == "diff_percent_asc":
        return "diff_percent ASC NULLS LAST, nm_id"
    if sort == "rrp_price_desc":
        return "rrp_price DESC NULLS LAST, nm_id"
    if sort == "rrp_price_asc":
        return "rrp_price ASC NULLS LAST, nm_id"
    if sort == "showcase_price_desc":
        return "showcase_price DESC NULLS LAST, nm_id"
    if sort == "showcase_price_asc":
        return "showcase_price ASC NULLS LAST, nm_id"
    if sort == "nm_id_desc":
        return "nm_id DESC"
    if sort == "nm_id_asc":
        return "nm_id ASC"
    # Fallback – should not be hit if mapping is exhaustive
    return "diff_percent DESC NULLS LAST, nm_id"


@dataclass
class DiscrepancyFilters:
    q: Optional[str]
    category_ids: List[int]
    only_below_rrp: bool
    has_wb_stock: Literal["any", "true", "false"]
    has_enterprise_stock: Literal["any", "true", "false"]
    front_snapshot_at: Optional[datetime]
    sort: SortKey
    page: int
    page_size: int
    nm_ids: Optional[List[int]] = None


def _parse_category_ids(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    result: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            result.append(int(part))
        except ValueError:
            continue
    return result


def _build_discrepancies_sql(
    project_id: int, filters: DiscrepancyFilters
) -> Tuple[str, Dict[str, Any]]:
    """Return parametrized SQL and params for list/export queries.

    The query performs:
    - per-project scoping (project_id)
    - per-brand scoping for frontend snapshots via project_marketplaces/settings
    - latest snapshots for RRP/WB prices/frontend/stock
    - diff_rub/diff_percent/is_below_rrp computation in SQL
    - server-side filtering and sorting
    """
    order_clause = _sort_to_order_clause(filters.sort)

    where_clauses: List[str] = ["1=1"]
    params: Dict[str, Any] = {
        "project_id": project_id,
        "limit": filters.page_size,
        "offset": (filters.page - 1) * filters.page_size,
        "qpat": None,
        "category_ids": filters.category_ids or None,
        "front_snapshot_at": filters.front_snapshot_at,
        "brand_ids": get_project_frontend_brand_id_strings(project_id),
        "nm_ids": filters.nm_ids or None,
    }

    # Search by article / nm_id / title
    if filters.q:
        q = filters.q.strip()
        params["qpat"] = f"%{q}%"
        # Try to parse numeric nm_id for more efficient filter
        try:
            qnum = int(q)
        except ValueError:
            qnum = None
        params["qnum"] = qnum
        where_clauses.append(
            """
            (
                (:qpat IS NOT NULL AND (
                    p.vendor_code_norm ILIKE :qpat
                    OR p.vendor_code ILIKE :qpat
                    OR p.title ILIKE :qpat
                ))
                OR (:qnum IS NOT NULL AND p.nm_id = :qnum)
            )
            """
        )
    else:
        params["qnum"] = None

    # Category filter (subject_id from products)
    if filters.category_ids:
        where_clauses.append("p.subject_id = ANY(:category_ids)")

    if filters.nm_ids:
        where_clauses.append("p.nm_id = ANY(:nm_ids)")

    # Stock filters
    if filters.has_wb_stock == "true":
        where_clauses.append("COALESCE(stock_latest.wb_stock_qty, 0) > 0")
    elif filters.has_wb_stock == "false":
        where_clauses.append("COALESCE(stock_latest.wb_stock_qty, 0) <= 0")

    if filters.has_enterprise_stock == "true":
        where_clauses.append("COALESCE(rrp_latest.rrp_stock, 0) > 0")
    elif filters.has_enterprise_stock == "false":
        where_clauses.append("COALESCE(rrp_latest.rrp_stock, 0) <= 0")

    # Only below RRP – strictly handled on computed diff
    only_below_rrp_expr = ""
    if filters.only_below_rrp:
        only_below_rrp_expr = "AND computed.is_below_rrp = TRUE"

    where_sql = " AND ".join(where_clauses)

    sql = f"""
    WITH
    rrp_run AS (
        SELECT MAX(snapshot_at) AS run_at
        FROM rrp_snapshots
        WHERE project_id = :project_id
    ),
    stock_run AS (
        SELECT MAX(snapshot_at) AS run_at
        FROM stock_snapshots
        WHERE project_id = :project_id
    ),
    front_run AS (
        SELECT COALESCE(CAST(:front_snapshot_at AS timestamptz), MAX(f.snapshot_at)) AS run_at
        FROM frontend_catalog_price_snapshots f
        WHERE f.query_type = 'brand'
          AND f.query_value = ANY(:brand_ids)
    ),
    -- Latest RRP per vendor_code_norm
    rrp_latest AS (
        SELECT s.vendor_code_norm,
               MAX(s.rrp_price) AS rrp_price,
               MAX(s.rrp_stock) AS rrp_stock
        FROM rrp_snapshots s
        JOIN rrp_run r ON s.snapshot_at = r.run_at
        WHERE s.project_id = :project_id
        GROUP BY s.vendor_code_norm
    ),
    -- Latest WB admin price per nm_id
    wb_price_latest AS (
        SELECT DISTINCT ON (ps.nm_id)
            ps.nm_id::bigint AS nm_id,
            ps.wb_price        AS wb_admin_price,
            ps.wb_discount     AS wb_discount_percent,
            ps.created_at      AS wb_price_updated_at,
            ps.raw->>'source'  AS wb_price_source
        FROM price_snapshots ps
        WHERE ps.project_id = :project_id
        ORDER BY ps.nm_id, ps.created_at DESC
    ),
    -- Latest frontend showcase price per nm_id for this brand run
    front_latest AS (
        SELECT DISTINCT ON (f.nm_id)
            f.nm_id::bigint AS nm_id,
            f.price_product        AS showcase_price,
            f.discount_calc_percent AS spp_percent,
            f.snapshot_at          AS showcase_updated_at
        FROM frontend_catalog_price_snapshots f
        JOIN front_run r ON f.snapshot_at = r.run_at
        WHERE f.query_type = 'brand'
          AND f.query_value = ANY(:brand_ids)
        ORDER BY f.nm_id, f.snapshot_at DESC
    ),
    -- Latest WB stock per nm_id for this project
    stock_latest AS (
        SELECT ss.nm_id::bigint AS nm_id,
               SUM(COALESCE(ss.quantity, 0))::bigint AS wb_stock_qty
        FROM stock_snapshots ss
        JOIN stock_run r ON ss.snapshot_at = r.run_at
        WHERE ss.project_id = :project_id
        GROUP BY ss.nm_id
    ),
    base AS (
        SELECT
            p.nm_id::bigint AS nm_id,
            p.vendor_code_norm AS article,
            p.vendor_code AS article_raw,
            p.title AS title,
            p.subject_id AS category_id,
            p.subject_name AS category_name,
            p.pics AS pics_json,
            rrp_latest.rrp_price AS rrp_price,
            rrp_latest.rrp_stock AS enterprise_stock_qty,
            wb_price_latest.wb_admin_price,
            wb_price_latest.wb_discount_percent,
            front_latest.showcase_price,
            front_latest.spp_percent,
            front_latest.showcase_updated_at,
            stock_latest.wb_stock_qty,
            rrp_run.run_at     AS rrp_updated_at,
            stock_run.run_at   AS stock_updated_at,
            front_run.run_at   AS showcase_run_at,
            wb_price_latest.wb_price_updated_at,
            wb_price_latest.wb_price_source
        FROM v_wb_product_source p
        LEFT JOIN rrp_latest ON btrim(rrp_latest.vendor_code_norm) = btrim(p.vendor_code_norm)
        LEFT JOIN wb_price_latest ON wb_price_latest.nm_id = p.nm_id
        LEFT JOIN front_latest ON front_latest.nm_id = p.nm_id
        LEFT JOIN stock_latest ON stock_latest.nm_id = p.nm_id
        LEFT JOIN rrp_run ON TRUE
        LEFT JOIN stock_run ON TRUE
        LEFT JOIN front_run ON TRUE
        WHERE p.project_id = :project_id
          AND p.vendor_code_norm IS NOT NULL
          AND {where_sql}
    ),
    computed AS (
        SELECT
            b.*,
            CASE
                WHEN b.rrp_price IS NOT NULL
                 AND b.showcase_price IS NOT NULL
                THEN (b.rrp_price - b.showcase_price)
                ELSE NULL
            END AS diff_rub,
            CASE
                WHEN b.rrp_price IS NOT NULL
                 AND b.rrp_price > 0
                 AND b.showcase_price IS NOT NULL
                THEN ((b.rrp_price - b.showcase_price) / b.rrp_price) * 100.0
                ELSE NULL
            END AS diff_percent,
            CASE
                WHEN b.rrp_price IS NOT NULL
                 AND b.rrp_price > 0
                 AND b.wb_admin_price IS NOT NULL
                 AND b.wb_admin_price > 0
                 AND b.showcase_price IS NOT NULL
                 AND b.showcase_price > 0
                THEN ROUND(b.rrp_price * b.wb_admin_price / b.showcase_price)
                ELSE NULL
            END AS recommended_wb_admin_price,
            CASE
                WHEN b.rrp_price IS NOT NULL
                 AND b.rrp_price > 0
                 AND b.wb_admin_price IS NOT NULL
                 AND b.wb_admin_price > 0
                 AND b.showcase_price IS NOT NULL
                 AND b.showcase_price > 0
                THEN ROUND(b.rrp_price * b.wb_admin_price / b.showcase_price) - b.wb_admin_price
                ELSE NULL
            END AS delta_recommended,
            CASE
                WHEN b.rrp_price IS NOT NULL
                 AND b.rrp_price > 0
                 AND b.wb_admin_price IS NOT NULL
                 AND b.wb_admin_price > 0
                 AND b.showcase_price IS NOT NULL
                 AND b.showcase_price > 0
                THEN ROUND((ROUND(b.rrp_price * b.wb_admin_price / b.showcase_price)) * b.showcase_price / b.wb_admin_price)
                ELSE NULL
            END AS expected_showcase_price,
            CASE
                WHEN b.rrp_price IS NOT NULL
                 AND b.showcase_price IS NOT NULL
                 AND b.showcase_price < b.rrp_price
                THEN TRUE
                ELSE FALSE
            END AS is_below_rrp
        FROM base b
    ),
    filtered AS (
        SELECT *
        FROM computed
        WHERE 1=1
        {only_below_rrp_expr}
    ),
    counted AS (
        SELECT
            *,
            COUNT(*) OVER() AS total_count
        FROM filtered
    )
    SELECT
        nm_id,
        article,
        article_raw,
        title,
        category_id,
        category_name,
        pics_json,
        wb_admin_price,
        rrp_price,
        showcase_price,
        wb_discount_percent,
        spp_percent,
        wb_stock_qty,
        enterprise_stock_qty,
        diff_rub,
        diff_percent,
        recommended_wb_admin_price,
        delta_recommended,
        expected_showcase_price,
        is_below_rrp,
        rrp_updated_at,
        stock_updated_at,
        showcase_run_at,
        showcase_updated_at,
        wb_price_updated_at,
        wb_price_source,
        total_count
    FROM counted
    ORDER BY {order_clause}
    LIMIT :limit OFFSET :offset
    """

    return sql, params


def _row_to_item(row: Dict[str, Any]) -> Dict[str, Any]:
    """Transform a raw DB row into the API response item structure."""
    # Photos from products.pics (JSONB) -> list of URLs (first one is thumbnail)
    photos: List[str] = []
    raw_pics = row.get("pics_json")
    if raw_pics:
        try:
            # raw_pics may already be a Python list/dict if driver decodes JSONB
            if isinstance(raw_pics, str):
                import json

                pics_val = json.loads(raw_pics)
            else:
                pics_val = raw_pics
            if isinstance(pics_val, list):
                for pic in pics_val:
                    if isinstance(pic, dict):
                        url = pic.get("url") or pic.get("big") or pic.get("c128")
                        if url:
                            photos.append(str(url))
                    elif isinstance(pic, str):
                        photos.append(pic)
        except Exception:
            # Best-effort: if parsing fails, just skip photos
            photos = []

    prices = {
        "wb_admin_price": float(row["wb_admin_price"]) if row.get("wb_admin_price") is not None else None,
        "rrp_price": float(row["rrp_price"]) if row.get("rrp_price") is not None else None,
        "showcase_price": float(row["showcase_price"]) if row.get("showcase_price") is not None else None,
    }
    discounts = {
        "wb_discount_percent": float(row["wb_discount_percent"])
        if row.get("wb_discount_percent") is not None
        else None,
        "spp_percent": float(row["spp_percent"]) if row.get("spp_percent") is not None else None,
    }
    stocks = {
        "wb_stock_qty": int(row["wb_stock_qty"]) if row.get("wb_stock_qty") is not None else 0,
        "enterprise_stock_qty": int(row["enterprise_stock_qty"])
        if row.get("enterprise_stock_qty") is not None
        else 0,
    }
    computed = {
        "is_below_rrp": bool(row.get("is_below_rrp", False)),
        "diff_rub": float(row["diff_rub"]) if row.get("diff_rub") is not None else None,
        "diff_percent": float(row["diff_percent"]) if row.get("diff_percent") is not None else None,
        "recommended_wb_admin_price": float(row["recommended_wb_admin_price"])
        if row.get("recommended_wb_admin_price") is not None
        else None,
        "delta_recommended": float(row["delta_recommended"])
        if row.get("delta_recommended") is not None
        else None,
        "expected_showcase_price": float(row["expected_showcase_price"])
        if row.get("expected_showcase_price") is not None
        else None,
    }
    wb_price_updated_at = row.get("wb_price_updated_at")
    showcase_updated_at = row.get("showcase_updated_at")
    if isinstance(wb_price_updated_at, datetime) and wb_price_updated_at.tzinfo is None:
        wb_price_updated_at = wb_price_updated_at.replace(tzinfo=timezone.utc)
    if isinstance(showcase_updated_at, datetime) and showcase_updated_at.tzinfo is None:
        showcase_updated_at = showcase_updated_at.replace(tzinfo=timezone.utc)
    showcase_price_stale = (
        row.get("wb_price_source") == "price_discrepancy_manual_apply"
        and isinstance(wb_price_updated_at, datetime)
        and isinstance(showcase_updated_at, datetime)
        and wb_price_updated_at > showcase_updated_at
    )
    staleness = {
        "showcase_price_stale": showcase_price_stale,
        "reason": "awaiting_showcase_refresh" if showcase_price_stale else None,
        "wb_price_updated_at": wb_price_updated_at.isoformat() if isinstance(wb_price_updated_at, datetime) else None,
        "showcase_updated_at": showcase_updated_at.isoformat() if isinstance(showcase_updated_at, datetime) else None,
    }

    category = None
    if row.get("category_id") is not None or row.get("category_name") is not None:
        category = {
            "id": row.get("category_id"),
            "name": row.get("category_name"),
        }

    return {
        "article": row.get("article"),
        "nm_id": int(row["nm_id"]) if row.get("nm_id") is not None else None,
        "title": row.get("title"),
        "category": category,
        "photos": photos,
        "prices": prices,
        "discounts": discounts,
        "stocks": stocks,
        "computed": computed,
        "staleness": staleness,
    }


def _get_price_discrepancy_item(project_id: int, nm_id: int) -> Optional[Dict[str, Any]]:
    return _get_price_discrepancy_items(project_id, [nm_id]).get(nm_id)


def _get_price_discrepancy_items(project_id: int, nm_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    normalized_nm_ids: set[int] = set()
    for nm_id in nm_ids:
        try:
            normalized_nm_id = int(nm_id)
        except (TypeError, ValueError):
            continue
        if normalized_nm_id > 0:
            normalized_nm_ids.add(normalized_nm_id)
    unique_nm_ids = sorted(normalized_nm_ids)
    if not unique_nm_ids:
        return {}

    filters = DiscrepancyFilters(
        q=None,
        category_ids=[],
        only_below_rrp=False,
        has_wb_stock="any",
        has_enterprise_stock="any",
        front_snapshot_at=None,
        sort="nm_id_asc",
        page=1,
        page_size=len(unique_nm_ids),
        nm_ids=unique_nm_ids,
    )
    sql, params = _build_discrepancies_sql(project_id, filters)
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()

    items_by_nm_id: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        row_dict = dict(row)
        row_nm_id = int(row_dict.get("nm_id") or 0)
        if row_nm_id:
            items_by_nm_id[row_nm_id] = _row_to_item(row_dict)
    return items_by_nm_id


def _parse_price_raw(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _get_latest_price_raw(project_id: int, nm_id: int) -> Dict[str, Any]:
    return _get_latest_price_raws(project_id, [nm_id]).get(nm_id, {})


def _get_latest_price_raws(project_id: int, nm_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    normalized_nm_ids: set[int] = set()
    for nm_id in nm_ids:
        try:
            normalized_nm_id = int(nm_id)
        except (TypeError, ValueError):
            continue
        if normalized_nm_id > 0:
            normalized_nm_ids.add(normalized_nm_id)
    unique_nm_ids = sorted(normalized_nm_ids)
    if not unique_nm_ids:
        return {}

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT DISTINCT ON (nm_id)
                    nm_id::bigint AS nm_id,
                    raw
                FROM price_snapshots
                WHERE project_id = :project_id
                  AND nm_id = ANY(:nm_ids)
                ORDER BY nm_id, created_at DESC
                """
            ),
            {"project_id": project_id, "nm_ids": unique_nm_ids},
        ).mappings().all()
    return {int(row["nm_id"]): _parse_price_raw(row.get("raw")) for row in rows}


def _coerce_int_price(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        rounded = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return rounded if rounded > 0 else None


def _build_price_apply_preview(project_id: int, nm_id: int) -> Dict[str, Any]:
    item = _get_price_discrepancy_item(project_id, nm_id)
    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден в отчете расхождений цен")

    recommended_price = _coerce_int_price(item["computed"].get("recommended_wb_admin_price"))
    if recommended_price is None:
        raise HTTPException(status_code=400, detail="Для товара нет рассчитанной рекомендованной цены")

    raw_price = _get_latest_price_raw(project_id, nm_id)
    editable_size_price = bool(raw_price.get("editableSizePrice"))
    raw_sizes = raw_price.get("sizes") if isinstance(raw_price.get("sizes"), list) else []
    mode: PriceApplyMode = "size" if editable_size_price else "base"

    sizes: List[Dict[str, Any]] = []
    for raw_size in raw_sizes:
        if not isinstance(raw_size, dict):
            continue
        size_id = raw_size.get("sizeID")
        try:
            size_id_int = int(size_id)
        except (TypeError, ValueError):
            continue
        sizes.append(
            {
                "size_id": size_id_int,
                "tech_size_name": raw_size.get("techSizeName"),
                "current_price": _coerce_int_price(raw_size.get("price")),
                "discounted_price": raw_size.get("discountedPrice"),
                "target_price": recommended_price,
            }
        )

    return {
        "item": item,
        "pricing_mode": mode,
        "editable_size_price": editable_size_price,
        "recommended_price": recommended_price,
        "default_discount": _coerce_int_price(item["discounts"].get("wb_discount_percent")) or 0,
        "sizes": sizes,
    }


def _extract_upload_id(payload: Dict[str, Any]) -> Optional[int]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None
    upload_id = data.get("id") or data.get("uploadID")
    try:
        return int(upload_id)
    except (TypeError, ValueError):
        return None


def _price_snapshots_has_raw_column() -> bool:
    with engine.connect() as conn:
        return (
            conn.execute(
                text(
                    """
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'price_snapshots'
                      AND column_name = 'raw'
                    LIMIT 1
                    """
                )
            ).scalar()
            is not None
        )


def _insert_manual_price_snapshot(
    *,
    project_id: int,
    nm_id: int,
    wb_price: int,
    wb_discount: int,
    response_payload: Dict[str, Any],
    pricing_mode: PriceApplyMode,
) -> None:
    customer_price = round(float(wb_price) * (1 - float(wb_discount) / 100), 2)
    created_at = datetime.now(timezone.utc)
    raw_payload = {
        "source": "price_discrepancy_manual_apply",
        "pricing_mode": pricing_mode,
        "nmID": nm_id,
        "price": wb_price,
        "discount": wb_discount,
        "wb_response": response_payload,
    }
    params = {
        "project_id": project_id,
        "nm_id": nm_id,
        "wb_price": wb_price,
        "wb_discount": wb_discount,
        "spp": 0,
        "customer_price": customer_price,
        "rrc": wb_price,
        "created_at": created_at,
        "raw": json.dumps(raw_payload, ensure_ascii=False),
    }
    if _price_snapshots_has_raw_column():
        sql = text(
            """
            INSERT INTO price_snapshots
                (marketplace_product_id, nm_id, wb_price, wb_discount, spp, customer_price, rrc, raw, project_id, created_at)
            VALUES
                (:marketplace_product_id, :nm_id, :wb_price, :wb_discount, :spp, :customer_price, :rrc, CAST(:raw AS jsonb), :project_id, :created_at)
            """
        )
    else:
        sql = text(
            """
            INSERT INTO price_snapshots
                (marketplace_product_id, nm_id, wb_price, wb_discount, spp, customer_price, rrc, project_id, created_at)
            VALUES
                (:marketplace_product_id, :nm_id, :wb_price, :wb_discount, :spp, :customer_price, :rrc, :project_id, :created_at)
            """
        )
    with engine.begin() as conn:
        params["marketplace_product_id"] = resolve_marketplace_product_id(
            project_id=project_id,
            marketplace_code="wildberries",
            marketplace_item_id=nm_id,
            connection=conn,
        )
        conn.execute(sql, params)


def _get_latest_front_snapshot_at(project_id: int) -> Optional[datetime]:
    """Return the latest WB frontend (showcase) snapshot_at for project storefront brands."""
    brand_ids = get_project_frontend_brand_id_strings(project_id)
    if not brand_ids:
        return None
    with engine.connect() as conn:
        front_max = conn.execute(
            text(
                """
                SELECT MAX(f.snapshot_at)
                FROM frontend_catalog_price_snapshots f
                WHERE f.query_type = 'brand'
                  AND f.query_value = ANY(:brand_ids)
                """
            ),
            {"brand_ids": brand_ids},
        ).scalar()
    if isinstance(front_max, datetime):
        if front_max.tzinfo is None:
            return front_max.replace(tzinfo=timezone.utc)
        return front_max
    return None


def _get_updated_at(project_id: int, front_snapshot_at: Optional[datetime] = None) -> str:
    """Return ISO8601 updated_at for meta based on latest snapshot timestamps.

    If no data is available at all, fallback to `datetime.now(timezone.utc)`.
    """
    # We intentionally keep this as a separate lightweight query instead of
    # complicating the main aggregation SQL.
    if front_snapshot_at is not None and isinstance(front_snapshot_at, datetime):
        if front_snapshot_at.tzinfo is None:
            front_snapshot_at = front_snapshot_at.replace(tzinfo=timezone.utc)
    with engine.connect() as conn:
        rrp_max = conn.execute(
            text("SELECT MAX(snapshot_at) FROM rrp_snapshots WHERE project_id = :project_id"),
            {"project_id": project_id},
        ).scalar()
        stock_max = conn.execute(
            text("SELECT MAX(snapshot_at) FROM stock_snapshots WHERE project_id = :project_id"),
            {"project_id": project_id},
        ).scalar()
        price_max = conn.execute(
            text("SELECT MAX(created_at) FROM price_snapshots WHERE project_id = :project_id"),
            {"project_id": project_id},
        ).scalar()
        if front_snapshot_at is None:
            brand_ids = get_project_frontend_brand_id_strings(project_id)
            front_max = conn.execute(
                text(
                    """
                    SELECT MAX(f.snapshot_at)
                    FROM frontend_catalog_price_snapshots f
                    WHERE f.query_type = 'brand'
                      AND f.query_value = ANY(:brand_ids)
                    """
                ),
                {"brand_ids": brand_ids},
            ).scalar()
        else:
            front_max = front_snapshot_at

    candidates = [
        ts
        for ts in [rrp_max, stock_max, price_max, front_max]
        if ts is not None
    ]
    if not candidates:
        return datetime.now(timezone.utc).isoformat()
    latest = max(candidates)
    # SQLAlchemy usually returns datetime with tzinfo; guard just in case.
    if isinstance(latest, datetime):
        if latest.tzinfo is None:
            latest = latest.replace(tzinfo=timezone.utc)
        return latest.isoformat()
    return datetime.now(timezone.utc).isoformat()


@router.post("/{project_id}/wildberries/price-discrepancies/price-apply/bulk")
async def apply_wb_recommended_prices_bulk(
    body: WbBulkPriceApplyRequest,
    project_id: int = Path(..., description="Project ID"),
    _current_user: dict = Depends(get_current_active_user),
    _membership: dict = Depends(require_project_admin),
):
    """Create one WB price upload task for selected report rows."""
    seen: set[int] = set()
    nm_ids: List[int] = []
    for raw_nm_id in body.nm_ids:
        try:
            nm_id = int(raw_nm_id)
        except (TypeError, ValueError):
            continue
        if nm_id <= 0 or nm_id in seen:
            continue
        seen.add(nm_id)
        nm_ids.append(nm_id)

    if not nm_ids:
        raise HTTPException(status_code=400, detail="Не выбраны товары для установки цен")

    ready: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    items_by_nm_id = _get_price_discrepancy_items(project_id, nm_ids)
    raw_prices_by_nm_id = _get_latest_price_raws(project_id, nm_ids)

    for nm_id in nm_ids:
        item = items_by_nm_id.get(nm_id)
        if not item:
            skipped.append({"nm_id": nm_id, "reason": "not_found", "message": "Товар не найден в отчете"})
            continue

        recommended_price = _coerce_int_price(item["computed"].get("recommended_wb_admin_price"))
        if recommended_price is None:
            skipped.append(
                {
                    "nm_id": nm_id,
                    "article": item.get("article"),
                    "reason": "no_recommended_price",
                    "message": "Нет рекомендованной цены",
                }
            )
            continue

        if (item.get("staleness") or {}).get("showcase_price_stale"):
            skipped.append(
                {
                    "nm_id": nm_id,
                    "article": item.get("article"),
                    "reason": "awaiting_showcase_refresh",
                    "message": "Ждем обновления витрины",
                }
            )
            continue

        raw_price = raw_prices_by_nm_id.get(nm_id, {})
        if bool(raw_price.get("editableSizePrice")):
            skipped.append(
                {
                    "nm_id": nm_id,
                    "article": item.get("article"),
                    "reason": "size_price",
                    "message": "Размерная цена, нужен отдельный режим",
                }
            )
            continue

        discount = _coerce_int_price(item["discounts"].get("wb_discount_percent")) or 0
        ready.append(
            {
                "nm_id": nm_id,
                "article": item.get("article"),
                "title": item.get("title"),
                "current_price": item["prices"].get("wb_admin_price"),
                "recommended_price": recommended_price,
                "discount": discount,
            }
        )

    if not ready:
        return {
            "status": "skipped",
            "upload_id": None,
            "already_exists": False,
            "accepted_count": 0,
            "skipped_count": len(skipped),
            "ready": [],
            "skipped": skipped,
            "wb_response": None,
        }

    token = get_wb_token_for_project(project_id)
    if not token:
        raise HTTPException(status_code=400, detail="Для проекта не настроен токен Wildberries")

    wb_payload = [
        {"nmID": item["nm_id"], "price": item["recommended_price"], "discount": item["discount"]}
        for item in ready
    ]
    client = WBClient(token)
    response_payload = await client.upload_price_task(wb_payload)
    upload_id = _extract_upload_id(response_payload)

    if response_payload.get("error"):
        status_code = int(response_payload.get("statusCode") or 502)
        retry_after = (response_payload.get("rateLimit") or {}).get("retry_after")
        if status_code == 429:
            retry_text = f" Повторите через {retry_after} сек." if retry_after else ""
            raise HTTPException(
                status_code=429,
                detail=f"Wildberries ограничил частоту запросов к API цен.{retry_text}",
            )
        raise HTTPException(
            status_code=502,
            detail=response_payload.get("errorText") or "Wildberries не принял задачу массового обновления цен",
        )

    for item in ready:
        _insert_manual_price_snapshot(
            project_id=project_id,
            nm_id=int(item["nm_id"]),
            wb_price=int(item["recommended_price"]),
            wb_discount=int(item["discount"]),
            response_payload=response_payload,
            pricing_mode="base",
        )

    return {
        "status": "accepted",
        "upload_id": upload_id,
        "already_exists": bool((response_payload.get("data") or {}).get("alreadyExists"))
        if isinstance(response_payload.get("data"), dict)
        else False,
        "accepted_count": len(ready),
        "skipped_count": len(skipped),
        "ready": ready,
        "skipped": skipped,
        "wb_status_code": client.last_response_status,
        "wb_response": response_payload,
    }


@router.get("/{project_id}/wildberries/price-discrepancies/{nm_id}/price-apply-preview")
async def get_wb_price_apply_preview(
    project_id: int = Path(..., description="Project ID"),
    nm_id: int = Path(..., description="WB nmID"),
    _current_user: dict = Depends(get_current_active_user),
    _membership: dict = Depends(require_project_admin),
):
    """Return editable price-apply defaults for a report row."""
    return _build_price_apply_preview(project_id, nm_id)


@router.post("/{project_id}/wildberries/price-discrepancies/{nm_id}/price-apply")
async def apply_wb_recommended_price(
    body: WbPriceApplyRequest,
    project_id: int = Path(..., description="Project ID"),
    nm_id: int = Path(..., description="WB nmID"),
    _current_user: dict = Depends(get_current_active_user),
    _membership: dict = Depends(require_project_admin),
):
    """Create a WB price upload task from the report recommendation modal."""
    preview = _build_price_apply_preview(project_id, nm_id)
    expected_mode = preview["pricing_mode"]
    if body.pricing_mode != expected_mode:
        raise HTTPException(
            status_code=400,
            detail=f"Для товара доступен режим {expected_mode}, а не {body.pricing_mode}",
        )

    token = get_wb_token_for_project(project_id)
    if not token:
        raise HTTPException(status_code=400, detail="Для проекта не настроен токен Wildberries")

    client = WBClient(token)
    applied_price: int
    applied_discount: int
    if body.pricing_mode == "base":
        if body.price is None:
            raise HTTPException(status_code=400, detail="Укажите цену для установки")
        discount = body.discount
        if discount is None:
            discount = int(preview.get("default_discount") or 0)
        applied_price = int(body.price)
        applied_discount = int(discount)
        wb_payload = [{"nmID": nm_id, "price": applied_price, "discount": applied_discount}]
        response_payload = await client.upload_price_task(wb_payload)
    else:
        known_sizes = {int(size["size_id"]) for size in preview.get("sizes", [])}
        if not body.sizes:
            raise HTTPException(status_code=400, detail="Укажите цены для размеров")
        unknown_sizes = [item.size_id for item in body.sizes if item.size_id not in known_sizes]
        if unknown_sizes:
            raise HTTPException(
                status_code=400,
                detail=f"Размеры не найдены у товара: {', '.join(str(size_id) for size_id in unknown_sizes)}",
            )
        wb_payload = [
            {"nmID": nm_id, "sizeID": int(item.size_id), "price": int(item.price)}
            for item in body.sizes
        ]
        applied_price = min(int(item.price) for item in body.sizes)
        applied_discount = int(preview.get("default_discount") or 0)
        response_payload = await client.upload_size_price_task(wb_payload)

    upload_id = _extract_upload_id(response_payload)
    if response_payload.get("error"):
        status_code = int(response_payload.get("statusCode") or 502)
        retry_after = (response_payload.get("rateLimit") or {}).get("retry_after")
        if status_code == 429:
            retry_text = f" Повторите через {retry_after} сек." if retry_after else ""
            raise HTTPException(
                status_code=429,
                detail=f"Wildberries ограничил частоту запросов к API цен.{retry_text}",
            )
        raise HTTPException(
            status_code=502,
            detail=response_payload.get("errorText") or "Wildberries не принял задачу обновления цены",
        )

    _insert_manual_price_snapshot(
        project_id=project_id,
        nm_id=nm_id,
        wb_price=applied_price,
        wb_discount=applied_discount,
        response_payload=response_payload,
        pricing_mode=body.pricing_mode,
    )

    return {
        "status": "accepted",
        "pricing_mode": body.pricing_mode,
        "upload_id": upload_id,
        "already_exists": bool((response_payload.get("data") or {}).get("alreadyExists"))
        if isinstance(response_payload.get("data"), dict)
        else False,
        "wb_status_code": client.last_response_status,
        "wb_response": response_payload,
    }


@router.get("/{project_id}/wildberries/price-discrepancies/price-apply-status")
async def get_wb_price_apply_status(
    project_id: int = Path(..., description="Project ID"),
    upload_id: int = Query(..., gt=0, description="WB price upload ID"),
    _current_user: dict = Depends(get_current_active_user),
    _membership: dict = Depends(require_project_admin),
):
    """Return a compact status for a WB price upload task."""
    token = get_wb_token_for_project(project_id)
    if not token:
        raise HTTPException(status_code=400, detail="Для проекта не настроен токен Wildberries")

    client = WBClient(token)
    buffer_state = await client.get_price_upload_state(upload_id, processed=False)
    if not buffer_state.get("error") and buffer_state.get("data"):
        buffer_goods = await client.get_price_upload_goods(upload_id, processed=False, limit=1000)
        return {
            "status": "waiting",
            "upload_id": upload_id,
            "state": buffer_state.get("data"),
            "goods": (buffer_goods.get("data") or {}).get("bufferGoods")
            if isinstance(buffer_goods.get("data"), dict)
            else [],
            "wb_response": buffer_state,
        }

    history_state = await client.get_price_upload_state(upload_id, processed=True)
    if history_state.get("error"):
        raise HTTPException(
            status_code=502,
            detail=history_state.get("errorText") or "Не удалось получить статус задачи Wildberries",
        )

    history_goods = await client.get_price_upload_goods(upload_id, processed=True, limit=1000)
    goods = []
    if isinstance(history_goods.get("data"), dict):
        goods = history_goods["data"].get("historyGoods") or []
    errored_goods = [
        item for item in goods if isinstance(item, dict) and item.get("errorText")
    ]
    state = history_state.get("data") if isinstance(history_state.get("data"), dict) else {}
    overall = int(state.get("overAllGoodsNumber") or len(goods) or 0)
    success = int(state.get("successGoodsNumber") or 0)
    compact_status = "error" if errored_goods else "applied"
    if compact_status == "applied" and overall and success < overall:
        compact_status = "waiting"

    return {
        "status": compact_status,
        "upload_id": upload_id,
        "state": state,
        "goods": goods,
        "errors": errored_goods,
        "wb_response": history_state,
    }


@router.get("/{project_id}/wildberries/price-discrepancies")
async def get_wb_price_discrepancies(
    project_id: int = Path(..., description="Project ID"),
    q: Optional[str] = Query(None, description="Search by article/nmID/title"),
    category_ids: Optional[str] = Query(
        None,
        description='Comma-separated WB category/subject IDs, e.g. "1,2,3"',
        example="12,34,56",
    ),
    front_snapshot_at: Optional[datetime] = Query(
        None,
        description=(
            "Use a specific WB frontend showcase snapshot_at (UTC recommended). "
            "If omitted, the latest available snapshot is used."
        ),
    ),
    only_below_rrp: bool = Query(
        True,
        description="Filter: only items where showcase_price < rrp_price",
    ),
    has_wb_stock: Literal["any", "true", "false"] = Query(
        "any", description="Filter by WB stock quantity"
    ),
    has_enterprise_stock: Literal["any", "true", "false"] = Query(
        "any", description="Filter by enterprise (1C/XML) stock quantity"
    ),
    sort: Optional[str] = Query(
        "diff_percent_desc",
        description="Sort key, e.g. diff_percent_desc, diff_rub_desc, nm_id_asc",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    _auth: dict = Depends(allow_client_portal_read),
):
    """Return price discrepancies between RRP and WB showcase price for a project.

    Always returns HTTP 200 with items/meta (never 404), even if no data is available.
    """
    start_time = datetime.now(timezone.utc)
    logger.info(
        f"get_wb_price_discrepancies: starting for project_id={project_id} "
        f"page={page} page_size={page_size} only_below_rrp={only_below_rrp} "
        f"front_snapshot_at={front_snapshot_at.isoformat() if front_snapshot_at else None}"
    )
    
    if front_snapshot_at is not None and isinstance(front_snapshot_at, datetime) and front_snapshot_at.tzinfo is None:
        # Treat naive datetimes as UTC to avoid environment-dependent casts in Postgres.
        front_snapshot_at = front_snapshot_at.replace(tzinfo=timezone.utc)

    filters = DiscrepancyFilters(
        q=q,
        category_ids=_parse_category_ids(category_ids),
        only_below_rrp=only_below_rrp,
        has_wb_stock=has_wb_stock,
        has_enterprise_stock=has_enterprise_stock,
        front_snapshot_at=front_snapshot_at,
        sort=_parse_sort(sort),
        page=page,
        page_size=page_size,
    )

    sql, params = _build_discrepancies_sql(project_id, filters)

    items: List[Dict[str, Any]] = []
    total_count = 0
    
    # #region agent log
    import json
    try:
        with open(r'd:\Work\EcomCore\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "H1",
                "location": "api_wb_price_discrepancies.py:578",
                "message": "get_wb_price_discrepancies: before SQL execution",
                "data": {
                    "project_id": project_id,
                    "filters_only_below_rrp": filters.only_below_rrp,
                },
                "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion
    
    with engine.connect() as conn:
        # #region agent log
        # Diagnostic: Check data availability at each step
        try:
            # Check rrp_run (critical for JOIN)
            rrp_run_check = conn.execute(
                text("SELECT MAX(snapshot_at) AS run_at FROM rrp_snapshots WHERE project_id = :project_id"),
                {"project_id": project_id},
            ).scalar()
            
            # Check rrp_snapshots count
            rrp_count = conn.execute(
                text("SELECT COUNT(*) FROM rrp_snapshots WHERE project_id = :project_id"),
                {"project_id": project_id},
            ).scalar() or 0
            
            # Check products count
            products_count = conn.execute(
                text("SELECT COUNT(*) FROM v_wb_product_source WHERE project_id = :project_id AND vendor_code_norm IS NOT NULL"),
                {"project_id": project_id},
            ).scalar() or 0
            
            frontend_count = 0
            if params.get("brand_ids"):
                frontend_count = conn.execute(
                    text("""
                        SELECT COUNT(*) FROM frontend_catalog_price_snapshots
                        WHERE query_type = 'brand' AND query_value = ANY(:brand_ids)
                    """),
                    {"brand_ids": params["brand_ids"]},
                ).scalar() or 0
            
            # Check Internal Data availability
            internal_data_count = conn.execute(
                text("""
                    SELECT COUNT(*) FROM internal_product_prices ipp
                    JOIN internal_data_snapshots ids ON ipp.snapshot_id = ids.id
                    WHERE ids.project_id = :project_id AND ipp.rrp IS NOT NULL
                """),
                {"project_id": project_id},
            ).scalar() or 0
            
            # Check mapping: products with vendor_code_norm that match internal_sku
            mapping_count = conn.execute(
                text("""
                    SELECT COUNT(DISTINCT p.vendor_code_norm) FROM v_wb_product_source p
                    JOIN internal_products ip ON ip.internal_sku = p.vendor_code_norm
                    JOIN internal_product_prices ipp ON ipp.internal_product_id = ip.id
                    JOIN internal_data_snapshots ids ON ipp.snapshot_id = ids.id
                    WHERE ids.project_id = :project_id AND p.project_id = :project_id
                      AND ipp.rrp IS NOT NULL
                """),
                {"project_id": project_id},
            ).scalar() or 0
            
            with open(r'd:\Work\EcomCore\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H1",
                    "location": "api_wb_price_discrepancies.py:620",
                    "message": "get_wb_price_discrepancies: data availability check",
                    "data": {
                        "project_id": project_id,
                        "rrp_snapshots_count": rrp_count,
                        "rrp_run_max_snapshot_at": rrp_run_check.isoformat() if rrp_run_check else None,
                        "products_with_vendor_code_norm": products_count,
                        "frontend_catalog_price_snapshots_count": frontend_count,
                        "internal_data_rrp_count": internal_data_count,
                        "products_mapped_to_internal_data": mapping_count,
                    },
                    "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            try:
                with open(r'd:\Work\EcomCore\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "H1",
                        "location": "api_wb_price_discrepancies.py:650",
                        "message": "get_wb_price_discrepancies: data availability check ERROR",
                        "data": {"error": str(e)},
                        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                    }, ensure_ascii=False) + "\n")
            except Exception:
                pass
        # #endregion
        
        result = conn.execute(text(sql), params).mappings().all()
        
        # #region agent log
        try:
            with open(r'd:\Work\EcomCore\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H2",
                    "location": "api_wb_price_discrepancies.py:680",
                    "message": "get_wb_price_discrepancies: SQL result rows",
                    "data": {
                        "project_id": project_id,
                        "rows_returned": len(result),
                    },
                    "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass
        # #endregion
        
        for row in result:
            row_dict = dict(row)
            total_count = int(row_dict.get("total_count", total_count or 0))
            items.append(_row_to_item(row_dict))
        
        # #region agent log
        # If no data, check intermediate CTE results
        if total_count == 0:
            try:
                # Test rrp_latest CTE directly
                rrp_latest_test = conn.execute(
                    text("""
                        WITH
                        rrp_run AS (
                            SELECT MAX(snapshot_at) AS run_at FROM rrp_snapshots WHERE project_id = :project_id
                        ),
                        rrp_latest AS (
                            SELECT s.vendor_code_norm, MAX(s.rrp_price) AS rrp_price
                            FROM rrp_snapshots s
                            JOIN rrp_run r ON s.snapshot_at = r.run_at
                            WHERE s.project_id = :project_id
                            GROUP BY s.vendor_code_norm
                        )
                        SELECT COUNT(*) AS count FROM rrp_latest
                    """),
                    {"project_id": project_id},
                ).scalar() or 0
                
                # Test base CTE (products with joins)
                base_test = conn.execute(
                    text("""
                        WITH
                        rrp_run AS (
                            SELECT MAX(snapshot_at) AS run_at FROM rrp_snapshots WHERE project_id = :project_id
                        ),
                        front_run AS (
                            SELECT MAX(f.snapshot_at) AS run_at
                            FROM frontend_catalog_price_snapshots f
                            WHERE f.query_type = 'brand' AND f.query_value = ANY(:brand_ids)
                        ),
                        rrp_latest AS (
                            SELECT s.vendor_code_norm, MAX(s.rrp_price) AS rrp_price
                            FROM rrp_snapshots s
                            JOIN rrp_run r ON s.snapshot_at = r.run_at
                            WHERE s.project_id = :project_id
                            GROUP BY s.vendor_code_norm
                        ),
                        front_latest AS (
                            SELECT DISTINCT ON (f.nm_id) f.nm_id::bigint AS nm_id, f.price_product AS showcase_price
                            FROM frontend_catalog_price_snapshots f
                            JOIN front_run r ON f.snapshot_at = r.run_at
                            WHERE f.query_type = 'brand' AND f.query_value = ANY(:brand_ids)
                            ORDER BY f.nm_id, f.snapshot_at DESC
                        )
                        SELECT 
                            COUNT(*) AS products_total,
                            COUNT(rrp_latest.vendor_code_norm) AS products_with_rrp,
                            COUNT(front_latest.nm_id) AS products_with_frontend,
                            COUNT(CASE WHEN rrp_latest.vendor_code_norm IS NOT NULL AND front_latest.nm_id IS NOT NULL THEN 1 END) AS products_with_both
                        FROM v_wb_product_source p
                        LEFT JOIN rrp_latest ON btrim(rrp_latest.vendor_code_norm) = btrim(p.vendor_code_norm)
                        LEFT JOIN front_latest ON front_latest.nm_id = p.nm_id
                        WHERE p.project_id = :project_id AND p.vendor_code_norm IS NOT NULL
                    """),
                    {"project_id": project_id, "brand_ids": params["brand_ids"]},
                ).mappings().first()
                
                with open(r'd:\Work\EcomCore\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "H3",
                        "location": "api_wb_price_discrepancies.py:720",
                        "message": "get_wb_price_discrepancies: CTE analysis (empty result)",
                        "data": {
                            "project_id": project_id,
                            "rrp_latest_count": rrp_latest_test,
                            "products_total": base_test.get("products_total") if base_test else 0,
                            "products_with_rrp": base_test.get("products_with_rrp") if base_test else 0,
                            "products_with_frontend": base_test.get("products_with_frontend") if base_test else 0,
                            "products_with_both": base_test.get("products_with_both") if base_test else 0,
                            "only_below_rrp_filter": filters.only_below_rrp,
                        },
                        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                    }, ensure_ascii=False) + "\n")
            except Exception as e:
                try:
                    with open(r'd:\Work\EcomCore\.cursor\debug.log', 'a', encoding='utf-8') as f:
                        f.write(json.dumps({
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "H3",
                            "location": "api_wb_price_discrepancies.py:750",
                            "message": "get_wb_price_discrepancies: CTE analysis ERROR",
                            "data": {"error": str(e)},
                            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                        }, ensure_ascii=False) + "\n")
                except Exception:
                    pass
        # #endregion
    
    end_time = datetime.now(timezone.utc)
    elapsed_ms = (end_time - start_time).total_seconds() * 1000
    
    logger.info(
        f"get_wb_price_discrepancies: completed for project_id={project_id} "
        f"total_count={total_count} items_returned={len(items)} "
        f"elapsed={elapsed_ms:.2f}ms"
    )
    
    # If no data, check what's missing and add diagnostic info to response
    diagnostic_info = None
    if total_count == 0:
        logger.warning(
            f"get_wb_price_discrepancies: no data found for project_id={project_id}. "
            "Consider running diagnose_data_availability task to check prerequisites."
        )
        
        # Collect diagnostic information about missing data
        try:
            with engine.connect() as conn:
                # Check WB marketplace row and storefront brand scope.
                marketplace_check = conn.execute(
                    text("""
                        SELECT pm.is_enabled
                        FROM project_marketplaces pm
                        JOIN marketplaces m ON m.id = pm.marketplace_id
                        WHERE pm.project_id = :project_id AND m.code = 'wildberries'
                        LIMIT 1
                    """),
                    {"project_id": project_id},
                ).mappings().first()
                brand_ids = params.get("brand_ids") or []
                
                # Check table counts
                rrp_count = conn.execute(
                    text("SELECT COUNT(*) FROM rrp_snapshots WHERE project_id = :project_id"),
                    {"project_id": project_id},
                ).scalar() or 0

                rrp_latest_snapshot_at = conn.execute(
                    text("SELECT MAX(snapshot_at) FROM rrp_snapshots WHERE project_id = :project_id"),
                    {"project_id": project_id},
                ).scalar()
                
                price_count = conn.execute(
                    text("SELECT COUNT(*) FROM price_snapshots WHERE project_id = :project_id"),
                    {"project_id": project_id},
                ).scalar() or 0
                
                products_count = conn.execute(
                    text("SELECT COUNT(*) FROM v_wb_product_source WHERE project_id = :project_id"),
                    {"project_id": project_id},
                ).scalar() or 0
                
                frontend_count = 0
                if brand_ids:
                    frontend_count = conn.execute(
                        text("""
                            SELECT COUNT(*) FROM frontend_catalog_price_snapshots
                            WHERE query_type = 'brand' AND query_value = ANY(:brand_ids)
                        """),
                        {"brand_ids": brand_ids},
                    ).scalar() or 0
                
                stock_count = conn.execute(
                    text("SELECT COUNT(*) FROM stock_snapshots WHERE project_id = :project_id"),
                    {"project_id": project_id},
                ).scalar() or 0

                # Internal Data snapshot + RRP availability (source of truth for RRP)
                internal_latest = conn.execute(
                    text(
                        """
                        SELECT id, imported_at, status, rows_imported, rows_failed, row_count
                        FROM internal_data_snapshots
                        WHERE project_id = :project_id
                          AND status IN ('success', 'partial')
                        ORDER BY imported_at DESC NULLS LAST, id DESC
                        LIMIT 1
                        """
                    ),
                    {"project_id": project_id},
                ).mappings().first()

                sku_norm_expr = "NULLIF(regexp_replace(trim(both '/' from ip.internal_sku), '^.*/', ''), '')"
                internal_rrp_rows_found = 0
                internal_rrp_rows_matched_products = 0
                internal_rrp_rows_inserted = 0
                internal_rrp_errors_preview: list[dict[str, Any]] = []
                internal_snapshot_id = None
                internal_snapshot_imported_at = None
                internal_snapshot_status = None
                internal_snapshot_rows_imported = None
                internal_snapshot_rows_failed = None
                if internal_latest:
                    internal_snapshot_id = int(internal_latest["id"])
                    internal_snapshot_imported_at = internal_latest.get("imported_at")
                    internal_snapshot_status = internal_latest.get("status")
                    internal_snapshot_rows_imported = internal_latest.get("rows_imported")
                    internal_snapshot_rows_failed = internal_latest.get("rows_failed")

                    internal_rrp_rows_found = (
                        conn.execute(
                            text(
                                f"""
                                SELECT COUNT(*)::bigint
                                FROM (
                                  SELECT DISTINCT {sku_norm_expr} AS sku_norm
                                  FROM internal_product_prices ipp
                                  JOIN internal_products ip ON ip.id = ipp.internal_product_id
                                  WHERE ipp.snapshot_id = :snapshot_id
                                    AND ipp.rrp IS NOT NULL
                                    AND ip.internal_sku IS NOT NULL
                                ) t
                                WHERE t.sku_norm IS NOT NULL
                                """
                            ),
                            {"snapshot_id": internal_snapshot_id},
                        ).scalar()
                        or 0
                    )

                    # How much would match products (vendor_code_norm is generated in DB).
                    internal_rrp_rows_matched_products = (
                        conn.execute(
                            text(
                                f"""
                                WITH src AS (
                                  SELECT DISTINCT {sku_norm_expr} AS sku_norm
                                  FROM internal_product_prices ipp
                                  JOIN internal_products ip ON ip.id = ipp.internal_product_id
                                  WHERE ipp.snapshot_id = :snapshot_id
                                    AND ipp.rrp IS NOT NULL
                                    AND ip.internal_sku IS NOT NULL
                                )
                                SELECT COUNT(*)::bigint
                                FROM src
                                JOIN v_wb_product_source p
                                  ON p.project_id = :project_id
                                 AND p.vendor_code_norm = src.sku_norm
                                WHERE src.sku_norm IS NOT NULL
                                """
                            ),
                            {"project_id": project_id, "snapshot_id": internal_snapshot_id},
                        ).scalar()
                        or 0
                    )

                    # If the builder already ran using snapshot_at=imported_at, show inserted count for that run.
                    if internal_snapshot_imported_at:
                        internal_rrp_rows_inserted = (
                            conn.execute(
                                text(
                                    """
                                    SELECT COUNT(DISTINCT vendor_code_norm)::bigint
                                    FROM rrp_snapshots
                                    WHERE project_id = :project_id
                                      AND source_file = 'internal_data_sync'
                                      AND snapshot_at = :snapshot_at
                                    """
                                ),
                                {"project_id": project_id, "snapshot_at": internal_snapshot_imported_at},
                            ).scalar()
                            or 0
                        )

                    # Recent Internal Data row errors related to RRP (best-effort preview for UX).
                    try:
                        err_rows = (
                            conn.execute(
                                text(
                                    """
                                    SELECT
                                      row_index,
                                      source_key,
                                      error_code,
                                      message,
                                      created_at
                                    FROM internal_data_row_errors
                                    WHERE project_id = :project_id
                                      AND snapshot_id = :snapshot_id
                                      AND (
                                        message ILIKE '%rrp%'
                                        OR COALESCE(source_key, '') ILIKE '%rrp%'
                                      )
                                    ORDER BY created_at DESC NULLS LAST, row_index DESC
                                    LIMIT 20
                                    """
                                ),
                                {"project_id": project_id, "snapshot_id": internal_snapshot_id},
                            )
                            .mappings()
                            .all()
                        )
                        internal_rrp_errors_preview = [
                            {
                                "row_index": int(r.get("row_index")) if r.get("row_index") is not None else None,
                                "source_key": r.get("source_key"),
                                "error_code": r.get("error_code"),
                                "message": r.get("message"),
                                "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
                            }
                            for r in (err_rows or [])
                        ]
                    except Exception:
                        internal_rrp_errors_preview = []
                
                # Check how many products have both RRP and showcase prices
                products_with_both = conn.execute(
                    text("""
                        WITH
                        rrp_run AS (
                            SELECT MAX(snapshot_at) AS run_at FROM rrp_snapshots WHERE project_id = :project_id
                        ),
                        front_run AS (
                            SELECT MAX(f.snapshot_at) AS run_at
                            FROM frontend_catalog_price_snapshots f
                            WHERE f.query_type = 'brand' AND f.query_value = ANY(:brand_ids)
                        ),
                        rrp_latest AS (
                            SELECT s.vendor_code_norm, MAX(s.rrp_price) AS rrp_price
                            FROM rrp_snapshots s
                            JOIN rrp_run r ON s.snapshot_at = r.run_at
                            WHERE s.project_id = :project_id
                            GROUP BY s.vendor_code_norm
                        ),
                        front_latest AS (
                            SELECT DISTINCT ON (f.nm_id) f.nm_id::bigint AS nm_id, f.price_product AS showcase_price
                            FROM frontend_catalog_price_snapshots f
                            JOIN front_run r ON f.snapshot_at = r.run_at
                            WHERE f.query_type = 'brand' AND f.query_value = ANY(:brand_ids)
                            ORDER BY f.nm_id, f.snapshot_at DESC
                        )
                        SELECT COUNT(*) AS count
                        FROM v_wb_product_source p
                        LEFT JOIN rrp_latest ON btrim(rrp_latest.vendor_code_norm) = btrim(p.vendor_code_norm)
                        LEFT JOIN front_latest ON front_latest.nm_id = p.nm_id
                        WHERE p.project_id = :project_id
                          AND p.vendor_code_norm IS NOT NULL
                          AND rrp_latest.rrp_price IS NOT NULL
                          AND front_latest.showcase_price IS NOT NULL
                    """),
                        {"project_id": project_id, "brand_ids": brand_ids},
                    ).scalar() or 0
                
                diagnostic_info = {
                    "data_availability": {
                        "storefront_configured": bool(brand_ids),
                        "storefront_brand_ids": [int(brand_id) for brand_id in brand_ids],
                        "rrp_snapshots_count": rrp_count,
                        "rrp_snapshots_latest_snapshot_at": rrp_latest_snapshot_at.isoformat() if rrp_latest_snapshot_at else None,
                        "price_snapshots_count": price_count,
                        "products_count": products_count,
                        "frontend_catalog_price_snapshots_count": frontend_count,
                        "stock_snapshots_count": stock_count,
                        "products_with_both_rrp_and_showcase": products_with_both,
                        "internal_data_latest_snapshot": {
                            "id": internal_snapshot_id,
                            "imported_at": internal_snapshot_imported_at.isoformat() if internal_snapshot_imported_at else None,
                            "status": internal_snapshot_status,
                            "rows_imported": internal_snapshot_rows_imported,
                            "rows_failed": internal_snapshot_rows_failed,
                        }
                        if internal_snapshot_id is not None
                        else None,
                        "internal_data_rrp_rows_found": int(internal_rrp_rows_found or 0),
                        "internal_data_rrp_rows_matched_products": int(internal_rrp_rows_matched_products or 0),
                        "internal_data_rrp_rows_inserted": int(internal_rrp_rows_inserted or 0),
                        "internal_data_rrp_errors_preview": internal_rrp_errors_preview,
                    },
                    "issues": [],
                    "recommendations": [],
                }
                
                # Identify issues
                if not marketplace_check:
                    diagnostic_info["issues"].append("Wildberries marketplace is not configured for this project")
                    diagnostic_info["recommendations"].append("Connect Wildberries with an API token in project marketplaces")
                elif not brand_ids:
                    diagnostic_info["issues"].append("WB storefront brands are not configured")
                    diagnostic_info["recommendations"].append("Add a WB storefront brand in Wildberries marketplace settings")
                
                if rrp_count == 0:
                    diagnostic_info["issues"].append("No RRP snapshots found")
                    if int(internal_rrp_rows_found or 0) > 0:
                        diagnostic_info["recommendations"].append(
                            "Build RRP snapshots from Internal Data: "
                            "POST /api/v1/projects/{project_id}/ingest/run with domain='build_rrp_snapshots'"
                        )
                    else:
                        diagnostic_info["recommendations"].append(
                            "Import Internal Data with RRP prices (configure mapping_json.fields.rrp) "
                            "and then build snapshots: domain='build_rrp_snapshots'"
                        )
                
                if frontend_count == 0 and brand_ids:
                    diagnostic_info["issues"].append("No frontend catalog price snapshots found")
                    diagnostic_info["recommendations"].append("Run frontend prices ingestion: POST /api/v1/projects/{project_id}/ingest/run with domain='frontend_prices'")

                # If a specific vitrine snapshot was requested, validate it exists for this storefront brand scope.
                if front_snapshot_at is not None and brand_ids:
                    selected_front_count = (
                        conn.execute(
                            text(
                                """
                                SELECT COUNT(DISTINCT f.nm_id)::bigint
                                FROM frontend_catalog_price_snapshots f
                                WHERE f.query_type = 'brand'
                                  AND f.query_value = ANY(:brand_ids)
                                  AND f.snapshot_at = :front_snapshot_at
                                """
                            ),
                            {
                                "brand_ids": brand_ids,
                                "front_snapshot_at": front_snapshot_at,
                            },
                        ).scalar()
                        or 0
                    )
                    diagnostic_info["data_availability"]["front_snapshot_at_requested"] = (
                        front_snapshot_at.isoformat() if isinstance(front_snapshot_at, datetime) else None
                    )
                    diagnostic_info["data_availability"]["front_snapshot_distinct_nm_id_count"] = int(selected_front_count)
                    if int(selected_front_count) == 0:
                        diagnostic_info["issues"].append("Requested frontend showcase snapshot not found for configured storefront brands")
                        diagnostic_info["recommendations"].append(
                            "Pick another snapshot: GET /api/v1/projects/{project_id}/wildberries/price-discrepancies/front-snapshots"
                        )
                
                if products_count == 0:
                    diagnostic_info["issues"].append("No products found")
                    diagnostic_info["recommendations"].append("Run products ingestion: POST /api/v1/projects/{project_id}/ingest/run with domain='products'")
                
                if products_with_both == 0 and rrp_count > 0 and frontend_count > 0:
                    diagnostic_info["issues"].append("No products have both RRP and showcase prices (mapping issue)")
                    diagnostic_info["recommendations"].append("Check vendor_code_norm mapping between products and rrp_snapshots")
        except Exception as e:
            logger.error(
                f"get_wb_price_discrepancies: error collecting diagnostic info for project_id={project_id}: {e}",
                exc_info=True
            )
            # Don't fail the request if diagnostic collection fails
            diagnostic_info = None

    front_snapshot_at_used = front_snapshot_at or _get_latest_front_snapshot_at(project_id)
    updated_at_iso = _get_updated_at(project_id, front_snapshot_at=front_snapshot_at_used)

    response = {
        "meta": {
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "updated_at": updated_at_iso,
            "front_snapshot_at": front_snapshot_at_used.isoformat() if isinstance(front_snapshot_at_used, datetime) else None,
        },
        "items": items,
    }
    
    # Add diagnostic info if no data
    if diagnostic_info:
        response["diagnostic"] = diagnostic_info
    
    return response


@router.get("/{project_id}/wildberries/price-discrepancies/export.csv")
async def export_wb_price_discrepancies_csv(
    project_id: int = Path(..., description="Project ID"),
    q: Optional[str] = Query(None, description="Search by article/nmID/title"),
    category_ids: Optional[str] = Query(
        None,
        description='Comma-separated WB category/subject IDs, e.g. "1,2,3"',
        example="12,34,56",
    ),
    front_snapshot_at: Optional[datetime] = Query(
        None,
        description=(
            "Use a specific WB frontend showcase snapshot_at (UTC recommended). "
            "If omitted, the latest available snapshot is used."
        ),
    ),
    only_below_rrp: bool = Query(
        True,
        description="Filter: only items where showcase_price < rrp_price",
    ),
    has_wb_stock: Literal["any", "true", "false"] = Query(
        "any", description="Filter by WB stock quantity"
    ),
    has_enterprise_stock: Literal["any", "true", "false"] = Query(
        "any", description="Filter by enterprise (1C/XML) stock quantity"
    ),
    sort: Optional[str] = Query(
        "diff_percent_desc",
        description="Sort key, e.g. diff_percent_desc, diff_rub_desc, nm_id_asc",
    ),
    _auth: dict = Depends(allow_client_portal_read),
):
    """Export price discrepancies as CSV with current filters and sort applied."""
    if front_snapshot_at is not None and isinstance(front_snapshot_at, datetime) and front_snapshot_at.tzinfo is None:
        # Treat naive datetimes as UTC to avoid environment-dependent casts in Postgres.
        front_snapshot_at = front_snapshot_at.replace(tzinfo=timezone.utc)

    # Reuse the same SQL builder, but remove pagination limits for export.
    filters = DiscrepancyFilters(
        q=q,
        category_ids=_parse_category_ids(category_ids),
        only_below_rrp=only_below_rrp,
        has_wb_stock=has_wb_stock,
        has_enterprise_stock=has_enterprise_stock,
        front_snapshot_at=front_snapshot_at,
        sort=_parse_sort(sort),
        page=1,
        page_size=1000000,  # large upper bound; DB will still stream
    )
    sql, params = _build_discrepancies_sql(project_id, filters)
    # For export, we don't need COUNT(*) OVER(); but it's harmless to keep it.

    rows: List[Dict[str, Any]] = []
    with engine.connect() as conn:
        result = conn.execute(text(sql), params).mappings().all()
        for row in result:
            rows.append(dict(row))

    # Build CSV in memory
    import io
    import csv

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "article",
            "nm_id",
            "title",
            "wb_admin_price",
            "rrp_price",
            "showcase_price",
            "wb_discount_percent",
            "spp_percent",
            "diff_rub",
            "diff_percent",
            "recommended_wb_admin_price",
            "delta_recommended",
            "expected_showcase_price",
            "wb_stock_qty",
            "enterprise_stock_qty",
            "category_name",
        ]
    )

    for row in rows:
        item = _row_to_item(row)
        prices = item["prices"]
        discounts = item["discounts"]
        stocks = item["stocks"]
        computed = item["computed"]
        category = item.get("category") or {}

        writer.writerow(
            [
                item.get("article") or "",
                item.get("nm_id") or "",
                item.get("title") or "",
                prices.get("wb_admin_price") if prices.get("wb_admin_price") is not None else "",
                prices.get("rrp_price") if prices.get("rrp_price") is not None else "",
                prices.get("showcase_price") if prices.get("showcase_price") is not None else "",
                discounts.get("wb_discount_percent")
                if discounts.get("wb_discount_percent") is not None
                else "",
                discounts.get("spp_percent") if discounts.get("spp_percent") is not None else "",
                computed.get("diff_rub") if computed.get("diff_rub") is not None else "",
                computed.get("diff_percent") if computed.get("diff_percent") is not None else "",
                computed.get("recommended_wb_admin_price")
                if computed.get("recommended_wb_admin_price") is not None
                else "",
                computed.get("delta_recommended")
                if computed.get("delta_recommended") is not None
                else "",
                computed.get("expected_showcase_price")
                if computed.get("expected_showcase_price") is not None
                else "",
                stocks.get("wb_stock_qty") if stocks.get("wb_stock_qty") is not None else "",
                stocks.get("enterprise_stock_qty")
                if stocks.get("enterprise_stock_qty") is not None
                else "",
                category.get("name") or "",
            ]
        )

    csv_bytes = output.getvalue().encode("utf-8-sig")  # BOM for Excel-friendly CSV
    headers = {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": 'attachment; filename="wb_price_discrepancies.csv"',
    }
    return Response(content=csv_bytes, media_type="text/csv", headers=headers)


@router.post("/{project_id}/wildberries/price-discrepancies/diagnose")
async def diagnose_price_discrepancies(
    project_id: int = Path(..., description="Project ID"),
    current_user: dict = Depends(get_current_active_user),
    membership: dict = Depends(get_project_membership),
):
    """Trigger diagnostic task for price discrepancies data availability.
    
    This endpoint enqueues a Celery task to check:
    - WB storefront brand configuration
    - RRP snapshots availability
    - Price snapshots availability
    - Frontend catalog price snapshots availability
    - Stock snapshots availability
    - Products availability
    - Mapping between products and RRP snapshots
    
    Returns task_id for tracking.
    """
    from app.tasks.price_discrepancies import diagnose_data_availability
    
    logger.info(f"diagnose_price_discrepancies: triggering diagnostics for project_id={project_id}")
    
    result = diagnose_data_availability.delay(project_id)
    
    return {
        "task_id": result.id,
        "status": "queued",
        "message": "Diagnostic task queued. Check worker logs for results.",
    }


@router.get("/{project_id}/wildberries/categories")
async def get_wb_categories(
    project_id: int = Path(..., description="Project ID"),
    _auth: dict = Depends(allow_client_portal_read),
):
    """Return list of WB categories for a project.

    If we don't have a dedicated categories table, fall back to distinct
    subject_id/subject_name from products for this project.
    """
    sql = text(
        """
        SELECT DISTINCT
            p.subject_id AS id,
            p.subject_name AS name
        FROM v_wb_product_source p
        WHERE p.project_id = :project_id
          AND p.subject_id IS NOT NULL
        ORDER BY name NULLS LAST, id
        """
    )

    with engine.connect() as conn:
        result = conn.execute(sql, {"project_id": project_id}).mappings().all()
        items = [
            {
                "id": int(row["id"]),
                "name": row["name"],
            }
            for row in result
            if row.get("id") is not None
        ]

    return {"items": items}


@router.get("/{project_id}/wildberries/price-discrepancies/front-snapshots")
async def get_wb_front_price_discrepancies_snapshots(
    project_id: int = Path(..., description="Project ID"),
    limit: int = Query(25, ge=1, le=200, description="Max number of snapshots to return"),
    _auth: dict = Depends(allow_client_portal_read),
):
    """Return available WB frontend showcase snapshot versions for project storefront brands.

    Each item contains snapshot_at + count of distinct nm_id for that snapshot.
    """
    sql = text(
        """
        SELECT
            f.snapshot_at AS snapshot_at,
            COUNT(DISTINCT f.nm_id)::bigint AS items_count
        FROM frontend_catalog_price_snapshots f
        WHERE f.query_type = 'brand'
          AND f.query_value = ANY(:brand_ids)
        GROUP BY f.snapshot_at
        ORDER BY f.snapshot_at DESC
        LIMIT :limit
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {"brand_ids": get_project_frontend_brand_id_strings(project_id), "limit": limit},
        ).mappings().all()

    items = []
    for row in rows:
        snapshot_at = row.get("snapshot_at")
        if isinstance(snapshot_at, datetime):
            if snapshot_at.tzinfo is None:
                snapshot_at = snapshot_at.replace(tzinfo=timezone.utc)
            snapshot_at_str = snapshot_at.isoformat()
        else:
            snapshot_at_str = None
        items.append(
            {
                "snapshot_at": snapshot_at_str,
                "items_count": int(row.get("items_count") or 0),
            }
        )

    return {"items": items}
