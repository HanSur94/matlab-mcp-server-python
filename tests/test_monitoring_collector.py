"""Tests for MetricsCollector."""
from __future__ import annotations
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from matlab_mcp.config import load_config

def _make_config():
    config = load_config(None)
    config.monitoring.enabled = True
    config.monitoring.sample_interval = 1
    return config

def _make_mock_pool():
    pool = MagicMock()
    pool.get_status.return_value = {"total": 4, "available": 2, "busy": 2, "max": 10}
    return pool

def _make_mock_tracker():
    tracker = MagicMock()
    tracker.list_jobs.return_value = []
    return tracker

def _make_mock_sessions():
    sessions = MagicMock()
    sessions.session_count = 2
    return sessions


class TestCollectorInit:
    def test_collector_creation(self):
        from matlab_mcp.monitoring.collector import MetricsCollector
        collector = MetricsCollector(_make_config())
        assert collector.start_time <= time.time()
        assert collector.start_time > 0

    def test_collector_counters_start_at_zero(self):
        from matlab_mcp.monitoring.collector import MetricsCollector
        collector = MetricsCollector(_make_config())
        snapshot = collector.get_counters()
        assert snapshot["completed_total"] == 0
        assert snapshot["failed_total"] == 0
        assert snapshot["cancelled_total"] == 0
        assert snapshot["total_created_sessions"] == 0
        assert snapshot["error_total"] == 0
        assert snapshot["blocked_attempts"] == 0
        assert snapshot["health_check_failures"] == 0


class TestCollectorEvents:
    def test_record_event_increments_counters(self):
        from matlab_mcp.monitoring.collector import MetricsCollector
        collector = MetricsCollector(_make_config())
        collector.record_event("job_completed", {"job_id": "j1", "execution_ms": 500})
        collector.record_event("job_completed", {"job_id": "j2", "execution_ms": 1500})
        collector.record_event("job_failed", {"job_id": "j3", "error": "err"})
        collector.record_event("session_created", {"session_id_short": "abc12345"})
        collector.record_event("blocked_function", {"function": "system"})
        collector.record_event("health_check_fail", {"engine_id": "e1"})
        c = collector.get_counters()
        assert c["completed_total"] == 2
        assert c["failed_total"] == 1
        assert c["total_created_sessions"] == 1
        assert c["blocked_attempts"] == 1
        assert c["health_check_failures"] == 1
        assert c["error_total"] == 3  # failed + blocked + health_check

    def test_execution_ring_buffer(self):
        from matlab_mcp.monitoring.collector import MetricsCollector
        collector = MetricsCollector(_make_config())
        for i in range(150):
            collector.record_event("job_completed", {"job_id": f"j{i}", "execution_ms": i * 10})
        stats = collector.get_execution_stats()
        assert stats["avg_execution_ms"] > 0
        assert stats["p95_execution_ms"] >= stats["avg_execution_ms"]


class TestCollectorSampling:
    async def test_sample_metrics(self, tmp_path):
        from matlab_mcp.monitoring.collector import MetricsCollector
        from matlab_mcp.monitoring.store import MetricsStore
        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        collector = MetricsCollector(_make_config())
        collector.store = store
        collector.pool = _make_mock_pool()
        collector.tracker = _make_mock_tracker()
        collector.sessions = _make_mock_sessions()
        await collector.sample_once()
        latest = await store.get_latest()
        assert latest["pool.total_engines"] == 4
        assert latest["pool.available_engines"] == 2
        assert latest["pool.busy_engines"] == 2
        assert latest["pool.utilization_pct"] == 50.0
        assert latest["sessions.active_count"] == 2
        assert "system.uptime_seconds" in latest
        await store.close()

    async def test_sample_with_psutil_unavailable(self, tmp_path):
        from matlab_mcp.monitoring.collector import MetricsCollector
        from matlab_mcp.monitoring.store import MetricsStore
        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        collector = MetricsCollector(_make_config())
        collector.store = store
        collector.pool = _make_mock_pool()
        collector.tracker = _make_mock_tracker()
        collector.sessions = _make_mock_sessions()
        with patch("matlab_mcp.monitoring.collector._get_system_metrics", return_value=(None, None)):
            await collector.sample_once()
        latest = await store.get_latest()
        assert latest.get("system.memory_mb") is None
        assert latest.get("system.cpu_percent") is None
        await store.close()

    def test_get_current_snapshot(self):
        from matlab_mcp.monitoring.collector import MetricsCollector
        collector = MetricsCollector(_make_config())
        collector.pool = _make_mock_pool()
        collector.tracker = _make_mock_tracker()
        collector.sessions = _make_mock_sessions()
        snapshot = collector.get_current_snapshot()
        assert "timestamp" in snapshot
        assert snapshot["pool"]["total"] == 4
        assert snapshot["jobs"]["active"] == 0
        assert snapshot["jobs"]["completed_total"] == 0
        assert snapshot["sessions"]["active"] == 2
        assert snapshot["sessions"]["total_created"] == 0
        assert snapshot["errors"]["total"] == 0
        assert "system" in snapshot
        assert "counters" not in snapshot  # non-spec key must not be present
