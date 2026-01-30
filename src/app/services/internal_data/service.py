"""High-level Internal Data service: settings load, URL test, sync."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

from app.db_internal_data import (
    create_snapshot_with_rows,
    get_internal_data_settings,
    update_sync_result,
    update_test_result,
    upsert_internal_data_settings,
)
from app.services.internal_data.parsers import (
    parse_csv,
    parse_xlsx,
    parse_xml,
    introspect_csv,
    introspect_xlsx,
    introspect_xml,
    iter_rows_csv,
    iter_rows_xlsx,
    iter_items_xml,
)
from app.services.internal_data.sources import DownloadResult, download_file_from_url, get_file_from_storage, test_url_reachability


@dataclass
class TestUrlResult:
    ok: bool
    http_status: Optional[int]
    error: Optional[str]
    final_url: Optional[str]
    content_type: Optional[str]
    content_length: Optional[int]


@dataclass
class SourceInfo:
    settings: Dict[str, Any]
    download: DownloadResult
    kind: str  # 'table' or 'xml'


def get_or_create_settings(project_id: int) -> Dict[str, Any]:
    """Return settings row, creating a disabled default if missing."""
    settings = get_internal_data_settings(project_id)
    if settings:
        return settings
    return upsert_internal_data_settings(
        project_id,
        source_mode=None,
        source_url=None,
        file_storage_key=None,
        file_original_name=None,
        file_format=None,
        is_enabled=False,
        mapping_json={},
    )


def test_url_for_project(project_id: int, url: Optional[str]) -> TestUrlResult:
    # #region agent log
    try:
        import json, time
        with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H1","location":"service.py:66","message":"test_url_for_project called","data":{"project_id":project_id,"url":url},"timestamp":int(time.time()*1000)})+"\n")
    except Exception:
        pass
    # #endregion
    settings = get_or_create_settings(project_id)
    effective_url = url or settings.get("source_url")
    if not effective_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="URL is required for testing",
        )

    try:
        # #region agent log
        try:
            import json, time
            with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H1","location":"service.py:83","message":"Before test_url_reachability","data":{"effective_url":effective_url},"timestamp":int(time.time()*1000)})+"\n")
        except Exception:
            pass
        # #endregion
        # Use optimized URL testing function that only downloads first 1KB instead of entire file
        import time as time_module
        start_time = time_module.time()
        ok, err, http_status, content_type, content_length, final_url = test_url_reachability(effective_url)
        duration = time_module.time() - start_time
        # #region agent log
        try:
            import json, time
            with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H1","location":"service.py:87","message":"test_url_reachability completed","data":{"duration":duration,"ok":ok,"http_status":http_status,"content_length":content_length,"final_url":final_url},"timestamp":int(time.time()*1000)})+"\n")
        except Exception:
            pass
        # #endregion
        if not final_url:
            final_url = effective_url  # Fallback to original URL if final_url not available
    except Exception as exc:
        # #region agent log
        try:
            import json, time, traceback
            with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H1","location":"service.py:95","message":"test_url_reachability exception","data":{"error":str(exc),"error_type":type(exc).__name__},"timestamp":int(time.time()*1000)})+"\n")
        except Exception:
            pass
        # #endregion
        ok = False
        err = str(exc)
        http_status = None
        final_url = None
        content_type = None
        content_length = None

    if settings.get("id"):
        update_test_result(
            settings_id=settings["id"],
            status="ok" if ok else "error",
        )

    return TestUrlResult(
        ok=ok,
        http_status=http_status,
        error=err,
        final_url=final_url,
        content_type=content_type,
        content_length=content_length,
    )


def _parse_downloaded_file(download: DownloadResult) -> Any:
    file_format = (download.file_format or "").lower()
    if file_format in ("csv",):
        return list(parse_csv(download.path))
    if file_format in ("xlsx", "xlsm"):
        return list(parse_xlsx(download.path))
    if file_format == "xml":
        # XML support is limited to the legacy RRP-style format; map validation
        # issues to a clear 400 so callers can see what is wrong.
        try:
            return parse_xml(download.path)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
    # Fallback: try CSV first
    try:
        return list(parse_csv(download.path))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format for Internal Data: {file_format or 'unknown'}",
        )


def sync_now(project_id: int) -> Dict[str, Any]:
    """Run Internal Data sync: download current source, parse, and persist snapshot."""
    started_at = datetime.utcnow()
    import time as time_module
    import os
    t0 = time_module.perf_counter()
    # get_or_create_settings is called inside _load_source_for_project as well,
    # but we need the settings row here to update sync status.
    settings = get_or_create_settings(project_id)

    if not settings.get("is_enabled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Internal Data is disabled for this project",
        )

    try:
        t_load_start = time_module.perf_counter()
        source_info = _load_source_for_project(project_id)
        download = source_info.download
        settings = source_info.settings
        source_mode = settings.get("source_mode")
        t_load_s = time_module.perf_counter() - t_load_start

        file_size_bytes = None
        try:
            file_size_bytes = os.path.getsize(download.path)
        except Exception:
            file_size_bytes = None

        # Diagnostic logging: mapping configuration
        mapping_json = settings.get("mapping_json") or {}
        use_mapping = _mapping_has_required_fields(mapping_json)
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"[Internal Data sync] project_id={project_id}, settings_id={settings.get('id')}, "
            f"file_format={settings.get('file_format')}, source_mode={source_mode}, "
            f"use_mapping={use_mapping}"
        )
        if use_mapping:
            fields = mapping_json.get("fields", {})
            sku_spec = fields.get("internal_sku", {})
            logger.info(
                f"[Internal Data sync] mapping in effect: internal_sku.key={sku_spec.get('key')}, "
                f"internal_sku.transforms={sku_spec.get('transforms', [])}"
            )

        t_parse_start = time_module.perf_counter()
        if use_mapping:
            # Mapping-based pipeline: stream raw rows and apply mapping.
            fmt = (download.file_format or settings.get("file_format") or "").lower()
            if fmt == "csv":
                raw_iter = iter_rows_csv(download.path)
            elif fmt in ("xlsx", "xlsm"):
                raw_iter = iter_rows_xlsx(download.path)
            elif fmt == "xml":
                raw_iter = iter_items_xml(download.path)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unsupported file format for mapping: {fmt or 'unknown'}",
                )

            # Check on_error option from mapping_json
            options = (mapping_json or {}).get("options", {})
            on_error = options.get("on_error", "fail")
            
            MAX_SAVED_ERRORS = 10000
            rows, row_errors, metrics = apply_mapping_to_rows(
                mapping_json, raw_iter, max_errors=10, on_error="skip", max_saved_errors=MAX_SAVED_ERRORS
            )
            
            rows_total = metrics.get("total_rows", 0)
            rows_imported = metrics.get("rows_imported", 0)
            rows_failed = metrics.get("rows_failed", 0)
            
            # Determine status
            if rows_failed == 0:
                status = "success"
                error_summary = None
            elif rows_imported > 0:
                status = "partial"
                error_summary = f"{rows_failed} rows failed validation"
            else:
                status = "error"
                error_summary = f"All {rows_failed} rows failed validation"
            
            # Prepare errors for DB (limit to MAX_SAVED_ERRORS)
            errors_for_db = row_errors[:MAX_SAVED_ERRORS]
            
            # Preview for response (first 10)
            errors_preview = [
                {
                    "row_index": err["row_index"],
                    "message": err["message"],
                    "source_key": err.get("source_key"),
                }
                for err in row_errors[:10]
            ]
        else:
            # Legacy pipeline.
            rows = _parse_downloaded_file(download)
            rows_total = len(rows)
            rows_imported = len(rows)
            rows_failed = 0
            status = "success"
            error_summary = None
            errors_for_db = []
            errors_preview = []
        t_parse_s = time_module.perf_counter() - t_parse_start

        # Create snapshot and persist rows/errors in a single transaction
        t_snapshot_start = time_module.perf_counter()
        snapshot, row_count = create_snapshot_with_rows(
            project_id,
            settings_row=settings,
            source_mode=source_mode,
            source_url=settings.get("source_url") if source_mode == "url" else None,
            file_storage_key=settings.get("file_storage_key"),
            file_original_name=settings.get("file_original_name"),
            file_format=download.file_format,
            rows=rows,
            rows_total=rows_total if use_mapping else None,
            rows_imported=rows_imported if use_mapping else None,
            rows_failed=rows_failed if use_mapping else None,
            status=status,
            error_summary=error_summary,
            row_errors=errors_for_db if use_mapping else None,
        )
        t_snapshot_s = time_module.perf_counter() - t_snapshot_start
        t_total_s = time_module.perf_counter() - t0
        
        update_sync_result(settings["id"], status=status, error=error_summary)
        finished_at = datetime.utcnow()

        logger.info(
            "[Internal Data sync timings] project_id=%s settings_id=%s source_mode=%s fmt=%s "
            "path=%s file_size_bytes=%s use_mapping=%s rows_total=%s rows_imported=%s rows_failed=%s "
            "t_load_s=%.3f t_parse_s=%.3f t_snapshot_s=%.3f t_total_s=%.3f",
            project_id,
            settings.get("id"),
            source_mode,
            (download.file_format or settings.get("file_format")),
            download.path,
            file_size_bytes,
            use_mapping,
            rows_total if use_mapping else None,
            rows_imported if use_mapping else row_count,
            rows_failed if use_mapping else 0,
            t_load_s,
            t_parse_s,
            t_snapshot_s,
            t_total_s,
        )
        
        # Post-sync hook: Build Internal Data RRP -> rrp_snapshots
        # This ensures price discrepancies report has RRP data after Internal Data sync.
        #
        # Important: allow 'partial' (mapping pipeline may skip bad rows but still import data).
        rrp_sync_stats = None
        effective_rows_imported = rows_imported if use_mapping else row_count
        if status in ("success", "partial") and (effective_rows_imported or 0) > 0:
            try:
                from app.services.internal_data.sync_rrp import sync_internal_data_to_rrp_snapshots

                rrp_sync_stats = sync_internal_data_to_rrp_snapshots(project_id)
                logger.info(
                    "sync_internal_data: post-sync RRP build completed "
                    "project_id=%s rows_inserted=%s rows_found_rrp=%s snapshot_id=%s",
                    project_id,
                    (rrp_sync_stats or {}).get("rows_inserted", 0),
                    (rrp_sync_stats or {}).get("rows_found_rrp", 0),
                    (rrp_sync_stats or {}).get("snapshot_id"),
                )
            except Exception as e:
                # Don't fail the sync if RRP build fails
                logger.warning(
                    f"sync_internal_data: post-sync RRP build failed for project_id={project_id}: {e}",
                    exc_info=True,
                )
        
        return {
            "status": status,
            "snapshot_id": snapshot["id"],
            "project_id": project_id,
            "version": snapshot.get("version"),
            "row_count": row_count,
            "rows_total": rows_total if use_mapping else None,
            "rows_imported": rows_imported if use_mapping else None,
            "rows_updated": snapshot.get("rows_updated", 0) if use_mapping else None,
            "rows_failed": rows_failed if use_mapping else None,
            "errors_preview": errors_preview if use_mapping and errors_preview else None,
            "error": error_summary,
            "rrp_sync": rrp_sync_stats,
            "started_at": started_at,
            "finished_at": finished_at,
        }
    except FileNotFoundError as exc:
        msg = (
            "Uploaded Internal Data file was not found on server. "
            "This usually means INTERNAL_DATA_DIR is not persistent/mounted into the api container."
        )
        logger.error(
            "[Internal Data sync] file not found: project_id=%s error=%s",
            project_id,
            exc,
            exc_info=True,
        )
        if settings.get("id"):
            update_sync_result(settings["id"], status="error", error=msg)
        finished_at = datetime.utcnow()
        return {
            "status": "error",
            "snapshot_id": None,
            "project_id": project_id,
            "version": None,
            "row_count": None,
            "error": msg,
            "started_at": started_at,
            "finished_at": finished_at,
        }
    except PermissionError as exc:
        msg = (
            "Internal Data storage path is not accessible (permission denied). "
            "Please contact administrator (check INTERNAL_DATA_DIR and container volume permissions)."
        )
        logger.error(
            "[Internal Data sync] permission error: project_id=%s error=%s",
            project_id,
            exc,
            exc_info=True,
        )
        if settings.get("id"):
            update_sync_result(settings["id"], status="error", error=msg)
        finished_at = datetime.utcnow()
        return {
            "status": "error",
            "snapshot_id": None,
            "project_id": project_id,
            "version": None,
            "row_count": None,
            "error": msg,
            "started_at": started_at,
            "finished_at": finished_at,
        }
    except HTTPException as exc:
        # Propagate HTTP errors directly but record failure status.
        if settings.get("id"):
            update_sync_result(settings["id"], status="error", error=str(exc.detail))
        raise
    except Exception as exc:  # pragma: no cover - defensive
        if settings.get("id"):
            update_sync_result(settings["id"], status="error", error=str(exc))
        finished_at = datetime.utcnow()
        return {
            "status": "error",
            "snapshot_id": None,
            "project_id": project_id,
            "version": None,
            "row_count": None,
            "error": str(exc),
            "started_at": started_at,
            "finished_at": finished_at,
        }


def _load_source_for_project(project_id: int) -> SourceInfo:
    """Load current Internal Data source file for a project and classify its kind."""
    settings = get_or_create_settings(project_id)

    source_mode = settings.get("source_mode")
    if source_mode not in ("url", "upload"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Internal Data source_mode is not configured",
        )

    if source_mode == "url":
        source_url = settings.get("source_url")
        if not source_url:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="source_url is not configured for URL mode",
            )
        download = download_file_from_url(
            source_url,
            suggested_format=settings.get("file_format"),
        )
    else:
        storage_key = settings.get("file_storage_key")
        if not storage_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No uploaded file configured for upload mode",
            )
        download = get_file_from_storage(storage_key)

    fmt = (download.file_format or settings.get("file_format") or "").lower()
    if fmt in ("xml",):
        kind = "xml"
    elif fmt in ("csv", "xlsx", "xlsm"):
        kind = "table"
    else:
        # Try to treat unknown formats as table-like; if parsing fails later,
        # the caller will return a 400 with a clear message.
        kind = "table"

    return SourceInfo(settings=settings, download=download, kind=kind)


def introspect_source_for_project(project_id: int) -> Dict[str, Any]:
    """Read the configured source and return detected fields without persisting anything.

    The response is unified for all formats:
      - source_fields: [{key,label,kind}]
      - sample_rows: list[dict] using the same keys.
    """
    import json
    import time

    info = _load_source_for_project(project_id)
    settings = info.settings
    download = info.download

    file_format = (download.file_format or settings.get("file_format")) or None

    # agent log: entry
    try:  # pragma: no cover - debug logging
        with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
            _f.write(
                json.dumps(
                    {
                        "sessionId": "debug-session",
                        "runId": "introspect",
                        "hypothesisId": "H1",
                        "location": "service.introspect_source_for_project:entry",
                        "message": "Introspect entry",
                        "data": {
                            "project_id": project_id,
                            "kind": info.kind,
                            "file_format": file_format,
                            "path": download.path,
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass

    # XML: attributes on <item> elements
    if info.kind == "xml":
        try:
            attribute_names, items = introspect_xml(download.path, max_items=20, preview_items=5)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to introspect Internal Data XML: {exc}",
            ) from exc
        if not attribute_names:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No <item> attributes were found in XML source",
            )
        source_fields = [{"key": f"@{name}", "label": name, "kind": "attribute"} for name in attribute_names]
        sample_rows: List[Dict[str, Any]] = []
        for raw in items[:5]:
            sample = {f"@{k}": v for k, v in raw.items()}
            sample_rows.append(sample)
        result = {
            "file_format": file_format,
            "source_fields": source_fields,
            "sample_rows": sample_rows,
        }
        try:  # pragma: no cover - debug logging
            with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
                _f.write(
                    json.dumps(
                        {
                            "sessionId": "debug-session",
                            "runId": "introspect",
                            "hypothesisId": "H2",
                            "location": "service.introspect_source_for_project:xml_exit",
                            "message": "Introspect XML result",
                            "data": {
                                "project_id": project_id,
                                "source_fields_len": len(source_fields),
                                "sample_rows_len": len(sample_rows),
                            },
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
        return result

    # Table-like (CSV/XLSX)
    fmt = (file_format or "").lower()
    try:
        if fmt == "csv":
            headers, rows = introspect_csv(download.path, max_rows=5)
        elif fmt in ("xlsx", "xlsm"):
            headers, rows = introspect_xlsx(download.path, max_rows=5)
        else:
            # Fallback to CSV-style introspection
            headers, rows = introspect_csv(download.path, max_rows=5)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to introspect Internal Data source: {exc}",
        ) from exc

    if not headers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No headers were found in Internal Data source",
        )

    source_fields = [{"key": name, "label": name, "kind": "column"} for name in headers]
    # rows already have keys equal to headers
    sample_rows = rows[:5]

    result = {
        "file_format": file_format,
        "source_fields": source_fields,
        "sample_rows": sample_rows,
    }
    try:  # pragma: no cover - debug logging
        with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
            _f.write(
                json.dumps(
                    {
                        "sessionId": "debug-session",
                        "runId": "introspect",
                        "hypothesisId": "H3",
                        "location": "service.introspect_source_for_project:table_exit",
                        "message": "Introspect table result",
                        "data": {
                            "project_id": project_id,
                            "fmt": fmt,
                            "source_fields_len": len(source_fields),
                            "sample_rows_len": len(sample_rows),
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    return result


#
# Mapping helpers
#


def _apply_transforms(
    value: Any, 
    transforms: List[str], 
    diagnostic: bool = False
) -> Tuple[Any, Optional[str], Optional[List[Any]]]:
    """Apply a sequence of simple transforms to a value.

    Returns (new_value, error_message, diagnostic_steps). On error, new_value is None.
    If diagnostic=True, returns intermediate values after each transform.
    """
    v = value
    diagnostic_steps = [("initial", v)] if diagnostic else None
    
    for name in transforms or []:
        if v is None:
            break
        v_before = v
        if name == "strip":
            if isinstance(v, str):
                v = v.strip()
        elif name == "sku_last_segment":
            if isinstance(v, str):
                parts = [p.strip() for p in v.split("/") if p.strip()]
                v = parts[-1] if parts else v.strip().strip("/")
        elif name == "to_decimal":
            if v is None:
                continue
            s = str(v).replace(" ", "").replace(",", ".")
            if not s:
                v = None
            else:
                try:
                    v = float(s)
                except ValueError:
                    return None, f"cannot parse decimal from '{v}'", diagnostic_steps
        elif name == "to_int":
            if v is None:
                continue
            s = str(v).strip()
            if not s:
                v = None
            else:
                try:
                    v = int(s)
                except ValueError:
                    return None, f"cannot parse int from '{v}'", diagnostic_steps
        # Unknown transforms are ignored for now.
        
        if diagnostic and v_before != v:
            diagnostic_steps.append((name, v))
    
    return v, None, diagnostic_steps


def _mapping_has_required_fields(mapping_json: Dict[str, Any]) -> bool:
    """Return True if mapping_json has internal_sku and rrp with non-empty key."""
    fields = (mapping_json or {}).get("fields") or {}
    for name in ("internal_sku", "rrp"):
        spec = fields.get(name) or {}
        key = (spec.get("key") or "").strip()
        if not key:
            return False
    return True


def apply_mapping_to_rows(
    mapping_json: Dict[str, Any],
    raw_rows: Iterable[Dict[str, Any]],
    max_errors: int = 50,
    on_error: str = "fail",
    max_saved_errors: int = 10000,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """Apply mapping_json to raw rows and return (normalized_rows, row_errors, metrics).

    Args:
        mapping_json: Mapping configuration
        raw_rows: Iterable of raw row dictionaries
        max_errors: Maximum number of errors to collect for preview
        on_error: "fail" (raise on errors) or "skip" (skip invalid rows) - deprecated, always skip now
        max_saved_errors: Maximum number of errors to save to DB

    Returns:
        Tuple of (normalized_rows, row_errors, metrics_dict)
        row_errors: List of dicts with keys: row_index, source_key, raw_row, error_code, message, transforms, trace
    """
    fields = (mapping_json or {}).get("fields") or {}
    normalized: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    sku_spec = fields.get("internal_sku") or {}
    rrp_spec = fields.get("rrp") or {}
    stock_spec = fields.get("stock") or {}
    barcode_spec = fields.get("barcode") or {}

    sku_key = (sku_spec.get("key") or "").strip()
    rrp_key = (rrp_spec.get("key") or "").strip()
    stock_key = (stock_spec.get("key") or "").strip()
    barcode_key = (barcode_spec.get("key") or "").strip()

    sku_transforms = sku_spec.get("transforms") or []
    rrp_transforms = rrp_spec.get("transforms") or []
    stock_transforms = stock_spec.get("transforms") or []
    barcode_transforms = barcode_spec.get("transforms") or []

    # Metrics tracking
    total_rows = 0
    invalid_internal_sku_count = 0
    invalid_rrp_count = 0
    skipped_rows_count = 0  # Count of rows that were skipped (unique rows with errors)
    first_invalid_examples: List[Dict[str, Any]] = []
    
    # Diagnostic: track first 3 internal_sku errors
    sku_error_count = 0
    import logging
    logger = logging.getLogger(__name__)

    for idx, raw in enumerate(raw_rows):
        total_rows += 1
        row_error_messages: List[str] = []
        has_invalid_sku = False
        has_invalid_rrp = False
        error_code = None
        diagnostic_trace = None

        # internal_sku
        raw_sku = raw.get(sku_key) if sku_key else None
        sku_val, err, diagnostic_steps = _apply_transforms(
            raw_sku, sku_transforms, diagnostic=(sku_error_count < 3)
        )
        if err:
            row_error_messages.append(f"internal_sku: {err}")
            has_invalid_sku = True
            error_code = "transform_error"
            diagnostic_trace = diagnostic_steps
        # Validate emptiness only after transforms are applied
        # Empty string or None after transforms means missing/empty
        if sku_val is None or (isinstance(sku_val, str) and not sku_val):
            row_error_messages.append("internal_sku: missing or empty after transforms")
            has_invalid_sku = True
            if not error_code:
                error_code = "missing_required"
            if not diagnostic_trace:
                diagnostic_trace = diagnostic_steps
            # Diagnostic logging for first 3 internal_sku errors
            if sku_error_count < 3:
                available_keys = sorted(list(raw.keys()))
                logger.warning(
                    f"[Internal Data mapping diagnostic] row_index={idx}, "
                    f"source_key={sku_key}, raw_value_repr={repr(raw_sku)}, "
                    f"available_keys={available_keys}, "
                    f"transforms={sku_transforms}, "
                    f"value_after_each_transform={diagnostic_steps}"
                )
                sku_error_count += 1

        # rrp
        raw_rrp = raw.get(rrp_key) if rrp_key else None
        rrp_val, err, _ = _apply_transforms(raw_rrp, rrp_transforms or ["to_decimal"])
        if err:
            row_error_messages.append(f"rrp: {err}")
            has_invalid_rrp = True
            if not error_code:
                error_code = "parse_error"
        if rrp_val is None:
            row_error_messages.append("rrp: missing or not a valid number")
            has_invalid_rrp = True
            if not error_code:
                error_code = "missing_required"

        # stock (optional)
        stock_val = None
        if stock_key:
            raw_stock = raw.get(stock_key)
            stock_val, err, _ = _apply_transforms(raw_stock, stock_transforms or ["to_int"])
            # For optional field we only record parsing errors, not absence.
            if err:
                row_errors.append(f"stock: {err}")

        # barcode (optional)
        barcode_val = None
        if barcode_key:
            raw_barcode = raw.get(barcode_key)
            barcode_val, err, _ = _apply_transforms(raw_barcode, barcode_transforms or ["strip"])
            if err:
                row_errors.append(f"barcode: {err}")

        # Update metrics
        if has_invalid_sku:
            invalid_internal_sku_count += 1
        if has_invalid_rrp:
            invalid_rrp_count += 1
        
        # Collect error examples (first 3)
        if row_error_messages and len(first_invalid_examples) < 3:
            first_invalid_examples.append({
                "row_index": idx,
                "raw_value_repr": repr(raw_sku) if raw_sku is not None else "None",
                "message": "; ".join(row_error_messages),
            })
        
        if row_error_messages:
            # Build structured error
            row_error = {
                "row_index": idx,
                "source_key": sku_key if has_invalid_sku else rrp_key,
                "raw_row": raw,  # Full raw row dict
                "error_code": error_code or "unknown",
                "message": "; ".join(row_error_messages),
                "transforms": sku_transforms if has_invalid_sku else (rrp_transforms or ["to_decimal"]),
                "trace": diagnostic_trace,
            }
            
            # Save error if under limit
            if len(errors) < max_saved_errors:
                errors.append(row_error)
            
            # Update preview (first max_errors for UI)
            if len(first_invalid_examples) < max_errors:
                pass  # Already added above
            
            skipped_rows_count += 1
            continue  # Skip this row, continue processing

        attrs: Dict[str, Any] = {}
        if stock_val is not None:
            attrs["stock"] = stock_val
        if barcode_val:
            attrs["barcode"] = barcode_val

        normalized.append(
            {
                "internal_sku": str(sku_val),
                "name": None,
                "lifecycle_status": None,
                "attributes": attrs or None,
                "identifiers": [],
                "price": {"currency": "RUB", "rrp": float(rrp_val), "rrp_promo": None, "extra": None},
                "cost": None,
            }
        )

    # Build metrics
    rows_failed = skipped_rows_count
    rows_imported = len(normalized)
    
    metrics = {
        "total_rows": total_rows,
        "rows_imported": rows_imported,
        "rows_failed": rows_failed,
        "invalid_internal_sku_count": invalid_internal_sku_count,
        "invalid_rrp_count": invalid_rrp_count,
        "first_invalid_examples": first_invalid_examples,
    }
    
    # Log aggregated metrics
    logger.info(
        f"[Internal Data mapping metrics] total_rows={total_rows}, "
        f"rows_imported={rows_imported}, rows_failed={rows_failed}, "
        f"invalid_internal_sku_count={invalid_internal_sku_count}, "
        f"invalid_rrp_count={invalid_rrp_count}"
    )

    return normalized, errors, metrics


def validate_mapping_for_project(project_id: int, mapping_json: Dict[str, Any]) -> Dict[str, Any]:
    """Validate mapping_json against a small sample of the current source."""
    mapping_json = mapping_json or {}
    if not _mapping_has_required_fields(mapping_json):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mapping_json.fields.internal_sku and mapping_json.fields.rrp with non-empty key are required",
        )

    preview_spec = introspect_source_for_project(project_id)
    sample_rows = preview_spec.get("sample_rows") or []

    normalized, errors, _ = apply_mapping_to_rows(mapping_json, sample_rows, max_errors=50)
    return {
        "preview_rows": normalized,
        "errors": errors,
    }


def _normalize_field_name(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _suggest_mapping_from_fields(
    kind: str,
    fields: List[str],
    existing_mapping: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Build or extend mapping_json based on detected fields and synonyms."""
    existing_mapping = existing_mapping or {}

    synonyms = {
        "internal_sku": ["article", "sku", "vendorcode", "internal_sku", "articul"],
        "rrp": ["price", "rrp", "pricerrp", "price_rrp"],
        "stock": ["stock", "qty", "quantity", "amount"],
        "barcode": ["barcode", "ean", "ean13"],
        "cost": ["cost", "cogs", "sebestoimost", " себестоимость"],
    }

    normalized_fields = {field: _normalize_field_name(field) for field in fields}

    mapping: Dict[str, Any] = dict(existing_mapping)

    for target_field, candidates in synonyms.items():
        if target_field in mapping and mapping.get(target_field):
            # Respect existing mapping for this field
            continue

        candidate_norms = {_normalize_field_name(c) for c in candidates}
        chosen_source: Optional[str] = None
        for original, norm in normalized_fields.items():
            if norm in candidate_norms:
                chosen_source = original
                break

        if not chosen_source:
            continue

        entry: Dict[str, Any] = {
            "source": "attribute" if kind == "xml" else "column",
            "name": chosen_source,
        }
        # No default transforms for internal_sku - only apply if explicitly specified in mapping_json

        mapping[target_field] = entry

    return mapping, fields


