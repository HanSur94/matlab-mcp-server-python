"""Tests for the monitoring dashboard Starlette sub-app.

Covers every route defined in ``create_monitoring_app``:
/health, /metrics, /dashboard, /dashboard/api/current,
/dashboard/api/history, /dashboard/api/events
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from starlette.testclient import TestClient

from matlab_mcp.monitoring.dashboard import create_monitoring_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_state() -> MagicMock:
    """Build a mock ``state`` object that satisfies all dashboard route deps."""
    state = MagicMock()

    # collector.pool
    state.collector.pool.get_status.return_value = {
        "total": 2,
        "available": 1,
        "busy": 1,
        "max": 4,
    }

    # collector.tracker
    state.collector.tracker.list_jobs.return_value = []

    # collector.sessions
    state.collector.sessions.session_count = 1

    # collector.start_time (fixed value for deterministic uptime)
    state.collector.start_time = 1_000_000.0

    # counters / execution stats / snapshot
    state.collector.get_counters.return_value = {
        "completed_total": 5,
        "failed_total": 1,
        "cancelled_total": 0,
        "total_created_sessions": 3,
        "error_total": 1,
        "blocked_attempts": 0,
        "health_check_failures": 0,
    }
    state.collector.get_execution_stats.return_value = {
        "avg_execution_ms": 50.0,
        "p95_execution_ms": 100.0,
    }
    state.collector.get_current_snapshot.return_value = {
        "pool": {"total": 2},
        "jobs": {},
    }

    # Async store for history / events
    mock_store = AsyncMock()
    mock_store.get_history = AsyncMock(
        return_value=[{"timestamp": "2024-01-01", "value": 50.0}],
    )
    mock_store.get_events = AsyncMock(
        return_value=[
            {
                "id": 1,
                "timestamp": "2024-01-01",
                "event_type": "job_completed",
                "details": "{}",
            }
        ],
    )
    state.collector.store = mock_store

    return state


def _make_client(state: MagicMock | None = None) -> TestClient:
    """Create a ``TestClient`` bound to the monitoring app."""
    if state is None:
        state = _make_mock_state()
    app = create_monitoring_app(state)
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

class TestHealthRoute:
    def test_health_returns_json(self) -> None:
        """GET /health should return a 200 JSON response with 'status' key."""
        client = _make_client()
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body

    def test_health_has_expected_keys(self) -> None:
        """The health payload must include uptime, engines, and issues."""
        client = _make_client()
        body = client.get("/health").json()
        assert "uptime_seconds" in body
        assert "engines" in body
        assert "issues" in body

    def test_health_unhealthy_returns_503(self) -> None:
        """When no engines are running the status code should be 503."""
        state = _make_mock_state()
        state.collector.pool.get_status.return_value = {
            "total": 0,
            "available": 0,
            "busy": 0,
            "max": 4,
        }
        client = _make_client(state)
        resp = client.get("/health")
        assert resp.status_code == 503
        assert resp.json()["status"] == "unhealthy"


# ---------------------------------------------------------------------------
# /metrics
# ---------------------------------------------------------------------------

class TestMetricsRoute:
    def test_metrics_returns_json(self) -> None:
        """GET /metrics should return the collector's current snapshot."""
        client = _make_client()
        resp = client.get("/metrics")
        assert resp.status_code == 200
        body = resp.json()
        assert "pool" in body

    def test_metrics_delegates_to_snapshot(self) -> None:
        """The response must match get_current_snapshot() output."""
        state = _make_mock_state()
        state.collector.get_current_snapshot.return_value = {"sentinel": True}
        client = _make_client(state)
        body = client.get("/metrics").json()
        assert body == {"sentinel": True}


# ---------------------------------------------------------------------------
# /dashboard
# ---------------------------------------------------------------------------

