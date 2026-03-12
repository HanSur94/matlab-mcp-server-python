"""Tests for health evaluation."""
from __future__ import annotations
import time
from unittest.mock import MagicMock
import pytest

def _make_collector(*, start_time=None, error_total=0, pool_status=None, active_jobs=0, active_sessions=0):
    from matlab_mcp.monitoring.collector import MetricsCollector
    from matlab_mcp.config import load_config
    from matlab_mcp.jobs.models import JobStatus

    config = load_config(None)
    collector = MetricsCollector(config)
    if start_time:
        collector.start_time = start_time
    collector._counters["error_total"] = error_total

    pool = MagicMock()
    pool.get_status.return_value = pool_status or {"total": 4, "available": 2, "busy": 2, "max": 10}
    collector.pool = pool

    tracker = MagicMock()
    jobs = [MagicMock() for _ in range(active_jobs)]
    for j in jobs:
        j.status = JobStatus.RUNNING  # Use real enum, not MagicMock
    tracker.list_jobs.return_value = jobs
    collector.tracker = tracker

    sessions = MagicMock()
    sessions.session_count = active_sessions
    collector.sessions = sessions
    return collector


class TestHealthEvaluation:
    def test_healthy_status(self):
        from matlab_mcp.monitoring.health import evaluate_health
        collector = _make_collector(start_time=time.time() - 3600, pool_status={"total": 4, "available": 2, "busy": 2, "max": 10})
        result = evaluate_health(collector)
        assert result["status"] == "healthy"
        assert result["issues"] == []
        assert result["uptime_seconds"] >= 3599

    def test_degraded_high_utilization(self):
        from matlab_mcp.monitoring.health import evaluate_health
        # 19/20 busy = 95% utilization, but not at max capacity (1 still available)
        collector = _make_collector(pool_status={"total": 20, "available": 1, "busy": 19, "max": 20})
        result = evaluate_health(collector)
        assert result["status"] == "degraded"
        assert any("utilization" in i.lower() for i in result["issues"])

    def test_unhealthy_all_busy_at_max(self):
        from matlab_mcp.monitoring.health import evaluate_health
        collector = _make_collector(pool_status={"total": 10, "available": 0, "busy": 10, "max": 10})
        result = evaluate_health(collector)
        assert result["status"] == "unhealthy"
        assert any("max capacity" in i.lower() for i in result["issues"])

    def test_degraded_high_error_rate(self):
        from matlab_mcp.monitoring.health import evaluate_health
        collector = _make_collector(start_time=time.time() - 60, error_total=10)  # 10 errors/min
        result = evaluate_health(collector)
        assert result["status"] == "degraded"
        assert any("error rate" in i.lower() for i in result["issues"])

    def test_unhealthy_no_engines(self):
        from matlab_mcp.monitoring.health import evaluate_health
        collector = _make_collector(pool_status={"total": 0, "available": 0, "busy": 0, "max": 0})
        result = evaluate_health(collector)
        assert result["status"] == "unhealthy"

    def test_response_shape(self):
        from matlab_mcp.monitoring.health import evaluate_health
        collector = _make_collector(active_jobs=3, active_sessions=2)
        result = evaluate_health(collector)
        assert "status" in result
        assert "uptime_seconds" in result
        assert "issues" in result
        assert "engines" in result
        assert result["active_jobs"] == 3
        assert result["active_sessions"] == 2
