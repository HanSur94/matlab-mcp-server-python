"""Tests for MetricsStore — async SQLite metrics storage."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


class TestMetricsStoreInit:
    async def test_creates_db_file(self, tmp_path):
        from matlab_mcp.monitoring.store import MetricsStore
        db_path = str(tmp_path / "metrics.db")
        store = MetricsStore(db_path)
        await store.initialize()
        assert Path(db_path).exists()
        await store.close()

    async def test_creates_tables(self, tmp_path):
        from matlab_mcp.monitoring.store import MetricsStore
        import aiosqlite
        db_path = str(tmp_path / "metrics.db")
        store = MetricsStore(db_path)
        await store.initialize()
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in await cursor.fetchall()}
        assert "metrics" in tables
        assert "events" in tables
        await store.close()


class TestMetricsStoreWrite:
    async def test_insert_metrics(self, tmp_path):
        from matlab_mcp.monitoring.store import MetricsStore
        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        ts = datetime.now(timezone.utc).isoformat()
        metrics = {"pool.total_engines": 4, "pool.utilization_pct": 50.0, "system.memory_mb": None}
        await store.insert_metrics(ts, metrics)
        rows = await store.get_latest()
        assert rows["pool.total_engines"] == 4
        assert rows["pool.utilization_pct"] == 50.0
        assert rows["system.memory_mb"] is None
        await store.close()

    async def test_insert_event(self, tmp_path):
        from matlab_mcp.monitoring.store import MetricsStore
        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        await store.insert_event("engine_scale_up", {"engine_id": "e1", "total_after": 3})
        events = await store.get_events(limit=10)
        assert len(events) == 1
        assert events[0]["event_type"] == "engine_scale_up"
        assert json.loads(events[0]["details"])["engine_id"] == "e1"
        await store.close()

    async def test_insert_metrics_error_does_not_raise(self, tmp_path):
        from matlab_mcp.monitoring.store import MetricsStore
        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        await store.close()
        ts = datetime.now(timezone.utc).isoformat()
        await store.insert_metrics(ts, {"pool.total": 1})  # Should not raise


class TestMetricsStoreRead:
    async def test_get_history(self, tmp_path):
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

    async def test_get_events_filtered_by_type(self, tmp_path):
        from matlab_mcp.monitoring.store import MetricsStore
        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        await store.insert_event("job_completed", {"job_id": "j1"})
        await store.insert_event("job_failed", {"job_id": "j2"})
        await store.insert_event("job_completed", {"job_id": "j3"})
        failed = await store.get_events(limit=10, event_type="job_failed")
        assert len(failed) == 1
        assert failed[0]["event_type"] == "job_failed"
        await store.close()

    async def test_get_aggregates(self, tmp_path):
        from matlab_mcp.monitoring.store import MetricsStore
        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        now = datetime.now(timezone.utc)
        for i in range(8):
            await store.insert_event("job_completed", {"job_id": f"j{i}", "execution_ms": 100})
        for i in range(2):
            await store.insert_event("job_failed", {"job_id": f"f{i}", "error": "err"})
        agg = await store.get_aggregates(hours=1)
        assert agg["job_success_rate"] == pytest.approx(0.8, abs=0.01)
        assert "avg_execution_ms" in agg
        assert "p95_execution_ms" in agg
        assert agg["error_rate_per_minute"] > 0
        await store.close()


class TestMetricsStorePrune:
    async def test_prune_removes_old_data(self, tmp_path):
        from matlab_mcp.monitoring.store import MetricsStore
        import aiosqlite
        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        new_ts = datetime.now(timezone.utc).isoformat()
        await store.insert_metrics(old_ts, {"pool.total": 2})
        await store.insert_metrics(new_ts, {"pool.total": 4})
        await store.insert_event("job_completed", {"job_id": "old"})
        # Manually set the old event's timestamp
        async with aiosqlite.connect(str(tmp_path / "metrics.db")) as db:
            await db.execute("UPDATE events SET timestamp = ? WHERE id = 1", (old_ts,))
            await db.commit()
        await store.prune(retention_days=7)
        latest = await store.get_latest()
        assert latest["pool.total"] == 4
        history = await store.get_history("pool.total", hours=24 * 30)
        assert len(history) == 1
        events = await store.get_events(limit=100)
        assert len(events) == 0
        await store.close()
