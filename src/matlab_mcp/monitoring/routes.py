"""HTTP route handlers for /health and /metrics endpoints."""
from __future__ import annotations

from typing import Any

from matlab_mcp.monitoring.health import evaluate_health


def build_health_response(state: Any) -> dict[str, Any]:
    """Build the ``/health`` JSON response from server state.

    Delegates to :func:`evaluate_health` using the collector
    attached to *state*.
    """
    return evaluate_health(state.collector)


def get_health_status_code(response: dict[str, Any]) -> int:
    """Map a health response to an HTTP status code.

    Returns 503 (Service Unavailable) when the server is unhealthy,
    200 (OK) otherwise (healthy or degraded).
    """
    return 503 if response.get("status") == "unhealthy" else 200


def build_metrics_response(state: Any) -> dict[str, Any]:
    """Build the ``/metrics`` JSON response from server state.

    Returns a live snapshot of pool, job, session, error, and system
    metrics without hitting the SQLite store.
    """
    return state.collector.get_current_snapshot()
