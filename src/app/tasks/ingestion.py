"""Celery tasks for ingestion domains.

These tasks wrap existing async ingestion functions so we can enqueue them via Celery
from a single stable API endpoint.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from app.celery_app import celery_app


@celery_app.task(name="app.tasks.ingestion.prices")
def ingest_prices_task(project_id: int) -> Dict[str, Any]:
    from app.ingest_prices import ingest_prices as _ingest_prices

    asyncio.run(_ingest_prices(project_id))
    return {"status": "completed", "project_id": project_id, "domain": "prices"}


@celery_app.task(name="app.tasks.ingestion.supplier_stocks")
def ingest_supplier_stocks_task(project_id: int) -> Dict[str, Any]:
    from app.ingest_supplier_stocks import ingest_supplier_stocks as _ingest_supplier_stocks

    asyncio.run(_ingest_supplier_stocks(project_id))
    return {"status": "completed", "project_id": project_id, "domain": "supplier_stocks"}


@celery_app.task(name="app.tasks.ingestion.products")
def ingest_products_task(project_id: int) -> Dict[str, Any]:
    from app.ingest_products import ingest as _ingest_products

    asyncio.run(_ingest_products(project_id, loop_delay_s=0))
    return {"status": "completed", "project_id": project_id, "domain": "products"}


@celery_app.task(name="app.tasks.ingestion.stocks")
def ingest_stocks_task(project_id: int) -> Dict[str, Any]:
    from app.ingest_stocks import ingest_stocks as _ingest_stocks

    asyncio.run(_ingest_stocks(project_id))
    return {"status": "completed", "project_id": project_id, "domain": "stocks"}


@celery_app.task(name="app.tasks.ingestion.warehouses")
def ingest_warehouses_task(_: int) -> Dict[str, Any]:
    """Warehouses ingestion is not project-scoped; project_id is ignored."""
    from app.ingest_stocks import ingest_warehouses as _ingest_warehouses

    asyncio.run(_ingest_warehouses())
    return {"status": "completed", "domain": "warehouses"}


@celery_app.task(name="app.tasks.ingestion.frontend_prices")
def ingest_frontend_prices_task(project_id: int) -> Dict[str, Any]:
    """Ingest WB frontend catalog prices for a project.

    Source of configuration:
    - brand_id: project_marketplaces.settings_json.brand_id for WB marketplace (project-scoped)
    - base_url: app_settings key 'frontend_prices.brand_base_url' (global)
    - sleep_ms: app_settings key 'frontend_prices.sleep_ms' (global, default 800)
    """
    from sqlalchemy import text
    from app.db import engine
    from app.ingest_frontend_prices import ingest_frontend_brand_prices

    brand_id: int | None = None
    sleep_ms: int = 800
    # Default: full crawl (until empty / totalPages). Can be capped via app_settings.frontend_prices.max_pages.
    max_pages: int = 0

    with engine.connect() as conn:
        brand_id_str = conn.execute(
            text(
                """
                SELECT pm.settings_json->>'brand_id' AS brand_id
                FROM project_marketplaces pm
                JOIN marketplaces m ON m.id = pm.marketplace_id
                WHERE pm.project_id = :project_id
                  AND m.code = 'wildberries'
                LIMIT 1
                """
            ),
            {"project_id": project_id},
        ).scalar_one_or_none()

        sleep_ms_str = conn.execute(
            text(
                """
                SELECT value->>'value' AS value
                FROM app_settings
                WHERE key = 'frontend_prices.sleep_ms'
                """
            )
        ).scalar_one_or_none()

        max_pages_str = conn.execute(
            text(
                """
                SELECT value->>'value' AS value
                FROM app_settings
                WHERE key = 'frontend_prices.max_pages'
                """
            )
        ).scalar_one_or_none()

    if brand_id_str:
        try:
            brand_id = int(brand_id_str)
        except (ValueError, TypeError):
            return {
                "status": "error",
                "domain": "frontend_prices",
                "reason": "invalid_brand_id",
                "brand_id": brand_id_str,
            }
    else:
        return {
            "status": "error",
            "domain": "frontend_prices",
            "reason": "brand_id_not_configured_for_project",
            "project_id": project_id,
        }

    if sleep_ms_str:
        try:
            sleep_ms = int(sleep_ms_str)
        except (ValueError, TypeError):
            sleep_ms = 800

    if max_pages_str:
        try:
            max_pages = int(max_pages_str)
        except (ValueError, TypeError):
            max_pages = 0

    # Hard safety cap to avoid runaway jobs if WB API behaves unexpectedly
    if max_pages > 0:
        max_pages = min(max_pages, 50)

    result = asyncio.run(
        ingest_frontend_brand_prices(
            brand_id=brand_id,
            base_url=None,
            max_pages=max_pages,
            sleep_ms=sleep_ms,
        )
    )

    if isinstance(result, dict) and "error" in result:
        return {
            "status": "error",
            "domain": "frontend_prices",
            "project_id": project_id,
            "brand_id": brand_id,
            **result,
        }

    return {
        "status": "completed",
        "domain": "frontend_prices",
        "project_id": project_id,
        "brand_id": brand_id,
        "max_pages": max_pages,
        "result": result,
    }


@celery_app.task(name="app.tasks.ingestion.rrp_xml")
def ingest_rrp_xml_task(project_id: int) -> Dict[str, Any]:
    """Ingest RRP prices from a local XML file (MVP).

    Source file:
    - env RRP_XML_PATH, else /app/test.xml

    Expected XML format (current test.xml):
      <items>
        <item article="SKU" stock="123" price="84"/>
      </items>
    """
    import os
    import xml.etree.ElementTree as ET
    from decimal import Decimal, InvalidOperation

    from sqlalchemy import text
    from app.db import engine

    file_path = os.getenv("RRP_XML_PATH", "/app/test.xml")

    parsed_count = 0
    skipped_count = 0
    written_count = 0

    # Parse (streaming)
    by_sku: dict[str, dict[str, Any]] = {}
    snapshots: list[dict[str, Any]] = []
    try:
        for _, elem in ET.iterparse(file_path, events=("end",)):
            if elem.tag != "item":
                continue

            raw_sku = (elem.attrib.get("article") or "").strip()
            raw_price = (elem.attrib.get("price") or "").strip()
            raw_qty = (elem.attrib.get("stock") or "").strip()
            raw_barcode = (elem.attrib.get("barcode") or "").strip()

            if not raw_sku or not raw_price:
                skipped_count += 1
                elem.clear()
                continue

            # SKU cleanup:
            # - "560/ZKPY-1138" -> "ZKPY-1138"
            # - "4003/" -> "4003"
            parts = [p.strip() for p in raw_sku.split("/") if p.strip()]
            sku = parts[-1] if parts else raw_sku.strip().strip("/")
            if not sku:
                skipped_count += 1
                elem.clear()
                continue

            try:
                price = Decimal(raw_price)
            except (InvalidOperation, ValueError):
                skipped_count += 1
                elem.clear()
                continue

            qty: int | None = None
            if raw_qty:
                try:
                    qty = int(raw_qty)
                except Exception:
                    qty = None

            parsed_count += 1
            by_sku[sku] = {
                "project_id": project_id,
                "sku": sku,
                "rrp_price": price,
                "qty": qty,
                "source_file": file_path,
            }
            snapshots.append(
                {
                    "project_id": project_id,
                    "vendor_code_raw": raw_sku,
                    "vendor_code_norm": sku,
                    "barcode": raw_barcode or None,
                    "rrp_price": price,
                    "rrp_stock": qty,
                    "source_file": file_path,
                }
            )
            elem.clear()
    except FileNotFoundError:
        return {
            "status": "error",
            "domain": "rrp_xml",
            "reason": "file_not_found",
            "file_path": file_path,
        }
    except Exception as e:
        return {
            "status": "error",
            "domain": "rrp_xml",
            "reason": f"{type(e).__name__}: {e}",
            "file_path": file_path,
        }

    rows = list(by_sku.values())
    if not rows:
        return {
            "status": "completed",
            "domain": "rrp_xml",
            "project_id": project_id,
            "file_path": file_path,
            "parsed_count": parsed_count,
            "written_count": 0,
            "skipped_count": skipped_count,
            "message": "No valid items found in XML",
        }

    upsert_sql = text(
        """
        INSERT INTO rrp_prices (project_id, sku, rrp_price, qty, source_file, created_at, updated_at)
        VALUES (:project_id, :sku, :rrp_price, :qty, :source_file, now(), now())
        ON CONFLICT (project_id, sku)
        DO UPDATE SET
          rrp_price = EXCLUDED.rrp_price,
          qty = EXCLUDED.qty,
          source_file = EXCLUDED.source_file,
          updated_at = now()
        """
    )

    with engine.begin() as conn:
        # Append-only snapshots
        conn.execute(
            text(
                """
                INSERT INTO rrp_snapshots
                  (project_id, snapshot_at, vendor_code_raw, vendor_code_norm, barcode, rrp_price, rrp_stock, source_file)
                VALUES
                  (:project_id, now(), :vendor_code_raw, :vendor_code_norm, :barcode, :rrp_price, :rrp_stock, :source_file)
                """
            ),
            snapshots,
        )
        conn.execute(upsert_sql, rows)
        written_count = len(rows)

    print(
        f"ingest_rrp_xml: file={file_path} parsed={parsed_count} written={written_count} skipped={skipped_count}"
    )

    return {
        "status": "completed",
        "domain": "rrp_xml",
        "project_id": project_id,
        "file_path": file_path,
        "parsed_count": parsed_count,
        "written_count": written_count,
        "skipped_count": skipped_count,
    }

