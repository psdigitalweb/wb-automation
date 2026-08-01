"""Celery tasks for ingestion domains.

These tasks wrap existing async ingestion functions so we can enqueue them via Celery
from a single stable API endpoint.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from app.celery_app import celery_app


def _get_frontend_prices_proxy_config(project_id: int) -> tuple[str | None, str | None]:
    """Return (proxy_url, proxy_scheme) for frontend_prices only.

    Safety:
    - Raises on misconfiguration when enabled (to avoid silent non-proxy runs).
    - Does NOT include host/user/pass in exception messages.
    """
    from app.services.project_proxy import get_frontend_prices_proxy_config

    return get_frontend_prices_proxy_config(int(project_id))


@celery_app.task(name="app.tasks.ingestion.prices")
def ingest_prices_task(project_id: int) -> Dict[str, Any]:
    from app.ingest_prices import ingest_prices as _ingest_prices

    result = asyncio.run(_ingest_prices(project_id))
    if isinstance(result, dict):
        status_value = "completed" if result.get("ok", True) else "failed"
        return {**result, "status": status_value}
    return {"status": "completed", "project_id": project_id, "domain": "prices"}


@celery_app.task(name="app.tasks.ingestion.supplier_stocks")
def ingest_supplier_stocks_task(project_id: int) -> Dict[str, Any]:
    from app.ingest_supplier_stocks import ingest_supplier_stocks as _ingest_supplier_stocks

    result = asyncio.run(_ingest_supplier_stocks(project_id))
    status_value = "completed" if result.get("ok", True) else "failed"
    return {**result, "status": status_value}


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
def ingest_frontend_prices_task(project_id: int, run_id: int | None = None) -> Dict[str, Any]:
    """Ingest WB frontend catalog prices for a project.

    Source of configuration:
    - brand_id: project_marketplaces.settings_json.brand_id for WB marketplace (project-scoped)
    - base_url_template/max_pages/sleep_ms/sleep_jitter_ms: project_marketplaces.settings_json.frontend_prices (project-scoped)
      (fallback to app_settings for soft migration)
    """
    from sqlalchemy import text
    from app.db import engine
    from app.ingest_frontend_prices import ingest_frontend_brand_prices
    from app.services.ingest.runs import get_run
    from app.services.wb_storefront_brands import (
        extract_frontend_brand_ids,
        extract_storefront_snapshot_scope,
    )

    brand_id: int | None = None
    base_url_template: str | None = None
    sleep_ms: int = 800
    # Default: full crawl (until empty / totalPages). Can be capped via app_settings.frontend_prices.max_pages.
    max_pages: int = 0
    sleep_jitter_ms: int = 0

    with engine.connect() as conn:
        wb_settings_row = conn.execute(
            text(
                """
                SELECT
                  pm.settings_json AS settings_json,
                  pm.settings_json->'frontend_prices'->>'base_url_template' AS base_url_template,
                  pm.settings_json->'frontend_prices'->>'max_pages' AS fp_max_pages,
                  pm.settings_json->'frontend_prices'->>'sleep_base_ms' AS fp_sleep_base_ms,
                  pm.settings_json->'frontend_prices'->>'sleep_ms' AS fp_sleep_ms,
                  pm.settings_json->'frontend_prices'->>'sleep_jitter_ms' AS fp_sleep_jitter_ms
                FROM project_marketplaces pm
                JOIN marketplaces m ON m.id = pm.marketplace_id
                WHERE pm.project_id = :project_id
                  AND m.code = 'wildberries'
                LIMIT 1
                """
            ),
            {"project_id": project_id},
        ).mappings().first()

        brand_ids = extract_frontend_brand_ids((wb_settings_row or {}).get("settings_json"))
        storefront_scope = extract_storefront_snapshot_scope((wb_settings_row or {}).get("settings_json"))
        base_url_template = (wb_settings_row or {}).get("base_url_template")
        fp_sleep_base_ms_str = (wb_settings_row or {}).get("fp_sleep_base_ms")
        fp_sleep_ms_str = (wb_settings_row or {}).get("fp_sleep_ms")
        fp_max_pages_str = (wb_settings_row or {}).get("fp_max_pages")
        fp_sleep_jitter_ms_str = (wb_settings_row or {}).get("fp_sleep_jitter_ms")

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

    if brand_ids:
        brand_id = brand_ids[0]
    else:
        return {
            "status": "error",
            "domain": "frontend_prices",
            "reason": "no_storefront_brands_configured",
            "project_id": project_id,
            "error": "Добавьте бренд витрины WB в настройках Wildberries для загрузки frontend_prices.",
        }

    if sleep_ms_str:
        try:
            sleep_ms = int(sleep_ms_str)
        except (ValueError, TypeError):
            sleep_ms = 800

    if fp_sleep_base_ms_str:
        try:
            sleep_ms = int(fp_sleep_base_ms_str)
        except (ValueError, TypeError):
            pass
    elif fp_sleep_ms_str:
        try:
            sleep_ms = int(fp_sleep_ms_str)
        except (ValueError, TypeError):
            pass

    if max_pages_str:
        try:
            max_pages = int(max_pages_str)
        except (ValueError, TypeError):
            max_pages = 0

    if fp_max_pages_str:
        try:
            max_pages = int(fp_max_pages_str)
        except (ValueError, TypeError):
            pass

    if fp_sleep_jitter_ms_str:
        try:
            sleep_jitter_ms = int(fp_sleep_jitter_ms_str)
        except (ValueError, TypeError):
            sleep_jitter_ms = 0

    # Normalize
    if sleep_jitter_ms < 0:
        sleep_jitter_ms = abs(sleep_jitter_ms)

    # Hard safety cap to avoid runaway jobs if WB API behaves unexpectedly
    if max_pages > 0:
        max_pages = min(max_pages, 50)

    # Project-scoped proxy settings (applies ONLY to frontend_prices)
    proxy_url, proxy_scheme = _get_frontend_prices_proxy_config(int(project_id))

    print(
        "ingest_frontend_prices_task: "
        f"project_id={project_id} brand_id={brand_id} run_id={run_id} "
        f"base_url_template={'set' if (base_url_template and str(base_url_template).strip()) else 'none'} "
        f"max_pages={max_pages} sleep_ms={sleep_ms} sleep_jitter_ms={sleep_jitter_ms} "
        f"proxy_used={'yes' if proxy_url else 'no'} proxy_scheme={proxy_scheme or 'none'}"
    )

    # base_url_template must be set and contain {brand_id}; ingest_frontend_brand_prices will resolve it
    if not base_url_template or not str(base_url_template).strip():
        # #region agent log
        err_payload = {"hypothesisId": "fp_p2", "location": "ingestion.py:frontend_prices_task", "message": "base_url_template not configured", "data": {"project_id": project_id, "brand_id": brand_id, "reason": "base_url_template_not_configured"}, "timestamp": __import__("time").time() * 1000}
        print(f"[DEBUG] {err_payload}")
        try:
            _log_path = __import__("os").environ.get("DEBUG_LOG_PATH", __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "..", "..", ".cursor", "debug.log"))
            _d = __import__("os").path.dirname(_log_path)
            if _d:
                __import__("os").makedirs(_d, exist_ok=True)
            open(_log_path, "a", encoding="utf-8").write(__import__("json").dumps(err_payload, ensure_ascii=False) + "\n")
        except Exception:
            pass
        # #endregion
        return {
            "status": "error",
            "domain": "frontend_prices",
            "reason": "base_url_template_not_configured",
            "project_id": project_id,
            "brand_id": brand_id,
            "error": "base_url_template not configured or missing {brand_id}; add {brand_id} to project marketplace frontend_prices.base_url_template",
        }

    # Determine run_started_at for stable snapshot buckets (hourly) if run_id is provided.
    run_started_at = None
    if run_id is not None:
        run = get_run(run_id)
        if run:
            run_started_at = run.get("started_at") or run.get("created_at")

    result = asyncio.run(
        ingest_frontend_brand_prices(
            brand_id=brand_id,
            query_type=storefront_scope.query_type,
            base_url=str(base_url_template).strip(),
            max_pages=max_pages,
            sleep_ms=sleep_ms,
            sleep_jitter_ms=sleep_jitter_ms,
            run_id=run_id,
            project_id=project_id,
            run_started_at=run_started_at,
            proxy_url=proxy_url,
            proxy_scheme=proxy_scheme,
        )
    )

    if isinstance(result, dict) and "error" in result:
        # #region agent log
        err_payload = {"hypothesisId": "fp_p2", "location": "ingestion.py:frontend_prices_task", "message": "ingest returned error", "data": {"project_id": project_id, "brand_id": brand_id, "error": result.get("error")}, "timestamp": __import__("time").time() * 1000}
        print(f"[DEBUG] {err_payload}")
        try:
            _log_path = __import__("os").environ.get("DEBUG_LOG_PATH", __import__("os").path.join(__import__("os").path.dirname(__file__), "..", "..", "..", ".cursor", "debug.log"))
            _d = __import__("os").path.dirname(_log_path)
            if _d:
                __import__("os").makedirs(_d, exist_ok=True)
            open(_log_path, "a", encoding="utf-8").write(__import__("json").dumps(err_payload, ensure_ascii=False) + "\n")
        except Exception:
            pass
        # #endregion
        return {
            "status": "error",
            "domain": "frontend_prices",
            "project_id": project_id,
            "brand_id": brand_id,
            **result,
        }

    # Normalize stats_json contract
    stats: Dict[str, Any] = {
        "ok": "error" not in result,
        "project_id": project_id,
        "brand_id": brand_id,
        "max_pages": max_pages,
        "items_total": result.get("distinct_nm_id") or result.get("items_saved") or 0,
        "current_upserts": result.get("current_upserts_total", 0),
        "snapshots_inserted": result.get("showcase_snapshots_inserted_total", 0),
        "spp_events_inserted": result.get("spp_events_inserted_total", 0),
        **{k: v for k, v in result.items() if k not in {
            "current_upserts_total",
            "showcase_snapshots_inserted_total",
            "spp_events_inserted_total",
        }},
    }

    return stats


@celery_app.task(name="app.tasks.ingestion.rrp_xml")
def ingest_rrp_xml_task(project_id: int, run_id: int | None = None) -> Dict[str, Any]:
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
        f"ingest_rrp_xml: file={file_path} parsed={parsed_count} "
        f"written={written_count} skipped={skipped_count} run_id={run_id}"
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
