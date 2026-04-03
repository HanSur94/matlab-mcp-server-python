"""Extra coverage tests for monitoring/collector.py and monitoring/store.py.

Targets uncovered lines in collector.py:
- 42-43 (_get_system_metrics with psutil)
- 130-140 (store write in record_event via fire-and-forget)
- 150-153 (_flush_pending_events)
- 160-180 (sample_once pool/tracker/session metrics)
- 187-195 (system metrics in sample_once)
- 210-212 (execution stats persistence)
- 227-233 (start_sampling)
- 257-258 (get_current_snapshot pool)
- 274-275 (tracker in snapshot)
- 285-286 (sessions in snapshot)

Targets uncovered lines in store.py:
- 51 (_split_key no dot)
- 83-84 (close with no db)
- 111-112 (insert_metrics on closed)
- 120-121 (insert_event on closed)
- 140-148 (get_latest empty)
- 161-163 (get_latest with data)
- 170-189 (get_history)
- 204-244 (get_events filtering)
- 258-288 (get_aggregates)
- 326-328 (prune no db)
- 337-338 (prune errors)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from matlab_mcp.config import load_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config():
    config = load_config(None)
    config.monitoring.enabled = True
    config.monitoring.sample_interval = 1
    return config


def _make_status_pool(total=4, available=2, busy=2, max_engines=10):
    """Create a minimal MagicMock pool that returns get_status() data."""
    pool = MagicMock()
    pool.get_status.return_value = {
        "total": total,
        "available": available,
        "busy": busy,
        "max": max_engines,
    }
    return pool


def _make_mock_tracker(job_count=3):
    tracker = MagicMock()
    tracker.list_jobs.return_value = [f"job-{i}" for i in range(job_count)]
    return tracker


def _make_mock_sessions(count=5):
    sessions = MagicMock()
    sessions.session_count = count
    return sessions


# ===========================================================================
# MetricsCollector tests
# ===========================================================================


class TestGetSystemMetrics:
    def test_returns_memory_and_cpu_with_psutil(self):
        """_get_system_metrics should return floats when psutil is available."""
        from matlab_mcp.monitoring.collector import _get_system_metrics

        mem, cpu = _get_system_metrics()
        # psutil is in dev dependencies so it should be available
        assert mem is None or isinstance(mem, float)
        assert cpu is None or isinstance(cpu, float)

    def test_returns_none_when_psutil_unavailable(self):
        """_get_system_metrics should return (None, None) when psutil raises."""
        from matlab_mcp.monitoring.collector import _get_system_metrics

        with patch(
            "matlab_mcp.monitoring.collector.psutil",
            side_effect=ImportError("no psutil"),
            create=True,
        ):
            # The function catches all exceptions including ImportError
            # We need to patch the import inside the function
            pass

        # Patch at the import level inside the function
        import builtins

        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("mocked: no psutil")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            mem, cpu = _get_system_metrics()

        assert mem is None
        assert cpu is None


class TestCollectorRecordEventWithStore:
    async def test_record_event_fires_store_insert(self):
        """record_event with store set should create an async task for insert_event."""
        from matlab_mcp.monitoring.collector import MetricsCollector

        collector = MetricsCollector(_make_config())
        mock_store = AsyncMock()
        collector.store = mock_store

        # We are inside a running event loop (pytest-asyncio), so the
        # fire-and-forget path should work
        collector.record_event("job_completed", {"job_id": "j1", "execution_ms": 200})

        # Give the event loop a chance to process the task
        await asyncio.sleep(0.05)

        mock_store.insert_event.assert_called_once_with(
            "job_completed", {"job_id": "j1", "execution_ms": 200}
        )

    def test_record_event_queues_when_no_loop(self):
        """record_event with store but no running loop should queue the event."""
        from matlab_mcp.monitoring.collector import MetricsCollector

        collector = MetricsCollector(_make_config())
        collector.store = MagicMock()  # non-None store

        # Outside of an async context, get_running_loop raises RuntimeError.
        # record_event should catch that and queue the event.
        with patch("asyncio.get_running_loop", side_effect=RuntimeError("no loop")):
            collector.record_event("job_failed", {"job_id": "j2", "error": "boom"})

        assert len(collector._pending_events) == 1
        assert collector._pending_events[0] == (
            "job_failed",
            {"job_id": "j2", "error": "boom"},
        )


class TestCollectorFlushPendingEvents:
    async def test_flush_pending_events(self):
        """_flush_pending_events should write queued events to the store."""
        from matlab_mcp.monitoring.collector import MetricsCollector

        collector = MetricsCollector(_make_config())
        mock_store = AsyncMock()
        collector.store = mock_store

        # Manually add pending events
        collector._pending_events = [
            ("job_completed", {"job_id": "j1"}),
            ("job_failed", {"job_id": "j2"}),
        ]

        await collector._flush_pending_events()

        assert mock_store.insert_event.call_count == 2
        assert collector._pending_events == []

    async def test_flush_pending_no_store(self):
        """_flush_pending_events should be a no-op when store is None."""
        from matlab_mcp.monitoring.collector import MetricsCollector

        collector = MetricsCollector(_make_config())
        collector._pending_events = [("event", {"key": "val"})]
        collector.store = None

        await collector._flush_pending_events()

        # Pending events remain since there is no store
        assert len(collector._pending_events) == 1

    async def test_flush_pending_empty_list(self):
        """_flush_pending_events with empty list should be a no-op."""
        from matlab_mcp.monitoring.collector import MetricsCollector

        collector = MetricsCollector(_make_config())
        mock_store = AsyncMock()
        collector.store = mock_store
        collector._pending_events = []

        await collector._flush_pending_events()

        mock_store.insert_event.assert_not_called()


class TestCollectorSampleOnce:
    async def test_sample_once_with_all_components(self, tmp_path):
        """sample_once with pool, tracker, sessions should persist all metrics."""
        from matlab_mcp.monitoring.collector import MetricsCollector
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        collector = MetricsCollector(_make_config())
        collector.store = store
        collector.pool = _make_status_pool(total=6, available=4, busy=2, max_engines=10)
        collector.tracker = _make_mock_tracker(job_count=3)
        collector.sessions = _make_mock_sessions(count=5)

        # Add some execution times to test stats persistence
        for i in range(5):
            collector.record_event(
                "job_completed", {"job_id": f"j{i}", "execution_ms": (i + 1) * 100}
            )
        await asyncio.sleep(0.05)  # let fire-and-forget tasks complete

        await collector.sample_once()

        latest = await store.get_latest()
        assert latest["pool.total_engines"] == 6
        assert latest["pool.available_engines"] == 4
        assert latest["pool.busy_engines"] == 2
        assert latest["pool.max_engines"] == 10
        assert pytest.approx(latest["pool.utilization_pct"], abs=0.1) == 2 / 6 * 100
        assert latest["jobs.active_count"] == 3
        assert latest["sessions.active_count"] == 5
        assert "system.uptime_seconds" in latest
        # Execution stats should be persisted
        assert latest["jobs.avg_execution_ms"] is not None
        assert latest["jobs.p95_execution_ms"] is not None
        assert latest["jobs.completed_total"] == 5
        await store.close()

    async def test_sample_once_no_store_is_noop(self):
        """sample_once with store=None should return without error."""
        from matlab_mcp.monitoring.collector import MetricsCollector

        collector = MetricsCollector(_make_config())
        collector.store = None
        collector.pool = _make_status_pool()

        # Should not raise
        await collector.sample_once()

    async def test_sample_once_pool_error_handled(self, tmp_path):
        """sample_once should handle pool.get_status() raising an exception."""
        from matlab_mcp.monitoring.collector import MetricsCollector
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        collector = MetricsCollector(_make_config())
        collector.store = store
        bad_pool = MagicMock()
        bad_pool.get_status.side_effect = RuntimeError("pool crashed")
        collector.pool = bad_pool

        # Should not raise
        await collector.sample_once()

        latest = await store.get_latest()
        # Pool metrics should not be present since pool errored
        assert "pool.total_engines" not in latest
        # But system metrics should still be there
        assert "system.uptime_seconds" in latest
        await store.close()

    async def test_sample_once_tracker_error_handled(self, tmp_path):
        """sample_once should handle tracker.list_jobs() raising an exception."""
        from matlab_mcp.monitoring.collector import MetricsCollector
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        collector = MetricsCollector(_make_config())
        collector.store = store
        bad_tracker = MagicMock()
        bad_tracker.list_jobs.side_effect = RuntimeError("tracker crashed")
        collector.tracker = bad_tracker

        await collector.sample_once()

        latest = await store.get_latest()
        assert "jobs.active_count" not in latest
        await store.close()

    async def test_sample_once_sessions_error_handled(self, tmp_path):
        """sample_once should handle sessions.session_count raising an exception."""
        from matlab_mcp.monitoring.collector import MetricsCollector
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        collector = MetricsCollector(_make_config())
        collector.store = store
        bad_sessions = MagicMock()
        type(bad_sessions).session_count = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("sessions crashed"))
        )
        collector.sessions = bad_sessions

        await collector.sample_once()

        latest = await store.get_latest()
        assert "sessions.active_count" not in latest
        await store.close()


class TestCollectorStartSampling:
    async def test_start_sampling_runs_sample_once(self):
        """start_sampling should call sample_once at least once before we cancel."""
        from matlab_mcp.monitoring.collector import MetricsCollector

        collector = MetricsCollector(_make_config())
        collector.store = AsyncMock()
        collector.store.insert_metrics = AsyncMock()
        collector.store.insert_event = AsyncMock()

        task = asyncio.create_task(collector.start_sampling())
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # insert_metrics should have been called at least once
        assert collector.store.insert_metrics.call_count >= 1

    async def test_start_sampling_handles_sample_once_error(self):
        """start_sampling should continue looping even if sample_once fails."""
        from matlab_mcp.monitoring.collector import MetricsCollector

        config = _make_config()
        config.monitoring.sample_interval = 0  # minimal sleep between samples
        collector = MetricsCollector(config)

        call_count = 0

        async def failing_sample():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise RuntimeError("sample error")

        with patch.object(collector, "sample_once", side_effect=failing_sample):
            task = asyncio.create_task(collector.start_sampling())
            await asyncio.sleep(0.15)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        # Should have been called multiple times despite failures
        assert call_count >= 2


class TestCollectorGetCurrentSnapshot:
    def test_snapshot_with_all_components(self):
        """get_current_snapshot with pool, tracker, sessions returns full data."""
        from matlab_mcp.monitoring.collector import MetricsCollector

        collector = MetricsCollector(_make_config())
        collector.pool = _make_status_pool(total=4, available=1, busy=3, max_engines=8)
        collector.tracker = _make_mock_tracker(job_count=2)
        collector.sessions = _make_mock_sessions(count=7)

        # Record some events for counter coverage
        collector.record_event("job_completed", {"job_id": "j1", "execution_ms": 100})
        collector.record_event("job_failed", {"job_id": "j2", "error": "err"})

        snapshot = collector.get_current_snapshot()

        assert snapshot["pool"]["total"] == 4
        assert snapshot["pool"]["available"] == 1
        assert snapshot["pool"]["busy"] == 3
        assert snapshot["pool"]["max"] == 8
        assert snapshot["pool"]["utilization_pct"] == pytest.approx(75.0)
        assert snapshot["jobs"]["active"] == 2
        assert snapshot["jobs"]["completed_total"] == 1
        assert snapshot["jobs"]["failed_total"] == 1
        assert snapshot["sessions"]["active"] == 7
        assert snapshot["sessions"]["total_created"] == 0
        assert "system" in snapshot
        assert "uptime_seconds" in snapshot["system"]

    def test_snapshot_without_components(self):
        """get_current_snapshot with no pool/tracker/sessions returns defaults."""
        from matlab_mcp.monitoring.collector import MetricsCollector

        collector = MetricsCollector(_make_config())

        snapshot = collector.get_current_snapshot()

        assert snapshot["pool"] == {}
        assert snapshot["jobs"]["active"] == 0
        assert "active" not in snapshot["sessions"]

    def test_snapshot_pool_error_handled(self):
        """get_current_snapshot should handle pool.get_status() failure."""
        from matlab_mcp.monitoring.collector import MetricsCollector

        collector = MetricsCollector(_make_config())
        bad_pool = MagicMock()
        bad_pool.get_status.side_effect = RuntimeError("pool error")
        collector.pool = bad_pool

        snapshot = collector.get_current_snapshot()

        # Pool section should be empty dict (error was caught)
        assert snapshot["pool"] == {}

    def test_snapshot_tracker_error_handled(self):
        """get_current_snapshot should handle tracker.list_jobs() failure."""
        from matlab_mcp.monitoring.collector import MetricsCollector

        collector = MetricsCollector(_make_config())
        bad_tracker = MagicMock()
        bad_tracker.list_jobs.side_effect = RuntimeError("tracker error")
        collector.tracker = bad_tracker

        snapshot = collector.get_current_snapshot()

        # jobs.active should remain at 0 default
        assert snapshot["jobs"]["active"] == 0

    def test_snapshot_sessions_error_handled(self):
        """get_current_snapshot should handle sessions.session_count failure."""
        from matlab_mcp.monitoring.collector import MetricsCollector

        collector = MetricsCollector(_make_config())
        bad_sessions = MagicMock()
        type(bad_sessions).session_count = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("sessions error"))
        )
        collector.sessions = bad_sessions

        snapshot = collector.get_current_snapshot()

        # sessions should not have 'active' key
        assert "active" not in snapshot["sessions"]


# ===========================================================================
# MetricsStore tests
# ===========================================================================


class TestSplitKey:
    def test_split_key_with_dot(self):
        """_split_key should split 'pool.total' into ('pool', 'total')."""
        from matlab_mcp.monitoring.store import _split_key

        assert _split_key("pool.total") == ("pool", "total")

    def test_split_key_without_dot(self):
        """_split_key should return ('', key) when no dot is present."""
        from matlab_mcp.monitoring.store import _split_key

        assert _split_key("uptime") == ("", "uptime")

    def test_split_key_multiple_dots(self):
        """_split_key should split on the first dot only."""
        from matlab_mcp.monitoring.store import _split_key

        cat, name = _split_key("a.b.c")
        assert cat == "a"
        assert name == "b.c"


class TestStoreCloseNoDb:
    async def test_close_without_initialize(self):
        """close() on a store that was never initialized should be a no-op."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(":memory:")
        # _db is None, close should not raise
        await store.close()
        assert store._db is None


