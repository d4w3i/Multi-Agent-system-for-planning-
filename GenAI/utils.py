"""
=============================================================================
UTILS.PY - Shared Utilities for the GenAI Package
=============================================================================

This module contains small helpers shared across multiple modules in the
GenAI package. Keeping them here avoids duplication and keeps each
module focused on its primary responsibility.

CONTENTS:

    run_async_safely(coro)
        Run an async coroutine safely from a synchronous call site,
        regardless of whether an event loop is already running.

=============================================================================
"""

import asyncio
import concurrent.futures
from typing import Any, Coroutine, TypeVar

_T = TypeVar("_T")


def run_async_safely(coro: Coroutine[Any, Any, _T]) -> _T:
    """
    Run an async coroutine from a synchronous context.

    Handles two situations transparently:

    1. No running event loop (typical CLI / script usage):
       Calls ``asyncio.run()`` directly.

    2. Already inside a running event loop (e.g. Jupyter notebooks,
       or when called from another async framework):
       Offloads execution to a fresh ``ThreadPoolExecutor`` thread that
       owns its own event loop, then blocks until it finishes.

    Args:
        coro: Any awaitable coroutine to run.

    Returns:
        Whatever the coroutine returns.

    Raises:
        Re-raises any exception raised by the coroutine.

    Example:
        result = run_async_safely(my_async_function(arg1, arg2))
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We are inside an existing event loop — run in a separate thread.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()

    return asyncio.run(coro)
