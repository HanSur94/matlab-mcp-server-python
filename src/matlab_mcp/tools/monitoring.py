"""MCP tool implementations for server monitoring."""
from __future__ import annotations

from typing import Any

from matlab_mcp.monitoring.health import evaluate_health
from matlab_mcp.monitoring.store import ERROR_EVENT_TYPES


async def get_server_metrics_impl(state: Any) -> dict[str, Any]:
    """Implementation for get_server_metrics MCP tool."""
    if not state.collector:
        return {"error": "Monitoring is disabled"}
    return state.collector.get_current_snapshot()


async def get_server_health_impl(state: Any) -> dict[str, Any]:
    """Implementation for get_server_health MCP tool."""
    if not state.collector:
        return {"error": "Monitoring is disabled"}
    return evaluate_health(state.collector)


async def get_error_log_impl(state: Any, limit: int = 20) -> dict[str, Any]:
    """Implementation for get_error_log MCP tool.

    Returns only error-class events: job_failed, blocked_function,
    engine_crash, health_check_fail.
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
