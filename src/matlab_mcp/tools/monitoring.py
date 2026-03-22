"""Server monitoring MCP tool implementations.

Provides:
- get_server_metrics_impl — return a snapshot of current server metrics
- get_server_health_impl  — evaluate and return server health status
- get_error_log_impl      — retrieve recent error-class events
"""
from __future__ import annotations

from typing import Any

from matlab_mcp.monitoring.health import evaluate_health
from matlab_mcp.monitoring.store import ERROR_EVENT_TYPES


async def get_server_metrics_impl(state: Any) -> dict[str, Any]:
    """Return a snapshot of current server metrics.

    Parameters
    ----------
    state:
        Server state object with a ``collector`` attribute
        (a :class:`~matlab_mcp.monitoring.collector.MetricsCollector` or ``None``).

    Returns
    -------
    dict
        Metrics snapshot dict, or an error dict if monitoring is disabled.
    """
    if not state.collector:
        return {"error": "Monitoring is disabled"}
    return state.collector.get_current_snapshot()


async def get_server_health_impl(state: Any) -> dict[str, Any]:
    """Evaluate and return the current server health status.

    Parameters
    ----------
    state:
        Server state object with a ``collector`` attribute.

    Returns
    -------
    dict
        Health evaluation dict produced by
        :func:`~matlab_mcp.monitoring.health.evaluate_health`,
        or an error dict if monitoring is disabled.
    """
    if not state.collector:
        return {"error": "Monitoring is disabled"}
    return evaluate_health(state.collector)


async def get_error_log_impl(state: Any, limit: int = 20) -> dict[str, Any]:
    """Retrieve recent error-class events from the monitoring store.

    Only returns events of error types: ``job_failed``, ``blocked_function``,
    ``engine_crash``, and ``health_check_fail``.

    Parameters
    ----------
    state:
        Server state object with a ``collector`` attribute.
    limit:
        Maximum number of error events to return.

    Returns
    -------
    dict
        Dict with ``events`` list and ``total_errors_24h`` count,
        or an error dict if monitoring is disabled.
    """
    if not state.collector:
        return {"error": "Monitoring is disabled"}

    store = state.collector.store
    if not store:
        return {"events": [], "total_errors_24h": 0}

    events = await store.get_events(
        limit=limit,
        event_types=list(ERROR_EVENT_TYPES),
    )

    # Count errors in last 24h using aggregates (proper time window)
    aggregates = await store.get_aggregates(hours=24)
    error_rate = aggregates.get("error_rate_per_minute", 0)
    total_errors_24h = int(error_rate * 60 * 24)

    return {
        "events": events,
        "total_errors_24h": total_errors_24h,
    }
