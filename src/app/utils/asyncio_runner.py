"""Safe async coroutine runner for sync contexts (e.g., Celery tasks).

This module provides a helper to safely run async coroutines from sync code,
handling cases where an event loop may already be running.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Coroutine, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def _run_in_thread(coro: Coroutine[Any, Any, T]) -> T:
    """Run coroutine in a new thread with a fresh event loop.
    
    This is used when an event loop is already running in the current thread.
    """
    def _run():
        try:
            # Set event loop policy explicitly for better compatibility with httpx
            # This helps with httpx.AsyncClient in thread pools
            import sys
            if sys.platform == "win32":
                # On Windows, use ProactorEventLoopPolicy for better async I/O
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            else:
                # On Unix, use default policy
                asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
            
            # Create new event loop in this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                result = loop.run_until_complete(coro)
                return result
            finally:
                # Clean up event loop
                loop.close()
                asyncio.set_event_loop(None)
        except Exception as e:
            raise

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run)
        # Add timeout to prevent infinite hang (e.g., 1 hour max for long-running ingestion)
        result = future.result(timeout=3600)
        return result


def run_async_safe(
    coro: Coroutine[Any, Any, T],
    context_info: dict[str, Any] | None = None,
    force_thread: bool = False,
) -> T:
    """Safely run an async coroutine from a sync context.
    
    This function handles two cases:
    1. No event loop is running -> uses asyncio.run() directly (unless force_thread=True)
    2. Event loop is already running -> runs coroutine in a separate thread
       with a new event loop
    
    Args:
        coro: The async coroutine to run
        context_info: Optional dict with context info for logging (e.g., run_id, job_code)
        force_thread: If True, always use thread pool (useful for Celery prefork workers)
    
    Returns:
        The result of the coroutine
    
    Raises:
        Any exception raised by the coroutine
    """
    context_info = context_info or {}
    
    # For Celery prefork workers, always use thread pool to avoid race conditions
    # where loop might be created between check and asyncio.run() call
    if force_thread:
        logger.info(
            f"run_async_safe: force_thread=True, "
            f"using thread pool (context: {context_info})"
        )
        return _run_in_thread(coro)
    
    try:
        # Try to get the current event loop
        loop = asyncio.get_running_loop()
        detected_running_loop = True
    except RuntimeError as e:
        # No event loop is running
        detected_running_loop = False
        loop = None
    
    if detected_running_loop:
        logger.info(
            f"run_async_safe: detected_running_loop=True, "
            f"using thread pool (context: {context_info})"
        )
        return _run_in_thread(coro)
    else:
        logger.info(
            f"run_async_safe: detected_running_loop=False, "
            f"using asyncio.run() (context: {context_info})"
        )
        try:
            result = asyncio.run(coro)
            return result
        except RuntimeError as e:
            # If asyncio.run() fails with "cannot be called from a running event loop",
            # it means loop was created between check and call - fallback to thread pool
            error_msg = str(e)
            if "cannot be called from a running event loop" in error_msg:
                logger.warning(
                    f"run_async_safe: asyncio.run() failed (loop created after check), "
                    f"falling back to thread pool (context: {context_info})"
                )
                return _run_in_thread(coro)
            raise
