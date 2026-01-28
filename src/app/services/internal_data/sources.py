"""Source retrieval for Internal Data with SSRF protections."""

from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from typing import Optional

import httpx

from app.settings import INTERNAL_DATA_DIR


MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
HTTP_TIMEOUT_SECONDS = 10.0
TEST_URL_TIMEOUT_SECONDS = 15.0  # Longer timeout for URL testing
MAX_TEST_DOWNLOAD_BYTES = 1024  # Only download first 1KB for testing


@dataclass
class DownloadResult:
    path: str
    file_format: Optional[str]
    url: str
    content_type: Optional[str]
    content_length: Optional[int]


def _ensure_base_dir() -> None:
    os.makedirs(INTERNAL_DATA_DIR, exist_ok=True)


def _is_private_ip(ip: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local


def _resolve_and_validate_host(host: str) -> None:
    if host.lower() in {"localhost", "127.0.0.1"}:
        raise ValueError("Localhost is not allowed for Internal Data URLs")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise ValueError(f"Failed to resolve host: {exc}") from exc
    for family, _, _, _, sockaddr in infos:
        if family in (socket.AF_INET, socket.AF_INET6):
            ip = sockaddr[0]
            if _is_private_ip(ip):
                raise ValueError("Private or loopback IP addresses are not allowed for Internal Data URLs")


def _validate_url_for_ssrf(url: str) -> None:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("https",):
        raise ValueError("Only https URLs are allowed for Internal Data source")
    if not parsed.netloc:
        raise ValueError("Invalid URL")
    host = parsed.hostname
    if not host:
        raise ValueError("Invalid URL host")
    _resolve_and_validate_host(host)


def download_file_from_url(url: str, *, suggested_format: Optional[str] = None) -> DownloadResult:
    """Download file from URL with SSRF protections and limits."""
    # #region agent log
    try:
        import json, time
        with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H1","location":"sources.py:69","message":"download_file_from_url called","data":{"url":url,"timeout":HTTP_TIMEOUT_SECONDS},"timestamp":int(time.time()*1000)})+"\n")
    except Exception:
        pass
    # #endregion
    _validate_url_for_ssrf(url)
    _ensure_base_dir()

    headers = {"User-Agent": "EcomCore-InternalData/1.0"}
    timeout = httpx.Timeout(HTTP_TIMEOUT_SECONDS, connect=HTTP_TIMEOUT_SECONDS)

    with httpx.stream("GET", url, headers=headers, timeout=timeout, follow_redirects=True) as resp:
        resp.raise_for_status()

        final_url = str(resp.url)
        content_type = resp.headers.get("content-type")
        content_length_header = resp.headers.get("content-length")
        content_length = int(content_length_header) if content_length_header and content_length_header.isdigit() else None

        if content_length is not None and content_length > MAX_DOWNLOAD_BYTES:
            raise ValueError("File is too large for Internal Data (size limit exceeded)")

        from datetime import datetime
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        ext = suggested_format or ""
        if not ext and final_url:
            from urllib.parse import urlparse

            path = urlparse(final_url).path
            _, dot, suffix = path.rpartition(".")
            if dot and suffix:
                ext = suffix.lower()

        if ext:
            filename = f"url_internal_{ts}.{ext}"
        else:
            filename = f"url_internal_{ts}"

        dest_path = os.path.join(INTERNAL_DATA_DIR, filename)
        total = 0
        # #region agent log
        try:
            import json, time
            with open("d:\\Work\\EcomCore\\.cursor\\debug.log", "a", encoding="utf-8") as _f:
                _f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H1","location":"sources.py:106","message":"Starting file download","data":{"dest_path":dest_path},"timestamp":int(time.time()*1000)})+"\n")
        except Exception:
            pass
        # #endregion
        with open(dest_path, "wb") as f:
            chunk_count = 0
            for chunk in resp.iter_bytes(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                chunk_count += 1
                if total > MAX_DOWNLOAD_BYTES:
                    raise ValueError("File is too large for Internal Data (size limit exceeded)")
                f.write(chunk)

    file_format = (suggested_format or "").lower() or None
    if not file_format and filename.rpartition(".")[1]:
        file_format = filename.rpartition(".")[2].lower()

    return DownloadResult(
        path=dest_path,
        file_format=file_format,
        url=final_url,
        content_type=content_type,
        content_length=content_length,
    )


def test_url_reachability(url: str) -> tuple[bool, Optional[str], Optional[int], Optional[str], Optional[int], Optional[str]]:
    """Test URL reachability without downloading the entire file.
    
    Returns:
        Tuple of (ok, error_message, http_status, content_type, content_length, final_url)
    """
    _validate_url_for_ssrf(url)
    
    headers = {"User-Agent": "EcomCore-InternalData/1.0"}
    # Use longer timeout for testing, but separate connect and read timeouts
    timeout = httpx.Timeout(TEST_URL_TIMEOUT_SECONDS, connect=5.0, read=TEST_URL_TIMEOUT_SECONDS)
    
    try:
        # Try HEAD first (fastest - no body download)
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.head(url, headers=headers)
                resp.raise_for_status()
                
                final_url = str(resp.url)
                content_type = resp.headers.get("content-type")
                content_length_header = resp.headers.get("content-length")
                content_length = int(content_length_header) if content_length_header and content_length_header.isdigit() else None
                
                return (True, None, resp.status_code, content_type, content_length, final_url)
        except (httpx.HTTPStatusError, httpx.RequestError):
            # HEAD not supported or failed, fallback to GET with minimal read
            # Use streamed GET but only read first few bytes to verify reachability
            with httpx.stream("GET", url, headers=headers, timeout=timeout, follow_redirects=True) as resp:
                resp.raise_for_status()
                
                final_url = str(resp.url)
                content_type = resp.headers.get("content-type")
                content_length_header = resp.headers.get("content-length")
                content_length = int(content_length_header) if content_length_header and content_length_header.isdigit() else None
                
                # Read only first few bytes to verify the connection works
                # This is much faster than downloading the entire file
                bytes_read = 0
                for chunk in resp.iter_bytes(chunk_size=1024):
                    bytes_read += len(chunk)
                    if bytes_read >= MAX_TEST_DOWNLOAD_BYTES:
                        break
                
                return (True, None, resp.status_code, content_type, content_length, final_url)
    except httpx.TimeoutException as exc:
        return (False, f"Timeout connecting to URL: {exc}", None, None, None, None)
    except httpx.HTTPStatusError as exc:
        return (False, f"HTTP {exc.response.status_code}: {exc}", exc.response.status_code, None, None, None)
    except Exception as exc:
        return (False, str(exc), None, None, None, None)


def get_file_from_storage(storage_key: str) -> DownloadResult:
    """Return local file path for previously uploaded Internal Data."""
    _ensure_base_dir()
    path = os.path.join(INTERNAL_DATA_DIR, storage_key)
    if not os.path.isfile(path):
        raise FileNotFoundError("Internal Data file not found on server")

    _, dot, suffix = storage_key.rpartition(".")
    file_format = suffix.lower() if dot and suffix else None
    return DownloadResult(
        path=path,
        file_format=file_format,
        url=f"file://{storage_key}",
        content_type=None,
        content_length=None,
    )