class TestStoreOperationsOnClosed:
    async def test_insert_metrics_on_closed(self, tmp_path):
        """insert_metrics on a closed store should warn and return."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        await store.close()

        # Should not raise
        await store.insert_metrics("2024-01-01T00:00:00Z", {"pool.total": 2})

    async def test_insert_event_on_closed(self, tmp_path):
        """insert_event on a closed store should warn and return."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        await store.close()

        await store.insert_event("job_completed", {"job_id": "j1"})

    async def test_get_latest_on_closed(self):
        """get_latest on a closed store should return empty dict."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(":memory:")
        result = await store.get_latest()
        assert result == {}

    async def test_get_history_on_closed(self):
        """get_history on a closed store should return empty list."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(":memory:")
        result = await store.get_history("pool.total", hours=1)
        assert result == []

    async def test_get_events_on_closed(self):
        """get_events on a closed store should return empty list."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(":memory:")
        result = await store.get_events(limit=10)
        assert result == []

    async def test_get_aggregates_on_closed(self):
        """get_aggregates on a closed store should return empty dict."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(":memory:")
        result = await store.get_aggregates(hours=1)
        assert result == {}

    async def test_prune_on_closed(self):
        """prune on a closed store should warn and return."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(":memory:")
        # Should not raise
        await store.prune(retention_days=7)


class TestStoreGetLatest:
    async def test_get_latest_empty_db(self, tmp_path):
        """get_latest on an empty database should return empty dict."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        result = await store.get_latest()
        assert result == {}
        await store.close()

    async def test_get_latest_with_data(self, tmp_path):
        """get_latest should return the most recent metrics snapshot."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        ts1 = "2024-01-01T00:00:00Z"
        ts2 = "2024-01-01T01:00:00Z"
        await store.insert_metrics(ts1, {"pool.total": 2, "pool.busy": 1})
        await store.insert_metrics(ts2, {"pool.total": 4, "pool.busy": 3})

        result = await store.get_latest()
        # Should return the ts2 snapshot (most recent)
        assert result["pool.total"] == 4.0
        assert result["pool.busy"] == 3.0
        await store.close()

    async def test_get_latest_with_no_dot_key(self, tmp_path):
        """get_latest should handle metrics with no category (no dot in key)."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        ts = "2024-01-01T00:00:00Z"
        await store.insert_metrics(ts, {"uptime": 3600})

        result = await store.get_latest()
        assert result["uptime"] == 3600.0
        await store.close()


