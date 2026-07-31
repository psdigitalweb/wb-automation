"""Read-only order geography aggregation from WB finance report raw lines."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text

from app.db import engine


GroupBy = str

_DATE_EXPR = """
COALESCE(
    CASE WHEN r.payload->>'sale_dt' ~ '^\\d{4}-\\d{2}-\\d{2}' THEN left(r.payload->>'sale_dt', 10)::date END,
    CASE WHEN r.payload->>'order_dt' ~ '^\\d{4}-\\d{2}-\\d{2}' THEN left(r.payload->>'order_dt', 10)::date END,
    CASE WHEN r.payload->>'rr_dt' ~ '^\\d{4}-\\d{2}-\\d{2}' THEN left(r.payload->>'rr_dt', 10)::date END,
    CASE WHEN r.payload->>'rr_date' ~ '^\\d{4}-\\d{2}-\\d{2}' THEN left(r.payload->>'rr_date', 10)::date END
)
"""

_AMOUNT_EXPR = """
CASE
    WHEN replace(replace(coalesce(r.payload->>'retail_amount', ''), ' ', ''), ',', '.') ~ '^-?\\d+(\\.\\d+)?$'
    THEN replace(replace(r.payload->>'retail_amount', ' ', ''), ',', '.')::numeric
    ELSE 0
END
"""

_REGION_MARKERS = {
    "область",
    "край",
    "республика",
    "автономный",
    "автономная",
    "округ",
}

_CITY_STOP_WORDS = {
    "улица",
    "ул",
    "проспект",
    "пр-кт",
    "переулок",
    "пер",
    "шоссе",
    "бульвар",
    "бул",
    "площадь",
    "пл",
    "набережная",
    "наб",
    "проезд",
    "тракт",
    "микрорайон",
    "мкр",
    "дом",
    "д",
}

_SETTLEMENT_PREFIXES = {
    "село",
    "деревня",
    "поселок",
    "посёлок",
    "пгт",
}

_FEDERAL_CITIES = {
    "Москва",
    "Санкт-Петербург",
    "Севастополь",
}


@dataclass
class _Bucket:
    country: Optional[str]
    region: Optional[str]
    city: Optional[str]
    ppvz_office_id: Optional[str]
    ppvz_office_name: Optional[str]
    office_name: Optional[str]
    orders: int = 0
    gross_sales: float = 0.0
    nm_counts: Dict[int, int] = field(default_factory=dict)
    first_order_date: Optional[date] = None
    last_order_date: Optional[date] = None


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _parse_region_city(ppvz_office_name: Optional[str], country: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort parser for WB PPVZ strings like "Московская область Подольск улица ...".

    The raw WB string is preserved in API items; this parser is only for MVP grouping.
    """
    name = _clean(ppvz_office_name)
    if not name:
        return "Нет данных ПВЗ", None

    parts = [p for p in re.split(r"\s+", name) if p]
    if len(parts) < 2:
        return None, parts[0] if parts else None

    first_two = " ".join(parts[:2])
    if first_two in {"Москва Москва", "Санкт-Петербург Санкт-Петербург"}:
        return parts[0], parts[1]
    if first_two == "Севастополь Севастополь":
        return "Севастополь", "Севастополь"
    if parts[0] in _FEDERAL_CITIES:
        return parts[0], _extract_city(parts[1:]) or parts[0]

    lower_parts = [p.lower().rstrip(".,") for p in parts]

    if lower_parts[0] == "республика" and len(parts) >= 3:
        region = " ".join(parts[:2])
        city = _extract_city(parts[2:])
        return region, city

    for idx, token in enumerate(lower_parts[:5]):
        if token in {"область", "край"}:
            region = " ".join(parts[: idx + 1])
            city = _extract_city(parts[idx + 1 :])
            return region, city
        if token == "округ" and idx > 0:
            region = " ".join(parts[: idx + 1])
            city = _extract_city(parts[idx + 1 :])
            return region, city

    if "область" in lower_parts:
        idx = lower_parts.index("область")
        region = " ".join(parts[: idx + 1])
        city = _extract_city(parts[idx + 1 :])
        return region, city

    if any(marker in lower_parts[:3] for marker in _REGION_MARKERS):
        city = _extract_city(parts[2:])
        return " ".join(parts[:2]), city

    if country and country != "Россия":
        return country, _extract_city(parts)

    return "Не определено", _extract_city(parts)


def _extract_city(parts: List[str]) -> Optional[str]:
    city_parts: List[str] = []
    normalized_parts = [part.lower().rstrip(".,") for part in parts]
    for idx, part in enumerate(parts):
        normalized = part.lower().rstrip(".,")
        if normalized in _CITY_STOP_WORDS:
            break
        if re.match(r"^\\d", normalized):
            break
        is_settlement_prefix = city_parts and city_parts[0].lower().rstrip(".,") in _SETTLEMENT_PREFIXES
        if (
            city_parts
            and idx + 1 < len(normalized_parts)
            and normalized_parts[idx + 1] in _CITY_STOP_WORDS
            and not (is_settlement_prefix and len(city_parts) < 2)
        ):
            break
        city_parts.append(part)
        if len(city_parts) >= 3:
            break
    return " ".join(city_parts).strip() or None


