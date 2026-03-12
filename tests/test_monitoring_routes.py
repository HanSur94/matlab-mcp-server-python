"""Tests for monitoring HTTP routes."""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import pytest


def _make_mock_state():
    """Create a mock server state with collector."""
    from matlab_mcp.monitoring.collector import MetricsCollector
    from matlab_mcp.config import load_config

    config = load_config(None)
    collector = MetricsCollector(config)

    pool = MagicMock()
    pool.get_status.return_value = {
        "total": 4, "available": 2, "busy": 2, "max": 10,
    }
    pool._pool_config = MagicMock()
    pool._pool_config.queue_max_size = 50

    tracker = MagicMock()
    tracker.list_jobs.return_value = []

    sessions = MagicMock()
    sessions.session_count = 2

    collector.pool = pool
    collector.tracker = tracker
    collector.sessions = sessions

    state = MagicMock()
    state.collector = collector
    state.pool = pool
    state.tracker = tracker
    state.sessions = sessions
    state.config = config

    return state


class TestHealthEndpoint:
    def test_health_response_structure(self):
        """health_handler returns proper JSON structure."""
        from matlab_mcp.monitoring.routes import build_health_response

        state = _make_mock_state()
        response = build_health_response(state)
        assert "status" in response
        assert "uptime_seconds" in response
        assert "engines" in response

    def test_health_status_code_healthy(self):
        """Returns 200 for healthy status."""
        from matlab_mcp.monitoring.routes import get_health_status_code, build_health_response

        state = _make_mock_state()
        response = build_health_response(state)
        assert get_health_status_code(response) == 200

    def test_health_status_code_degraded(self):
        """Returns 200 for degraded status."""
        from matlab_mcp.monitoring.routes import get_health_status_code

        assert get_health_status_code({"status": "degraded"}) == 200

    def test_health_status_code_unhealthy(self):
        """Returns 503 for unhealthy status."""
        from matlab_mcp.monitoring.routes import get_health_status_code

        assert get_health_status_code({"status": "unhealthy"}) == 503


class TestMetricsEndpoint:
    def test_metrics_response_structure(self):
        """metrics_handler returns proper JSON structure."""
        from matlab_mcp.monitoring.routes import build_metrics_response

        state = _make_mock_state()
        response = build_metrics_response(state)
        assert "timestamp" in response
        assert "pool" in response
        assert "jobs" in response
        assert "sessions" in response
        assert "errors" in response
        assert "system" in response
        assert response["pool"]["total"] == 4
