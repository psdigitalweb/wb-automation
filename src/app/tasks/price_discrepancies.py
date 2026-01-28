"""Celery tasks for price discrepancies diagnostics and validation.

This module provides:
- Diagnostic task to check data availability for price discrepancies report
- Validation task to ensure all required data is present after ingestion
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text

from app.celery_app import celery_app
from app.db import engine

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.price_discrepancies.diagnose_data_availability")
def diagnose_data_availability(project_id: int) -> Dict[str, Any]:
    """Diagnose data availability for price discrepancies report.
    
    Checks:
    - brand_id configuration in project_marketplaces
    - RRP snapshots availability
    - Price snapshots availability
    - Frontend catalog price snapshots availability
    - Stock snapshots availability
    - Products availability
    - Mapping between products.vendor_code_norm and rrp_snapshots.vendor_code_norm
    
    Returns diagnostic report with counts and warnings.
    """
    logger.info(f"diagnose_data_availability: starting for project_id={project_id}")
    start_time = datetime.now(timezone.utc)
    
    diagnostics: Dict[str, Any] = {
        "project_id": project_id,
        "started_at": start_time.isoformat(),
        "checks": {},
        "warnings": [],
        "errors": [],
    }
    
    with engine.connect() as conn:
        # Check 1: brand_id configuration
        brand_id_result = conn.execute(
            text("""
                SELECT pm.settings_json->>'brand_id' AS brand_id,
                       pm.is_enabled,
                       m.code AS marketplace_code
                FROM project_marketplaces pm
                JOIN marketplaces m ON m.id = pm.marketplace_id
                WHERE pm.project_id = :project_id
                  AND m.code = 'wildberries'
                LIMIT 1
            """),
            {"project_id": project_id},
        ).mappings().first()
        
        if not brand_id_result:
            diagnostics["errors"].append(
                "No Wildberries marketplace configured for this project. "
                "Please configure marketplace in project settings."
            )
            diagnostics["checks"]["brand_id"] = {
                "configured": False,
                "brand_id": None,
                "is_enabled": False,
            }
        else:
            brand_id_str = brand_id_result.get("brand_id")
            brand_id = None
            if brand_id_str:
                try:
                    brand_id = int(brand_id_str)
                except (ValueError, TypeError):
                    diagnostics["warnings"].append(
                        f"brand_id is not a valid integer: {brand_id_str}"
                    )
            
            diagnostics["checks"]["brand_id"] = {
                "configured": brand_id is not None,
                "brand_id": brand_id,
                "is_enabled": bool(brand_id_result.get("is_enabled")),
            }
            
            if not brand_id:
                diagnostics["warnings"].append(
                    "brand_id is not configured in project_marketplaces.settings_json. "
                    "Frontend catalog prices cannot be filtered by brand."
                )
        
        # Check 2: RRP snapshots
        rrp_stats = conn.execute(
            text("""
                SELECT 
                    COUNT(*) AS total_count,
                    COUNT(DISTINCT vendor_code_norm) AS distinct_skus,
                    MAX(snapshot_at) AS latest_snapshot_at,
                    MIN(snapshot_at) AS earliest_snapshot_at
                FROM rrp_snapshots
                WHERE project_id = :project_id
            """),
            {"project_id": project_id},
        ).mappings().first()
        
        rrp_count = rrp_stats["total_count"] or 0
        diagnostics["checks"]["rrp_snapshots"] = {
            "count": rrp_count,
            "distinct_skus": rrp_stats["distinct_skus"] or 0,
            "latest_snapshot_at": rrp_stats["latest_snapshot_at"].isoformat() if rrp_stats["latest_snapshot_at"] else None,
            "earliest_snapshot_at": rrp_stats["earliest_snapshot_at"].isoformat() if rrp_stats["earliest_snapshot_at"] else None,
        }
        
        if rrp_count == 0:
            diagnostics["warnings"].append(
                f"No RRP snapshots found for project_id={project_id}. "
                "Run RRP XML ingestion to populate data."
            )
        
        # Check 3: Price snapshots (WB admin prices)
        price_stats = conn.execute(
            text("""
                SELECT 
                    COUNT(*) AS total_count,
                    COUNT(DISTINCT nm_id) AS distinct_nm_ids,
                    MAX(created_at) AS latest_created_at,
                    MIN(created_at) AS earliest_created_at
                FROM price_snapshots
                WHERE project_id = :project_id
            """),
            {"project_id": project_id},
        ).mappings().first()
        
        price_count = price_stats["total_count"] or 0
        diagnostics["checks"]["price_snapshots"] = {
            "count": price_count,
            "distinct_nm_ids": price_stats["distinct_nm_ids"] or 0,
            "latest_created_at": price_stats["latest_created_at"].isoformat() if price_stats["latest_created_at"] else None,
            "earliest_created_at": price_stats["earliest_created_at"].isoformat() if price_stats["earliest_created_at"] else None,
        }
        
        if price_count == 0:
            diagnostics["warnings"].append(
                f"No price snapshots found for project_id={project_id}. "
                "Run prices ingestion to populate data."
            )
        
        # Check 4: Frontend catalog price snapshots (if brand_id is configured)
        if brand_id:
            frontend_stats = conn.execute(
                text("""
                    SELECT 
                        COUNT(*) AS total_count,
                        COUNT(DISTINCT nm_id) AS distinct_nm_ids,
                        MAX(snapshot_at) AS latest_snapshot_at,
                        MIN(snapshot_at) AS earliest_snapshot_at
                    FROM frontend_catalog_price_snapshots
                    WHERE query_type = 'brand'
                      AND query_value = :brand_id
                """),
                {"brand_id": str(brand_id)},
            ).mappings().first()
            
            frontend_count = frontend_stats["total_count"] or 0
            diagnostics["checks"]["frontend_catalog_price_snapshots"] = {
                "count": frontend_count,
                "distinct_nm_ids": frontend_stats["distinct_nm_ids"] or 0,
                "latest_snapshot_at": frontend_stats["latest_snapshot_at"].isoformat() if frontend_stats["latest_snapshot_at"] else None,
                "earliest_snapshot_at": frontend_stats["earliest_snapshot_at"].isoformat() if frontend_stats["earliest_snapshot_at"] else None,
            }
            
            if frontend_count == 0:
                diagnostics["warnings"].append(
                    f"No frontend catalog price snapshots found for brand_id={brand_id}. "
                    "Run frontend_prices ingestion to populate data."
                )
        else:
            diagnostics["checks"]["frontend_catalog_price_snapshots"] = {
                "count": 0,
                "distinct_nm_ids": 0,
                "latest_snapshot_at": None,
                "earliest_snapshot_at": None,
                "skipped": "brand_id not configured",
            }
        
        # Check 5: Stock snapshots
        stock_stats = conn.execute(
            text("""
                SELECT 
                    COUNT(*) AS total_count,
                    COUNT(DISTINCT nm_id) AS distinct_nm_ids,
                    MAX(snapshot_at) AS latest_snapshot_at,
                    MIN(snapshot_at) AS earliest_snapshot_at
                FROM stock_snapshots
                WHERE project_id = :project_id
            """),
            {"project_id": project_id},
        ).mappings().first()
        
        stock_count = stock_stats["total_count"] or 0
        diagnostics["checks"]["stock_snapshots"] = {
            "count": stock_count,
            "distinct_nm_ids": stock_stats["distinct_nm_ids"] or 0,
            "latest_snapshot_at": stock_stats["latest_snapshot_at"].isoformat() if stock_stats["latest_snapshot_at"] else None,
            "earliest_snapshot_at": stock_stats["earliest_snapshot_at"].isoformat() if stock_stats["earliest_snapshot_at"] else None,
        }
        
        if stock_count == 0:
            diagnostics["warnings"].append(
                f"No stock snapshots found for project_id={project_id}. "
                "Run stocks ingestion to populate data."
            )
        
        # Check 6: Products
        products_stats = conn.execute(
            text("""
                SELECT 
                    COUNT(*) AS total_count,
                    COUNT(DISTINCT nm_id) AS distinct_nm_ids,
                    COUNT(DISTINCT vendor_code_norm) AS distinct_vendor_codes
                FROM products
                WHERE project_id = :project_id
            """),
            {"project_id": project_id},
        ).mappings().first()
        
        products_count = products_stats["total_count"] or 0
        diagnostics["checks"]["products"] = {
            "count": products_count,
            "distinct_nm_ids": products_stats["distinct_nm_ids"] or 0,
            "distinct_vendor_codes": products_stats["distinct_vendor_codes"] or 0,
        }
        
        if products_count == 0:
            diagnostics["warnings"].append(
                f"No products found for project_id={project_id}. "
                "Run products ingestion to populate data."
            )
        
        # Check 7: Mapping between products.vendor_code_norm and rrp_snapshots.vendor_code_norm
        if products_count > 0 and rrp_count > 0:
            mapping_stats = conn.execute(
                text("""
                    SELECT 
                        COUNT(DISTINCT p.vendor_code_norm) AS products_with_rrp,
                        COUNT(DISTINCT p.nm_id) AS products_with_rrp_and_nm_id
                    FROM products p
                    INNER JOIN rrp_snapshots r ON r.vendor_code_norm = p.vendor_code_norm
                    WHERE p.project_id = :project_id
                      AND r.project_id = :project_id
                """),
                {"project_id": project_id},
            ).mappings().first()
            
            products_with_rrp = mapping_stats["products_with_rrp"] or 0
            diagnostics["checks"]["vendor_code_mapping"] = {
                "products_with_rrp": products_with_rrp,
                "products_with_rrp_and_nm_id": mapping_stats["products_with_rrp_and_nm_id"] or 0,
                "coverage_percent": round((products_with_rrp / products_stats["distinct_vendor_codes"]) * 100, 2) if products_stats["distinct_vendor_codes"] > 0 else 0,
            }
            
            if products_with_rrp == 0:
                diagnostics["warnings"].append(
                    "No mapping found between products.vendor_code_norm and rrp_snapshots.vendor_code_norm. "
                    "Price discrepancies report will show no RRP prices."
                )
            elif products_with_rrp < products_stats["distinct_vendor_codes"] * 0.5:
                diagnostics["warnings"].append(
                    f"Low mapping coverage: only {products_with_rrp}/{products_stats['distinct_vendor_codes']} "
                    f"products have matching RRP snapshots ({round((products_with_rrp / products_stats['distinct_vendor_codes']) * 100, 2)}%)."
                )
        
        # Check 8: Sample query to see if report would return data
        if brand_id and products_count > 0:
            sample_query = text("""
                WITH
                brand AS (
                    SELECT pm.settings_json->>'brand_id' AS brand_id
                    FROM project_marketplaces pm
                    JOIN marketplaces m ON m.id = pm.marketplace_id
                    WHERE pm.project_id = :project_id
                      AND m.code = 'wildberries'
                    LIMIT 1
                ),
                rrp_run AS (
                    SELECT MAX(snapshot_at) AS run_at
                    FROM rrp_snapshots
                    WHERE project_id = :project_id
                ),
                front_run AS (
                    SELECT MAX(f.snapshot_at) AS run_at
                    FROM frontend_catalog_price_snapshots f
                    JOIN brand b ON b.brand_id IS NOT NULL
                    WHERE f.query_type = 'brand'
                      AND f.query_value = b.brand_id
                ),
                rrp_latest AS (
                    SELECT s.vendor_code_norm,
                           MAX(s.rrp_price) AS rrp_price
                    FROM rrp_snapshots s
                    JOIN rrp_run r ON s.snapshot_at = r.run_at
                    WHERE s.project_id = :project_id
                    GROUP BY s.vendor_code_norm
                ),
                front_latest AS (
                    SELECT DISTINCT ON (f.nm_id)
                        f.nm_id::bigint AS nm_id,
                        f.price_product AS showcase_price
                    FROM frontend_catalog_price_snapshots f
                    JOIN brand b ON b.brand_id IS NOT NULL
                    JOIN front_run r ON f.snapshot_at = r.run_at
                    WHERE f.query_type = 'brand'
                      AND f.query_value = b.brand_id
                    ORDER BY f.nm_id, f.snapshot_at DESC
                )
                SELECT COUNT(*) AS sample_count
                FROM products p
                LEFT JOIN rrp_latest ON rrp_latest.vendor_code_norm = p.vendor_code_norm
                LEFT JOIN front_latest ON front_latest.nm_id = p.nm_id
                WHERE p.project_id = :project_id
                  AND p.vendor_code_norm IS NOT NULL
                  AND rrp_latest.rrp_price IS NOT NULL
                  AND front_latest.showcase_price IS NOT NULL
                LIMIT 10
            """)
            
            sample_result = conn.execute(sample_query, {"project_id": project_id}).scalar()
            diagnostics["checks"]["sample_report_query"] = {
                "rows_with_both_rrp_and_showcase": sample_result or 0,
            }
            
            if sample_result == 0:
                diagnostics["warnings"].append(
                    "Sample query returned 0 rows with both RRP and showcase prices. "
                    "Price discrepancies report will be empty."
                )
    
    end_time = datetime.now(timezone.utc)
    elapsed_ms = (end_time - start_time).total_seconds() * 1000
    
    diagnostics["completed_at"] = end_time.isoformat()
    diagnostics["elapsed_ms"] = round(elapsed_ms, 2)
    diagnostics["summary"] = {
        "total_warnings": len(diagnostics["warnings"]),
        "total_errors": len(diagnostics["errors"]),
        "has_data": all([
            diagnostics["checks"].get("rrp_snapshots", {}).get("count", 0) > 0,
            diagnostics["checks"].get("price_snapshots", {}).get("count", 0) > 0,
            diagnostics["checks"].get("frontend_catalog_price_snapshots", {}).get("count", 0) > 0,
            diagnostics["checks"].get("products", {}).get("count", 0) > 0,
        ]),
    }
    
    logger.info(
        f"diagnose_data_availability: completed for project_id={project_id} "
        f"warnings={len(diagnostics['warnings'])} errors={len(diagnostics['errors'])} "
        f"elapsed={elapsed_ms:.2f}ms"
    )
    
    # Log warnings and errors
    for warning in diagnostics["warnings"]:
        logger.warning(f"diagnose_data_availability: project_id={project_id} WARNING: {warning}")
    
    for error in diagnostics["errors"]:
        logger.error(f"diagnose_data_availability: project_id={project_id} ERROR: {error}")
    
    return diagnostics


@celery_app.task(name="app.tasks.price_discrepancies.diagnose_all_projects_data_availability")
def diagnose_all_projects_data_availability() -> Dict[str, Any]:
    """Diagnose data availability for all projects with Wildberries marketplace enabled.
    
    This task is scheduled to run periodically (every 6 hours) to check data availability
    for price discrepancies reports across all projects.
    
    Returns summary with counts per project.
    """
    logger.info("diagnose_all_projects_data_availability: starting")
    start_time = datetime.now(timezone.utc)
    
    with engine.connect() as conn:
        # Get all projects with Wildberries marketplace enabled
        projects = conn.execute(
            text("""
                SELECT DISTINCT pm.project_id
                FROM project_marketplaces pm
                JOIN marketplaces m ON m.id = pm.marketplace_id
                WHERE m.code = 'wildberries'
                  AND pm.is_enabled = TRUE
            """)
        ).scalars().all()
    
    project_ids = list(projects)
    logger.info(f"diagnose_all_projects_data_availability: found {len(project_ids)} projects with WB enabled")
    
    results = []
    for project_id in project_ids:
        try:
            result = diagnose_data_availability(project_id)
            results.append({
                "project_id": project_id,
                "summary": result.get("summary", {}),
                "warnings_count": len(result.get("warnings", [])),
                "errors_count": len(result.get("errors", [])),
            })
        except Exception as e:
            logger.error(
                f"diagnose_all_projects_data_availability: failed for project_id={project_id}: {e}",
                exc_info=True
            )
            results.append({
                "project_id": project_id,
                "error": str(e),
            })
    
    end_time = datetime.now(timezone.utc)
    elapsed_ms = (end_time - start_time).total_seconds() * 1000
    
    summary = {
        "started_at": start_time.isoformat(),
        "completed_at": end_time.isoformat(),
        "elapsed_ms": round(elapsed_ms, 2),
        "projects_checked": len(project_ids),
        "projects_with_warnings": sum(1 for r in results if r.get("warnings_count", 0) > 0),
        "projects_with_errors": sum(1 for r in results if r.get("errors_count", 0) > 0),
        "results": results,
    }
    
    logger.info(
        f"diagnose_all_projects_data_availability: completed "
        f"projects_checked={len(project_ids)} "
        f"projects_with_warnings={summary['projects_with_warnings']} "
        f"projects_with_errors={summary['projects_with_errors']} "
        f"elapsed={elapsed_ms:.2f}ms"
    )
    
    return summary