def _bucket_key(group_by: GroupBy, row: Dict[str, Any], region: Optional[str], city: Optional[str]) -> Tuple[Any, ...]:
    country = _clean(row.get("country"))
    office_name = _clean(row.get("office_name"))
    ppvz_office_id = _clean(row.get("ppvz_office_id"))
    ppvz_office_name = _clean(row.get("ppvz_office_name"))
    if group_by == "country":
        return (country,)
    if group_by == "region":
        return (country, region)
    if group_by == "city":
        return (country, region, city)
    if group_by == "office":
        return (office_name,)
    return (country, region, city, ppvz_office_id, ppvz_office_name)


def _empty_bucket(group_by: GroupBy, row: Dict[str, Any], region: Optional[str], city: Optional[str]) -> _Bucket:
    country = _clean(row.get("country"))
    office_name = _clean(row.get("office_name"))
    ppvz_office_id = _clean(row.get("ppvz_office_id"))
    ppvz_office_name = _clean(row.get("ppvz_office_name"))
    if group_by == "country":
        region = city = ppvz_office_id = ppvz_office_name = office_name = None
    elif group_by == "region":
        city = ppvz_office_id = ppvz_office_name = office_name = None
    elif group_by == "city":
        ppvz_office_id = ppvz_office_name = office_name = None
    elif group_by == "office":
        country = region = city = ppvz_office_id = ppvz_office_name = None
    return _Bucket(
        country=country,
        region=region,
        city=city,
        ppvz_office_id=ppvz_office_id,
        ppvz_office_name=ppvz_office_name,
        office_name=office_name,
    )