class TestStoreGetHistory:
    async def test_get_history_with_data(self, tmp_path):
        """get_history should return time-series rows for a specific metric."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        now = datetime.now(timezone.utc)
        for i in range(5):
            ts = (now - timedelta(minutes=5 - i)).isoformat()
            await store.insert_metrics(ts, {"pool.utilization_pct": 10.0 * (i + 1)})

        history = await store.get_history("pool.utilization_pct", hours=1)
        assert len(history) == 5
        assert history[0]["value"] == 10.0
        assert history[4]["value"] == 50.0
        await store.close()

    async def test_get_history_respects_time_window(self, tmp_path):
        """get_history should only return data within the specified time window."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        now = datetime.now(timezone.utc)
        old_ts = (now - timedelta(hours=5)).isoformat()
        new_ts = now.isoformat()

        await store.insert_metrics(old_ts, {"pool.total": 2})
        await store.insert_metrics(new_ts, {"pool.total": 4})

        # Only look back 1 hour
        history = await store.get_history("pool.total", hours=1)
        assert len(history) == 1
        assert history[0]["value"] == 4.0
        await store.close()

    async def test_get_history_no_dot_key(self, tmp_path):
        """get_history should work with a key that has no dot separator."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        ts = datetime.now(timezone.utc).isoformat()
        await store.insert_metrics(ts, {"uptime": 42.0})

        history = await store.get_history("uptime", hours=1)
        assert len(history) == 1
        assert history[0]["value"] == 42.0
        await store.close()


class TestStoreGetEvents:
    async def test_get_events_unfiltered(self, tmp_path):
        """get_events with no filters should return all events."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        await store.insert_event("job_completed", {"job_id": "j1"})
        await store.insert_event("job_failed", {"job_id": "j2"})
        await store.insert_event("session_created", {"sid": "s1"})

        events = await store.get_events(limit=10)
        assert len(events) == 3
        # Should be ordered newest first
        for ev in events:
            assert "id" in ev
            assert "timestamp" in ev
            assert "event_type" in ev
            assert "details" in ev
        await store.close()

    async def test_get_events_single_type_filter(self, tmp_path):
        """get_events with event_type filter should return only matching events."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        await store.insert_event("job_completed", {"job_id": "j1"})
        await store.insert_event("job_failed", {"job_id": "j2"})
        await store.insert_event("job_completed", {"job_id": "j3"})

        events = await store.get_events(limit=10, event_type="job_completed")
        assert len(events) == 2
        assert all(e["event_type"] == "job_completed" for e in events)
        await store.close()

    async def test_get_events_types_list_filter(self, tmp_path):
        """get_events with event_types list should return matching events."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        await store.insert_event("job_completed", {"job_id": "j1"})
        await store.insert_event("job_failed", {"job_id": "j2"})
        await store.insert_event("engine_crash", {"engine_id": "e1"})
        await store.insert_event("session_created", {"sid": "s1"})

        events = await store.get_events(
            limit=10, event_types=["job_failed", "engine_crash"]
        )
        assert len(events) == 2
        types = {e["event_type"] for e in events}
        assert types == {"job_failed", "engine_crash"}
        await store.close()

    async def test_get_events_limit(self, tmp_path):
        """get_events should respect the limit parameter."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        for i in range(10):
            await store.insert_event("job_completed", {"job_id": f"j{i}"})

        events = await store.get_events(limit=3)
        assert len(events) == 3
        await store.close()


class TestStoreGetAggregates:
    async def test_get_aggregates_with_job_events(self, tmp_path):
        """get_aggregates should compute success rate and execution stats."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        # Insert 8 completed, 2 failed
        for i in range(8):
            await store.insert_event(
                "job_completed", {"job_id": f"j{i}", "execution_ms": 100 + i * 10}
            )
        for i in range(2):
            await store.insert_event("job_failed", {"job_id": f"f{i}", "error": "err"})

        agg = await store.get_aggregates(hours=1)

        assert agg["job_success_rate"] == pytest.approx(0.8, abs=0.01)
        assert agg["avg_execution_ms"] is not None
        assert agg["avg_execution_ms"] > 0
        assert agg["p95_execution_ms"] is not None
        assert agg["p95_execution_ms"] >= agg["avg_execution_ms"]
        assert agg["error_rate_per_minute"] >= 0
        await store.close()

    async def test_get_aggregates_empty_db(self, tmp_path):
        """get_aggregates on empty database should return zeroes/Nones."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        agg = await store.get_aggregates(hours=1)

        assert agg["job_success_rate"] == 0.0
        assert agg["avg_execution_ms"] is None
        assert agg["p95_execution_ms"] is None
        assert agg["error_rate_per_minute"] == 0.0
        await store.close()

    async def test_get_aggregates_with_error_events(self, tmp_path):
        """get_aggregates should count error events for error_rate_per_minute."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        await store.insert_event("job_failed", {"job_id": "j1", "error": "err"})
        await store.insert_event("blocked_function", {"function": "system"})
        await store.insert_event("engine_crash", {"engine_id": "e1"})
        await store.insert_event("health_check_fail", {"engine_id": "e2"})

        agg = await store.get_aggregates(hours=1)

        # 4 error events in a 60-minute window = 4/60 per minute
        assert agg["error_rate_per_minute"] > 0
        await store.close()

    async def test_get_aggregates_no_execution_ms_in_details(self, tmp_path):
        """get_aggregates should handle completed events with no execution_ms."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        await store.insert_event("job_completed", {"job_id": "j1"})  # no execution_ms
        await store.insert_event(
            "job_completed", {"job_id": "j2", "execution_ms": None}
        )

        agg = await store.get_aggregates(hours=1)
        assert agg["job_success_rate"] == 1.0
        assert agg["avg_execution_ms"] is None  # no valid exec times
        await store.close()


class TestStorePrune:
    async def test_prune_removes_old_data(self, tmp_path):
        """prune should remove metrics and events older than retention_days."""
        from matlab_mcp.monitoring.store import MetricsStore

        import aiosqlite

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        new_ts = datetime.now(timezone.utc).isoformat()

        await store.insert_metrics(old_ts, {"pool.total": 2})
        await store.insert_metrics(new_ts, {"pool.total": 4})

        # Insert an event and manually backdate it
        await store.insert_event("job_completed", {"job_id": "old"})
        async with aiosqlite.connect(str(tmp_path / "metrics.db")) as db:
            await db.execute(
                "UPDATE events SET timestamp = ? WHERE id = 1", (old_ts,)
            )
            await db.commit()

        await store.prune(retention_days=7)

        latest = await store.get_latest()
        assert latest["pool.total"] == 4.0

        history = await store.get_history("pool.total", hours=24 * 30)
        assert len(history) == 1

        events = await store.get_events(limit=100)
        assert len(events) == 0
        await store.close()

    async def test_prune_on_closed_store(self):
        """prune on a closed store should not raise."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(":memory:")
        await store.prune(retention_days=7)  # _db is None, should just return