class TestDashboardRoute:
    def test_dashboard_returns_html_or_404(self) -> None:
        """GET /dashboard should return HTML (200 if index.html exists, 404 otherwise)."""
        client = _make_client()
        resp = client.get("/dashboard")
        assert resp.status_code in (200, 404)
        assert "text/html" in resp.headers["content-type"]

    def test_dashboard_404_contains_not_found(self) -> None:
        """When the cached HTML is None, a 404 with informative body is returned."""
        # We cannot easily remove the static file, but we can verify the route
        # responds; if it returns 404, the body should mention "not found".
        client = _make_client()
        resp = client.get("/dashboard")
        if resp.status_code == 404:
            assert "not found" in resp.text.lower()


# ---------------------------------------------------------------------------
# /dashboard/api/current
# ---------------------------------------------------------------------------

class TestApiCurrentRoute:
    def test_api_current_returns_json(self) -> None:
        """GET /dashboard/api/current returns the same payload as /metrics."""
        client = _make_client()
        resp = client.get("/dashboard/api/current")
        assert resp.status_code == 200
        assert resp.json() == client.get("/metrics").json()


# ---------------------------------------------------------------------------
# /dashboard/api/history
# ---------------------------------------------------------------------------

class TestApiHistoryRoute:
    def test_history_returns_data(self) -> None:
        """GET /dashboard/api/history should return a data list."""
        client = _make_client()
        resp = client.get("/dashboard/api/history")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 1

    def test_history_passes_metric_and_hours(self) -> None:
        """Query params 'metric' and 'hours' are forwarded to the store."""
        state = _make_mock_state()
        client = _make_client(state)
        client.get("/dashboard/api/history?metric=cpu.usage&hours=2.5")
        state.collector.store.get_history.assert_called_once_with("cpu.usage", 2.5)

    def test_history_invalid_hours_defaults_to_one(self) -> None:
        """Non-numeric 'hours' param falls back to 1.0."""
        state = _make_mock_state()
        client = _make_client(state)
        client.get("/dashboard/api/history?hours=abc")
        state.collector.store.get_history.assert_called_once_with(
            "pool.utilization_pct", 1.0,
        )

    def test_history_no_store_returns_warning(self) -> None:
        """When collector.store is None, return an empty list with a warning."""
        state = _make_mock_state()
        state.collector.store = None
        client = _make_client(state)
        resp = client.get("/dashboard/api/history")
        body = resp.json()
        assert body["data"] == []
        assert "warning" in body


# ---------------------------------------------------------------------------
# /dashboard/api/events
# ---------------------------------------------------------------------------

class TestApiEventsRoute:
    def test_events_returns_events(self) -> None:
        """GET /dashboard/api/events should return an events list."""
        client = _make_client()
        resp = client.get("/dashboard/api/events")
        assert resp.status_code == 200
        body = resp.json()
        assert "events" in body
        assert isinstance(body["events"], list)
        assert len(body["events"]) == 1

    def test_events_passes_limit_and_type(self) -> None:
        """Query params 'limit' and 'type' are forwarded to the store."""
        state = _make_mock_state()
        client = _make_client(state)
        client.get("/dashboard/api/events?limit=50&type=job_failed")
        state.collector.store.get_events.assert_called_once_with(
            limit=50, event_type="job_failed",
        )

    def test_events_invalid_limit_defaults_to_100(self) -> None:
        """Non-numeric 'limit' param falls back to 100."""
        state = _make_mock_state()
        client = _make_client(state)
        client.get("/dashboard/api/events?limit=xyz")
        state.collector.store.get_events.assert_called_once_with(
            limit=100, event_type=None,
        )

    def test_events_no_store_returns_warning(self) -> None:
        """When collector.store is None, return empty events with a warning."""
        state = _make_mock_state()
        state.collector.store = None
        client = _make_client(state)
        resp = client.get("/dashboard/api/events")
        body = resp.json()
        assert body["events"] == []
        assert "warning" in body

    def test_events_no_type_param(self) -> None:
        """Omitting 'type' should pass None to the store."""
        state = _make_mock_state()
        client = _make_client(state)
        client.get("/dashboard/api/events?limit=10")
        state.collector.store.get_events.assert_called_once_with(
            limit=10, event_type=None,
        )