def get_order_geography(
    *,
    project_id: int,
    date_from: date,
    date_to: date,
    group_by: GroupBy = "region",
    country: Optional[str] = None,
    nm_id: Optional[int] = None,
    vendor_code: Optional[str] = None,
    office_name: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """Aggregate WB sales geography from raw finance payload."""
    group_by = group_by if group_by in {"country", "region", "city", "ppvz", "office"} else "region"
    limit = min(max(int(limit or 100), 1), 500)

    where = [
        "r.project_id = :project_id",
        "r.payload->>'doc_type_name' = 'Продажа'",
        "r.payload->>'supplier_oper_name' = 'Продажа'",
        f"{_DATE_EXPR} BETWEEN :date_from AND :date_to",
    ]
    params: Dict[str, Any] = {
        "project_id": project_id,
        "date_from": date_from,
        "date_to": date_to,
    }
    if country:
        where.append("r.payload->>'site_country' = :country")
        params["country"] = country
    if nm_id is not None:
        where.append(
            """
            CASE
                WHEN r.payload->>'nm_id' ~ '^\\d+$' THEN (r.payload->>'nm_id')::bigint
                ELSE NULL
            END = :nm_id
            """
        )
        params["nm_id"] = int(nm_id)
    if vendor_code:
        where.append(
            """
            COALESCE(
                NULLIF(r.payload->>'sa_name', ''),
                NULLIF(r.payload->>'vendor_code', ''),
                NULLIF(r.payload->>'vendorCode', '')
            ) ILIKE :vendor_code
            """
        )
        params["vendor_code"] = f"%{vendor_code.strip()}%"
    if office_name:
        where.append("r.payload->>'office_name' ILIKE :office_name")
        params["office_name"] = f"%{office_name.strip()}%"

    sql = text(
        f"""
        WITH filtered_raw AS (
            SELECT r.*
            FROM wb_finance_report_lines r
            WHERE {" AND ".join(where)}
        ),
        missing_ppvz_ids AS (
            SELECT DISTINCT NULLIF(r.payload->>'ppvz_office_id', '') AS ppvz_office_id
            FROM filtered_raw r
            WHERE NULLIF(r.payload->>'ppvz_office_id', '') IS NOT NULL
              AND NULLIF(r.payload->>'ppvz_office_name', '') IS NULL
        ),
        ppvz_name_counts AS (
            SELECT
                NULLIF(r.payload->>'ppvz_office_id', '') AS ppvz_office_id,
                NULLIF(r.payload->>'ppvz_office_name', '') AS ppvz_office_name,
                COUNT(*)::bigint AS rows_count
            FROM wb_finance_report_lines r
            JOIN missing_ppvz_ids ids
              ON ids.ppvz_office_id = NULLIF(r.payload->>'ppvz_office_id', '')
            WHERE r.project_id = :project_id
              AND NULLIF(r.payload->>'ppvz_office_id', '') IS NOT NULL
              AND NULLIF(r.payload->>'ppvz_office_name', '') IS NOT NULL
            GROUP BY 1, 2
        ),
        ppvz_name_map AS (
            SELECT DISTINCT ON (ppvz_office_id)
                ppvz_office_id,
                ppvz_office_name
            FROM ppvz_name_counts
            ORDER BY ppvz_office_id, rows_count DESC, ppvz_office_name
        ),
        sales AS (
            SELECT
                NULLIF(r.payload->>'site_country', '') AS country,
                NULLIF(r.payload->>'ppvz_office_id', '') AS ppvz_office_id,
                COALESCE(
                    NULLIF(r.payload->>'ppvz_office_name', ''),
                    m.ppvz_office_name
                ) AS ppvz_office_name,
                NULLIF(r.payload->>'office_name', '') AS office_name,
                CASE
                    WHEN r.payload->>'nm_id' ~ '^\\d+$' THEN (r.payload->>'nm_id')::bigint
                    ELSE NULL
                END AS nm_id,
                {_DATE_EXPR} AS order_date,
                {_AMOUNT_EXPR} AS retail_amount
            FROM filtered_raw r
            LEFT JOIN ppvz_name_map m
              ON m.ppvz_office_id = NULLIF(r.payload->>'ppvz_office_id', '')
        )
        SELECT
            country,
            ppvz_office_id,
            ppvz_office_name,
            office_name,
            nm_id,
            COUNT(*)::bigint AS orders,
            COALESCE(SUM(retail_amount), 0)::numeric AS gross_sales,
            MIN(order_date) AS first_order_date,
            MAX(order_date) AS last_order_date
        FROM sales
        GROUP BY country, ppvz_office_id, ppvz_office_name, office_name, nm_id
        """
    )

    with engine.connect() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).mappings().all()]

    buckets: Dict[Tuple[Any, ...], _Bucket] = {}
    countries = set()
    regions = set()
    cities = set()
    ppvz_ids = set()
    total_orders = 0
    total_gross_sales = 0.0

    for row in rows:
        row_country = _clean(row.get("country"))
        region, city = _parse_region_city(_clean(row.get("ppvz_office_name")), row_country)
        key = _bucket_key(group_by, row, region, city)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = _empty_bucket(group_by, row, region, city)
            buckets[key] = bucket

        orders = int(row.get("orders") or 0)
        gross_sales = float(row.get("gross_sales") or 0)
        bucket.orders += orders
        bucket.gross_sales += gross_sales
        nm_value = row.get("nm_id")
        if nm_value is not None:
            bucket.nm_counts[int(nm_value)] = bucket.nm_counts.get(int(nm_value), 0) + orders
        first_date = row.get("first_order_date")
        last_date = row.get("last_order_date")
        if first_date is not None and (bucket.first_order_date is None or first_date < bucket.first_order_date):
            bucket.first_order_date = first_date
        if last_date is not None and (bucket.last_order_date is None or last_date > bucket.last_order_date):
            bucket.last_order_date = last_date

        total_orders += orders
        total_gross_sales += gross_sales
        if row_country:
            countries.add(row_country)
        if region:
            regions.add(region)
        if city:
            cities.add(city)
        ppvz_id = _clean(row.get("ppvz_office_id"))
        if ppvz_id:
            ppvz_ids.add(ppvz_id)

    sorted_buckets = sorted(buckets.values(), key=lambda b: (-b.orders, b.country or "", b.region or "", b.city or ""))
    items = [_serialize_bucket(bucket, total_orders) for bucket in sorted_buckets[:limit]]
    top_region = _top_region(rows)

    return {
        "summary": {
            "orders": total_orders,
            "gross_sales": round(total_gross_sales, 2),
            "countries": len(countries),
            "regions": len(regions),
            "cities": len(cities),
            "ppvz_count": len(ppvz_ids),
            "top_region": top_region,
        },
        "items": items,
        "group_by": group_by,
        "limit": limit,
        "total_groups": len(buckets),
    }


def _serialize_bucket(bucket: _Bucket, total_orders: int) -> Dict[str, Any]:
    top_nm_id = None
    top_nm_orders = 0
    if bucket.nm_counts:
        top_nm_id, top_nm_orders = max(bucket.nm_counts.items(), key=lambda item: item[1])
    share = (bucket.orders / total_orders) if total_orders else 0.0
    return {
        "country": bucket.country,
        "region": bucket.region,
        "city": bucket.city,
        "ppvz_office_id": bucket.ppvz_office_id,
        "ppvz_office_name": bucket.ppvz_office_name,
        "office_name": bucket.office_name,
        "orders": bucket.orders,
        "share": share,
        "gross_sales": round(bucket.gross_sales, 2),
        "unique_nm_ids": len(bucket.nm_counts),
        "top_nm_id": top_nm_id,
        "top_nm_orders": top_nm_orders,
        "first_order_date": bucket.first_order_date.isoformat() if bucket.first_order_date else None,
        "last_order_date": bucket.last_order_date.isoformat() if bucket.last_order_date else None,
    }


def _top_region(rows: List[Dict[str, Any]]) -> Optional[str]:
    counts: Dict[str, int] = {}
    for row in rows:
        country = _clean(row.get("country"))
        region, _city = _parse_region_city(_clean(row.get("ppvz_office_name")), country)
        if not region:
            continue
        counts[region] = counts.get(region, 0) + int(row.get("orders") or 0)
    if not counts:
        return None
    top_region, orders = max(counts.items(), key=lambda item: item[1])
    if orders <= 0 or math.isnan(float(orders)):
        return None
    return top_region
