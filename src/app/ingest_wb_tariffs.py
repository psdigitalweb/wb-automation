"""Ingestion routines for Wildberries Tariffs (marketplace-level, not project-scoped)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone, date
from typing import Any, Dict, List, Optional

from app.db_marketplace_tariffs import save_snapshot
from app.wb.common_client import WBCommonApiClient


MARKETPLACE_CODE = "wildberries"
DATA_DOMAIN = "tariffs"


async def ingest_wb_tariffs_commission(locale: str = "ru") -> Dict[str, Any]:
    """Fetch commission tariffs (locale-scoped, no date) and store snapshot."""
    client = WBCommonApiClient()
    res = await client.fetch_commission(locale=locale)

    http_status = res.get("http_status", 0)
    payload = res.get("payload")
    error: Optional[str] = None
    if http_status != 200:
        error = f"HTTP {http_status}"

    meta = save_snapshot(
        marketplace_code=MARKETPLACE_CODE,
        data_domain=DATA_DOMAIN,
        data_type="commission",
        as_of_date=None,
        locale=locale,
        request_params={"locale": locale},
        payload=payload,
        http_status=http_status,
        error=error,
    )

    return {
        "type": "commission",
        "locale": locale,
        "http_status": http_status,
        **meta,
    }


async def ingest_wb_tariffs_box(target_date: date) -> Dict[str, Any]:
    client = WBCommonApiClient()
    date_str = target_date.isoformat()
    res = await client.fetch_box_tariffs(date=date_str)
    http_status = res.get("http_status", 0)
    payload = res.get("payload")
    error: Optional[str] = None
    if http_status != 200:
        error = f"HTTP {http_status}"

    meta = save_snapshot(
        marketplace_code=MARKETPLACE_CODE,
        data_domain=DATA_DOMAIN,
        data_type="box",
        as_of_date=target_date,
        locale=None,
        request_params={"date": date_str},
        payload=payload,
        http_status=http_status,
        error=error,
    )
    return {
        "type": "box",
        "date": date_str,
        "http_status": http_status,
        **meta,
    }


async def ingest_wb_tariffs_pallet(target_date: date) -> Dict[str, Any]:
    client = WBCommonApiClient()
    date_str = target_date.isoformat()
    res = await client.fetch_pallet_tariffs(date=date_str)
    http_status = res.get("http_status", 0)
    payload = res.get("payload")
    error: Optional[str] = None
    if http_status != 200:
        error = f"HTTP {http_status}"

    meta = save_snapshot(
        marketplace_code=MARKETPLACE_CODE,
        data_domain=DATA_DOMAIN,
        data_type="pallet",
        as_of_date=target_date,
        locale=None,
        request_params={"date": date_str},
        payload=payload,
        http_status=http_status,
        error=error,
    )
    return {
        "type": "pallet",
        "date": date_str,
        "http_status": http_status,
        **meta,
    }


async def ingest_wb_tariffs_return(target_date: date) -> Dict[str, Any]:
    client = WBCommonApiClient()
    date_str = target_date.isoformat()
    res = await client.fetch_return_tariffs(date=date_str)
    http_status = res.get("http_status", 0)
    payload = res.get("payload")
    error: Optional[str] = None
    if http_status != 200:
        error = f"HTTP {http_status}"

    meta = save_snapshot(
        marketplace_code=MARKETPLACE_CODE,
        data_domain=DATA_DOMAIN,
        data_type="return",
        as_of_date=target_date,
        locale=None,
        request_params={"date": date_str},
        payload=payload,
        http_status=http_status,
        error=error,
    )
    return {
        "type": "return",
        "date": date_str,
        "http_status": http_status,
        **meta,
    }


async def ingest_wb_tariffs_acceptance_coefficients(
    warehouse_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    client = WBCommonApiClient()
    res = await client.fetch_acceptance_coefficients(warehouse_ids=warehouse_ids)
    http_status = res.get("http_status", 0)
    payload = res.get("payload")
    error: Optional[str] = None
    if http_status != 200:
        error = f"HTTP {http_status}"

    request_params: Dict[str, Any] = {}
    if warehouse_ids:
        request_params["warehouse_ids"] = warehouse_ids

    meta = save_snapshot(
        marketplace_code=MARKETPLACE_CODE,
        data_domain=DATA_DOMAIN,
        data_type="acceptance_coefficients",
        as_of_date=None,
        locale=None,
        request_params=request_params,
        payload=payload,
        http_status=http_status,
        error=error,
    )
    return {
        "type": "acceptance_coefficients",
        "http_status": http_status,
        **meta,
    }


async def ingest_wb_tariffs_all(days_ahead: int = 14) -> Dict[str, Any]:
    """Orchestrate full tariffs ingestion (idempotent via snapshot dedup).

    Strategy:
      - commission (locale=ru)
      - acceptance_coefficients (all warehouses)
      - box/pallet/return for today .. today+days_ahead (UTC)
    """
    today = datetime.now(timezone.utc).date()
    dates: List[date] = [today + timedelta(days=i) for i in range(0, days_ahead + 1)]

    print(
        f"ingest_wb_tariffs_all: starting for {len(dates)} dates "
        f"from {dates[0]} to {dates[-1]}"
    )

    results: Dict[str, Any] = {
        "commission": None,
        "acceptance_coefficients": None,
        "dates_total": len(dates),
        "box": {"inserted": 0, "skipped": 0},
        "pallet": {"inserted": 0, "skipped": 0},
        "return": {"inserted": 0, "skipped": 0},
    }

    # Commission
    commission_res = await ingest_wb_tariffs_commission(locale="ru")
    results["commission"] = commission_res

    # Acceptance coefficients (all warehouses)
    acc_res = await ingest_wb_tariffs_acceptance_coefficients(warehouse_ids=None)
    results["acceptance_coefficients"] = acc_res

    # Throttling between heavy endpoints
    await asyncio.sleep(0.5)

    # Box / pallet / return for each date, sequentially with small sleeps
    for d in dates:
        box_res = await ingest_wb_tariffs_box(d)
        if box_res.get("inserted"):
            results["box"]["inserted"] += 1
        else:
            results["box"]["skipped"] += 1

        await asyncio.sleep(0.3)

        pallet_res = await ingest_wb_tariffs_pallet(d)
        if pallet_res.get("inserted"):
            results["pallet"]["inserted"] += 1
        else:
            results["pallet"]["skipped"] += 1

        await asyncio.sleep(0.3)

        return_res = await ingest_wb_tariffs_return(d)
        if return_res.get("inserted"):
            results["return"]["inserted"] += 1
        else:
            results["return"]["skipped"] += 1

        await asyncio.sleep(0.3)

    print(
        "ingest_wb_tariffs_all: finished. "
        f"dates={len(dates)} "
        f"box_inserted={results['box']['inserted']} box_skipped={results['box']['skipped']} "
        f"pallet_inserted={results['pallet']['inserted']} pallet_skipped={results['pallet']['skipped']} "
        f"return_inserted={results['return']['inserted']} return_skipped={results['return']['skipped']}"
    )

    return results


def _sync_entry() -> None:
    asyncio.run(ingest_wb_tariffs_all())


if __name__ == "__main__":
    _sync_entry()

