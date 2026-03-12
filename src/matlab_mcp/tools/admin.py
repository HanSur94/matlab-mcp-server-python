"""Admin MCP tool implementations.

Provides:
- get_pool_status_impl — delegate to pool.get_status()
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def get_pool_status_impl(pool: Any) -> dict:
    """Return the current status of the engine pool.

    Parameters
    ----------
    pool:
        An :class:`~matlab_mcp.pool.manager.EnginePoolManager` instance
        (or any object with a ``get_status()`` method).

    Returns
    -------
    dict
        Status summary with ``total``, ``available``, ``busy``, and ``max`` keys.
    """
    return pool.get_status()