# ===========================================================================
# Exception path tests — force db operations to raise
# ===========================================================================


class TestStoreExceptionPaths:
    """Tests that force database operations to raise exceptions to cover
    the except/warning blocks in store.py."""

    async def test_close_db_raises(self, tmp_path):
        """close() should swallow exceptions from db.close()."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        # Monkey-patch db.close to raise
        store._db.close = AsyncMock(side_effect=RuntimeError("close failed"))
        await store.close()
        assert store._db is None  # should still be cleaned up

    async def test_insert_metrics_db_raises(self, tmp_path):
        """insert_metrics should swallow db errors."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        # Monkey-patch executemany to raise
        store._db.executemany = AsyncMock(side_effect=RuntimeError("write failed"))
        # Should not raise
        await store.insert_metrics("2024-01-01T00:00:00Z", {"pool.total": 2})
        await store.close()

    async def test_insert_event_db_raises(self, tmp_path):
        """insert_event should swallow db errors."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        store._db.execute = AsyncMock(side_effect=RuntimeError("write failed"))
        await store.insert_event("job_completed", {"job_id": "j1"})
        await store.close()

    async def test_get_latest_db_raises(self, tmp_path):
        """get_latest should return {} when db raises."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        store._db.execute = AsyncMock(side_effect=RuntimeError("read failed"))
        result = await store.get_latest()
        assert result == {}
        await store.close()

    async def test_get_history_db_raises(self, tmp_path):
        """get_history should return [] when db raises."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        store._db.execute = AsyncMock(side_effect=RuntimeError("read failed"))
        result = await store.get_history("pool.total", hours=1)
        assert result == []
        await store.close()

    async def test_get_events_db_raises(self, tmp_path):
        """get_events should return [] when db raises."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        store._db.execute = AsyncMock(side_effect=RuntimeError("read failed"))
        result = await store.get_events(limit=10)
        assert result == []
        await store.close()

    async def test_get_aggregates_db_raises(self, tmp_path):
        """get_aggregates should return {} when db raises."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        store._db.execute = AsyncMock(side_effect=RuntimeError("read failed"))
        result = await store.get_aggregates(hours=1)
        assert result == {}
        await store.close()

    async def test_prune_db_raises(self, tmp_path):
        """prune should swallow db errors."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        store._db.execute = AsyncMock(side_effect=RuntimeError("delete failed"))
        await store.prune(retention_days=7)
        await store.close()