def suggest_mapping_for_project(project_id: int, introspection: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a suggested mapping_json for the current project source."""
    settings = get_or_create_settings(project_id)
    existing_mapping = settings.get("mapping_json") or {}

    if introspection is None:
        introspection = introspect_source_for_project(project_id)

    kind = introspection.get("kind") or "table"
    if kind == "xml":
        fields = introspection.get("attribute_names") or []
    else:
        fields = introspection.get("headers") or []

    if not fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields were detected for mapping suggestion",
        )

    mapping, available_fields = _suggest_mapping_from_fields(
        kind=kind,
        fields=list(fields),
        existing_mapping=existing_mapping or None,
    )

    return {
        "kind": kind,
        "mapping_json": mapping,
        "available_fields": available_fields,
    }

    source_mode = settings.get("source_mode")
    if source_mode not in ("url", "upload"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Internal Data source_mode is not configured",
        )

    try:
        if source_mode == "url":
            if not settings.get("source_url"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="source_url is not configured for URL mode",
                )
            download = download_file_from_url(
                settings["source_url"],
                suggested_format=settings.get("file_format"),
            )
        else:
            storage_key = settings.get("file_storage_key")
            if not storage_key:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No uploaded file configured for upload mode",
                )
            download = get_file_from_storage(storage_key)

        rows = _parse_downloaded_file(download)
        snapshot, row_count = create_snapshot_with_rows(
            project_id,
            settings_row=settings,
            source_mode=source_mode,
            source_url=settings.get("source_url") if source_mode == "url" else None,
            file_storage_key=settings.get("file_storage_key"),
            file_original_name=settings.get("file_original_name"),
            file_format=download.file_format,
            rows=rows,
        )
        update_sync_result(settings["id"], status="success", error=None)
        finished_at = datetime.utcnow()
        return {
            "status": "success",
            "snapshot_id": snapshot["id"],
            "project_id": project_id,
            "version": snapshot.get("version"),
            "row_count": row_count,
            "rows_updated": snapshot.get("rows_updated", 0),
            "error": None,
            "started_at": started_at,
            "finished_at": finished_at,
        }
    except HTTPException:
        # Propagate HTTP errors directly
        update_sync_result(settings["id"], status="error", error="sync_failed")
        raise
    except Exception as exc:  # pragma: no cover - defensive
        update_sync_result(settings["id"], status="error", error=str(exc))
        finished_at = datetime.utcnow()
        return {
            "status": "error",
            "snapshot_id": None,
            "project_id": project_id,
            "version": None,
            "row_count": None,
            "error": str(exc),
            "started_at": started_at,
            "finished_at": finished_at,
        }

