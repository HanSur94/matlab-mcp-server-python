"""Tests for MCP monitoring tool implementations."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_mock_state():
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
    collector.store = AsyncMock()
    collector.store.get_events = AsyncMock(return_value=[])
    collector.store.get_aggregates = AsyncMock(return_value={
        "job_success_rate": 1.0, "avg_execution_ms": 0.0,
        "p95_execution_ms": 0.0, "error_rate_per_minute": 0.0,
    })

    return MagicMock(
        collector=collector,
        pool=pool,
        tracker=tracker,
        sessions=sessions,
        config=config,
    )


class TestGetServerMetrics:
    @pytest.mark.asyncio
    async def test_returns_metrics(self):
        from matlab_mcp.tools.monitoring import get_server_metrics_impl

        state = _make_mock_state()
        result = await get_server_metrics_impl(state)
        assert result["pool"]["total"] == 4
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_disabled_returns_error(self):
        from matlab_mcp.tools.monitoring import get_server_metrics_impl

        state = _make_mock_state()
        state.collector = None
        result = await get_server_metrics_impl(state)
        assert "error" in result


class TestGetServerHealth:
    @pytest.mark.asyncio
    async def test_returns_health(self):
        from matlab_mcp.tools.monitoring import get_server_health_impl

        state = _make_mock_state()
        result = await get_server_health_impl(state)
        assert result["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_disabled_returns_error(self):
        from matlab_mcp.tools.monitoring import get_server_health_impl

        state = _make_mock_state()
        state.collector = None
        result = await get_server_health_impl(state)
        assert "error" in result


class TestGetErrorLog:
    @pytest.mark.asyncio
    async def test_returns_events(self):
        from matlab_mcp.tools.monitoring import get_error_log_impl

        state = _make_mock_state()
        state.collector.store.get_events = AsyncMock(return_value=[
            {"timestamp": "2026-01-01T00:00:00Z", "event_type": "job_failed", "details": "{}"},
        ])

        result = await get_error_log_impl(state, limit=20)
        assert "events" in result
        assert len(result["events"]) == 1

    @pytest.mark.asyncio
    async def test_disabled_returns_error(self):
        from matlab_mcp.tools.monitoring import get_error_log_impl

        state = _make_mock_state()
        state.collector = None
        result = await get_error_log_impl(state, limit=20)
        assert "error" in result
