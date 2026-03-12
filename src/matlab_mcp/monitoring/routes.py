"""HTTP route handlers for /health and /metrics endpoints."""
from __future__ import annotations

from typing import Any

from matlab_mcp.monitoring.health import evaluate_health


def build_health_response(state: Any) -> dict[str, Any]:
    """Build the /health JSON response from server state."""
    return evaluate_health(state.collector)


def get_health_status_code(response: dict[str, Any]) -> int:
    """Return HTTP status code based on health status."""
    return 503 if response.get("status") == "unhealthy" else 200


def build_metrics_response(state: Any) -> dict[str, Any]:
    """Build the /metrics JSON response from server state."""
    return state.collector.get_current_snapshot()
