# Monitoring Feature Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add integrated monitoring with SQLite metrics storage, health/metrics HTTP endpoints, a Plotly.js dashboard, and enriched MCP tools for agent self-monitoring.

**Architecture:** A `MetricsCollector` background task samples pool/job/session/system metrics every 10s into a `MetricsStore` (SQLite via aiosqlite). A `health.py` module evaluates server health. HTTP routes serve `/health`, `/metrics`, and `/dashboard`. Three new MCP tools expose metrics to agents. For stdio transport, a separate uvicorn instance serves the HTTP endpoints.

**Tech Stack:** Python 3.9+, aiosqlite, Plotly.js (CDN + bundled), uvicorn/Starlette (from FastMCP), optional psutil

**Spec:** `docs/superpowers/specs/2026-03-12-monitoring-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `src/matlab_mcp/monitoring/__init__.py` | Package init, re-exports |
| `src/matlab_mcp/monitoring/store.py` | `MetricsStore` — async SQLite CRUD + pruning |
| `src/matlab_mcp/monitoring/collector.py` | `MetricsCollector` — background sampling, event recording, ring buffer |
| `src/matlab_mcp/monitoring/health.py` | `evaluate_health()` — healthy/degraded/unhealthy logic |
| `src/matlab_mcp/monitoring/routes.py` | HTTP route handlers (`/health`, `/metrics`) |
| `src/matlab_mcp/monitoring/dashboard.py` | Dashboard Starlette sub-app + API routes |
| `src/matlab_mcp/monitoring/static/index.html` | Dashboard HTML page |
| `src/matlab_mcp/monitoring/static/dashboard.js` | Plotly.js charts, polling, time range selector |
| `src/matlab_mcp/monitoring/static/style.css` | Dashboard styling |
| `src/matlab_mcp/tools/monitoring.py` | MCP tool implementations (`get_server_metrics_impl`, etc.) |
| `tests/test_monitoring_store.py` | Tests for MetricsStore |
| `tests/test_monitoring_collector.py` | Tests for MetricsCollector |
| `tests/test_monitoring_health.py` | Tests for health evaluation |
| `tests/test_monitoring_routes.py` | Tests for HTTP endpoints |
| `tests/test_monitoring_tools.py` | Tests for MCP monitoring tools |

### Modified Files
| File | Change |
|------|--------|
| `src/matlab_mcp/config.py` | Add `MonitoringConfig` model, update `AppConfig`, update `resolve_paths()` |
| `src/matlab_mcp/pool/manager.py` | Add optional `collector` param, record events |
| `src/matlab_mcp/jobs/executor.py` | Add optional `collector` param, record events |
| `src/matlab_mcp/security/validator.py` | Add optional `collector` param, record events |
| `src/matlab_mcp/session/manager.py` | Add optional `collector` param, record events |
| `src/matlab_mcp/server.py` | Construct collector first, start/stop in lifespan, mount routes, register tools |
| `pyproject.toml` | Add `aiosqlite` dep, add `monitoring` optional extra |

---

## Chunk 1: Foundation (Config + Store + Collector)

### Task 1: Add MonitoringConfig and Dependencies

**Files:**
- Modify: `src/matlab_mcp/config.py`
- Modify: `pyproject.toml`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test for MonitoringConfig defaults**

Add to `tests/test_config.py`:

```python
class TestMonitoringConfig:
    def test_monitoring_defaults(self):
        """MonitoringConfig has correct defaults."""
        from matlab_mcp.config import MonitoringConfig

        cfg = MonitoringConfig()
        assert cfg.enabled is True
        assert cfg.sample_interval == 10
        assert cfg.retention_days == 7
        assert cfg.db_path == "./monitoring/metrics.db"
        assert cfg.dashboard_enabled is True
        assert cfg.http_port == 8766

    def test_monitoring_in_app_config(self):
        """AppConfig includes monitoring section with defaults."""
        from matlab_mcp.config import load_config

        config = load_config(None)
        assert hasattr(config, "monitoring")
        assert config.monitoring.enabled is True
        assert config.monitoring.sample_interval == 10

    def test_monitoring_env_override(self, monkeypatch):
        """Environment variables override monitoring config."""
        from matlab_mcp.config import load_config

        monkeypatch.setenv("MATLAB_MCP_MONITORING_SAMPLE_INTERVAL", "5")
        monkeypatch.setenv("MATLAB_MCP_MONITORING_RETENTION_DAYS", "30")
        monkeypatch.setenv("MATLAB_MCP_MONITORING_ENABLED", "false")
        config = load_config(None)
        assert config.monitoring.sample_interval == 5
        assert config.monitoring.retention_days == 30
        assert config.monitoring.enabled is False

    def test_monitoring_db_path_resolved(self, tmp_path):
        """monitoring.db_path is resolved to absolute path."""
        from matlab_mcp.config import load_config

        config = load_config(None)
        config.resolve_paths(tmp_path)
        assert Path(config.monitoring.db_path).is_absolute()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py::TestMonitoringConfig -v`
Expected: FAIL with `ImportError` or `AttributeError`

- [ ] **Step 3: Implement MonitoringConfig**

In `src/matlab_mcp/config.py`, add after the `SessionsConfig` class:

```python
class MonitoringConfig(BaseModel):
    """Monitoring and dashboard configuration."""

    enabled: bool = True
    sample_interval: int = 10
    retention_days: int = 7
    db_path: str = "./monitoring/metrics.db"
    dashboard_enabled: bool = True
    http_port: int = 8766
```

In the `AppConfig` class, add the field:

```python
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
```

In `AppConfig.resolve_paths()`, add:

```python
        self.monitoring.db_path = str((base_dir / self.monitoring.db_path).resolve())
```

- [ ] **Step 4: Update pyproject.toml**

Add `aiosqlite` to dependencies and `monitoring` optional extra:

```toml
dependencies = [
    "fastmcp>=2.0.0,<3.0.0",
    "pydantic>=2.0.0",
    "pyyaml>=6.0",
    "Pillow>=9.0.0",
    "aiosqlite>=0.19.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.0",
    "ruff>=0.1.0",
]
monitoring = ["psutil>=5.9.0", "uvicorn>=0.20.0"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_config.py::TestMonitoringConfig -v`
Expected: PASS (4 tests)

- [ ] **Step 6: Run full config test suite for regressions**

Run: `pytest tests/test_config.py -v`
Expected: All existing tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/matlab_mcp/config.py pyproject.toml tests/test_config.py
git commit -m "feat: add MonitoringConfig and aiosqlite dependency"
```

---

### Task 2: Implement MetricsStore

**Files:**
- Create: `src/matlab_mcp/monitoring/__init__.py`
- Create: `src/matlab_mcp/monitoring/store.py`
- Create: `tests/test_monitoring_store.py`

- [ ] **Step 1: Create the monitoring package**

Create `src/matlab_mcp/monitoring/__init__.py`:

```python
"""Monitoring subsystem for MATLAB MCP Server."""
```

- [ ] **Step 2: Write failing tests for MetricsStore**

Create `tests/test_monitoring_store.py`:

```python
"""Tests for MetricsStore — async SQLite metrics storage."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


class TestMetricsStoreInit:
    async def test_creates_db_file(self, tmp_path):
        """Store creates SQLite database file on init."""
        from matlab_mcp.monitoring.store import MetricsStore

        db_path = str(tmp_path / "metrics.db")
        store = MetricsStore(db_path)
        await store.initialize()
        assert Path(db_path).exists()
        await store.close()

    async def test_creates_tables(self, tmp_path):
        """Store creates metrics and events tables."""
        from matlab_mcp.monitoring.store import MetricsStore

        db_path = str(tmp_path / "metrics.db")
        store = MetricsStore(db_path)
        await store.initialize()

        import aiosqlite

        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in await cursor.fetchall()}
        assert "metrics" in tables
        assert "events" in tables
        await store.close()


class TestMetricsStoreWrite:
    async def test_insert_metrics(self, tmp_path):
        """insert_metrics stores all metrics for a timestamp."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        ts = datetime.now(timezone.utc).isoformat()
        metrics = {
            "pool.total_engines": 4,
            "pool.utilization_pct": 50.0,
            "system.memory_mb": None,
        }
        await store.insert_metrics(ts, metrics)

        rows = await store.get_latest()
        assert rows["pool.total_engines"] == 4
        assert rows["pool.utilization_pct"] == 50.0
        assert rows["system.memory_mb"] is None
        await store.close()

    async def test_insert_event(self, tmp_path):
        """insert_event stores a discrete event."""
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
        """Write failures are logged and swallowed, never crash."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()
        await store.close()  # Close the connection

        # Writing after close should not raise
        ts = datetime.now(timezone.utc).isoformat()
        await store.insert_metrics(ts, {"pool.total": 1})  # Should not raise


class TestMetricsStoreRead:
    async def test_get_history(self, tmp_path):
        """get_history returns time-series data for a metric."""
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
        """get_events filters by event_type when specified."""
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
        """get_aggregates computes job success rate and error rate."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        now = datetime.now(timezone.utc)
        for i in range(8):
            ts = (now - timedelta(minutes=i)).isoformat()
            await store.insert_event("job_completed", {"job_id": f"j{i}", "execution_ms": 100})
        for i in range(2):
            ts = (now - timedelta(minutes=i)).isoformat()
            await store.insert_event("job_failed", {"job_id": f"f{i}", "error": "err"})

        agg = await store.get_aggregates(hours=1)
        assert agg["job_success_rate"] == pytest.approx(0.8, abs=0.01)
        assert "avg_execution_ms" in agg
        assert "p95_execution_ms" in agg
        assert agg["error_rate_per_minute"] > 0  # 2 failures in ~10 minutes
        await store.close()


class TestMetricsStorePrune:
    async def test_prune_removes_old_data(self, tmp_path):
        """prune() deletes metrics and events older than retention."""
        from matlab_mcp.monitoring.store import MetricsStore

        store = MetricsStore(str(tmp_path / "metrics.db"))
        await store.initialize()

        old_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        new_ts = datetime.now(timezone.utc).isoformat()

        await store.insert_metrics(old_ts, {"pool.total": 2})
        await store.insert_metrics(new_ts, {"pool.total": 4})
        await store.insert_event("job_completed", {"job_id": "old"})

        # Manually set the old event's timestamp
        import aiosqlite

        async with aiosqlite.connect(str(tmp_path / "metrics.db")) as db:
            await db.execute(
                "UPDATE events SET timestamp = ? WHERE id = 1", (old_ts,)
            )
            await db.commit()

        await store.prune(retention_days=7)

        latest = await store.get_latest()
        assert latest["pool.total"] == 4

        history = await store.get_history("pool.total", hours=24 * 30)
        assert len(history) == 1  # Old one pruned

        events = await store.get_events(limit=100)
        assert len(events) == 0  # Old event pruned
        await store.close()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_monitoring_store.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement MetricsStore**

Create `src/matlab_mcp/monitoring/store.py`:

```python
"""MetricsStore — async SQLite storage for metrics and events."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    category TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value REAL
);

CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_cat_name ON metrics(category, metric_name);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    details TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
"""

# Error-class event types (used by get_error_log and error_rate_per_minute)
ERROR_EVENT_TYPES = frozenset({
    "job_failed",
    "blocked_function",
    "engine_crash",
    "health_check_fail",
})


class MetricsStore:
    """Async SQLite storage for time-series metrics and discrete events.

    All write operations catch exceptions and log warnings — monitoring
    failures must never crash the server.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """Open database and create tables if needed."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    # ------------------------------------------------------------------
    # Write operations (log-and-swallow on error)
    # ------------------------------------------------------------------

    async def insert_metrics(
        self, timestamp: str, metrics: dict[str, Any]
    ) -> None:
        """Batch insert metrics for one timestamp.

        *metrics* keys use ``category.metric_name`` format,
        e.g. ``{"pool.total_engines": 4, "system.memory_mb": None}``.
        """
        try:
            if not self._db:
                return
            rows = []
            for key, value in metrics.items():
                parts = key.split(".", 1)
                category = parts[0] if len(parts) == 2 else "unknown"
                metric_name = parts[1] if len(parts) == 2 else key
                rows.append((timestamp, category, metric_name, value))
            await self._db.executemany(
                "INSERT INTO metrics (timestamp, category, metric_name, value) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
            await self._db.commit()
        except Exception as exc:
            logger.warning("Failed to insert metrics: %s", exc)

    async def insert_event(
        self, event_type: str, details: dict[str, Any]
    ) -> None:
        """Insert a discrete event."""
        try:
            if not self._db:
                return
            ts = datetime.now(timezone.utc).isoformat()
            await self._db.execute(
                "INSERT INTO events (timestamp, event_type, details) VALUES (?, ?, ?)",
                (ts, event_type, json.dumps(details)),
            )
            await self._db.commit()
        except Exception as exc:
            logger.warning("Failed to insert event: %s", exc)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_latest(self) -> dict[str, Any]:
        """Return most recent metrics sample as {key: value}."""
        if not self._db:
            return {}
        cursor = await self._db.execute(
            "SELECT category, metric_name, value FROM metrics "
            "WHERE timestamp = (SELECT MAX(timestamp) FROM metrics)"
        )
        rows = await cursor.fetchall()
        return {f"{cat}.{name}": val for cat, name, val in rows}

    async def get_history(
        self, metric_key: str, hours: float
    ) -> list[dict[str, Any]]:
        """Return time-series for a metric over the last *hours*."""
        if not self._db:
            return []
        parts = metric_key.split(".", 1)
        if len(parts) != 2:
            return []
        category, metric_name = parts
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
        ).isoformat()
        cursor = await self._db.execute(
            "SELECT timestamp, value FROM metrics "
            "WHERE category = ? AND metric_name = ? AND timestamp >= ? "
            "ORDER BY timestamp ASC",
            (category, metric_name, cutoff),
        )
        return [{"timestamp": ts, "value": val} for ts, val in await cursor.fetchall()]

    async def get_events(
        self,
        limit: int = 100,
        event_type: Optional[str] = None,
        event_types: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Return recent events, optionally filtered."""
        if not self._db:
            return []
        if event_type:
            cursor = await self._db.execute(
                "SELECT timestamp, event_type, details FROM events "
                "WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?",
                (event_type, limit),
            )
        elif event_types:
            placeholders = ",".join("?" for _ in event_types)
            cursor = await self._db.execute(
                f"SELECT timestamp, event_type, details FROM events "
                f"WHERE event_type IN ({placeholders}) "
                f"ORDER BY timestamp DESC LIMIT ?",
                (*event_types, limit),
            )
        else:
            cursor = await self._db.execute(
                "SELECT timestamp, event_type, details FROM events "
                "ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        return [
            {"timestamp": ts, "event_type": et, "details": details}
            for ts, et, details in await cursor.fetchall()
        ]

    async def get_aggregates(self, hours: float) -> dict[str, Any]:
        """Compute aggregates over the last *hours*."""
        if not self._db:
            return {}
        cutoff = (
            datetime.now(timezone.utc) - timedelta(hours=hours)
        ).isoformat()

        # Job success rate from events
        cursor = await self._db.execute(
            "SELECT event_type, COUNT(*) FROM events "
            "WHERE event_type IN ('job_completed', 'job_failed') "
            "AND timestamp >= ? GROUP BY event_type",
            (cutoff,),
        )
        counts = dict(await cursor.fetchall())
        completed = counts.get("job_completed", 0)
        failed = counts.get("job_failed", 0)
        total_jobs = completed + failed
        success_rate = completed / total_jobs if total_jobs > 0 else 1.0

        # Avg execution time from metric samples
        cursor = await self._db.execute(
            "SELECT AVG(value) FROM metrics "
            "WHERE category = 'jobs' AND metric_name = 'avg_execution_ms' "
            "AND timestamp >= ? AND value IS NOT NULL",
            (cutoff,),
        )
        row = await cursor.fetchone()
        avg_exec = row[0] if row and row[0] is not None else 0.0

        # P95 execution time from metric samples
        cursor = await self._db.execute(
            "SELECT AVG(value) FROM metrics "
            "WHERE category = 'jobs' AND metric_name = 'p95_execution_ms' "
            "AND timestamp >= ? AND value IS NOT NULL",
            (cutoff,),
        )
        row = await cursor.fetchone()
        p95_exec = row[0] if row and row[0] is not None else 0.0

        # Error rate per minute
        error_types = tuple(ERROR_EVENT_TYPES)
        placeholders = ",".join("?" for _ in error_types)
        cursor = await self._db.execute(
            f"SELECT COUNT(*) FROM events "
            f"WHERE event_type IN ({placeholders}) AND timestamp >= ?",
            (*error_types, cutoff),
        )
        error_count = (await cursor.fetchone())[0]
        minutes = hours * 60
        error_rate = error_count / minutes if minutes > 0 else 0.0

        return {
            "job_success_rate": success_rate,
            "avg_execution_ms": avg_exec,
            "p95_execution_ms": p95_exec,
            "error_rate_per_minute": error_rate,
        }

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    async def prune(self, retention_days: int) -> None:
        """Delete metrics and events older than retention_days."""
        try:
            if not self._db:
                return
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=retention_days)
            ).isoformat()
            await self._db.execute(
                "DELETE FROM metrics WHERE timestamp < ?", (cutoff,)
            )
            await self._db.execute(
                "DELETE FROM events WHERE timestamp < ?", (cutoff,)
            )
            await self._db.commit()
        except Exception as exc:
            logger.warning("Failed to prune metrics: %s", exc)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_monitoring_store.py -v`
Expected: All PASS

- [ ] **Step 6: Install updated dependencies**

```bash
pip install -e ".[dev]"
```

- [ ] **Step 7: Commit**

```bash
git add src/matlab_mcp/monitoring/__init__.py src/matlab_mcp/monitoring/store.py tests/test_monitoring_store.py
git commit -m "feat: add MetricsStore with async SQLite storage"
```

---

### Task 3: Implement MetricsCollector

**Files:**
- Create: `src/matlab_mcp/monitoring/collector.py`
- Create: `tests/test_monitoring_collector.py`

- [ ] **Step 1: Write failing tests for MetricsCollector**

Create `tests/test_monitoring_collector.py`:

```python
"""Tests for MetricsCollector — background sampling and event recording."""
from __future__ import annotations

import asyncio
import time
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from matlab_mcp.config import AppConfig, load_config


def _make_config() -> AppConfig:
    config = load_config(None)
    config.monitoring.enabled = True
    config.monitoring.sample_interval = 1  # Fast for tests
    return config


def _make_mock_pool():
    pool = MagicMock()
    pool.get_status.return_value = {
        "total": 4,
        "available": 2,
        "busy": 2,
        "max": 10,
    }
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
        """MetricsCollector can be created with config."""
        from matlab_mcp.monitoring.collector import MetricsCollector

        config = _make_config()
        collector = MetricsCollector(config)
        assert collector.start_time <= time.time()
        assert collector.start_time > 0

    def test_collector_counters_start_at_zero(self):
        """All cumulative counters start at zero."""
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
        """record_event() updates in-memory counters."""
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
        """Execution times stored in ring buffer for avg/p95."""
        from matlab_mcp.monitoring.collector import MetricsCollector

        collector = MetricsCollector(_make_config())

        for i in range(150):
            collector.record_event("job_completed", {"job_id": f"j{i}", "execution_ms": i * 10})

        stats = collector.get_execution_stats()
        # Ring buffer holds last 100 (indices 50-149, values 500-1490)
        assert stats["avg_execution_ms"] > 0
        assert stats["p95_execution_ms"] >= stats["avg_execution_ms"]

    def test_record_event_with_store(self):
        """record_event() writes to store when set."""
        from matlab_mcp.monitoring.collector import MetricsCollector

        collector = MetricsCollector(_make_config())
        mock_store = AsyncMock()
        collector.store = mock_store

        collector.record_event("engine_scale_up", {"engine_id": "e1"})

        # Event should be queued for async write
        assert collector._pending_events


class TestCollectorSampling:
    async def test_sample_metrics(self, tmp_path):
        """sample_once() collects and stores metrics."""
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

        await store.close()

    async def test_sample_with_psutil_unavailable(self, tmp_path):
        """System metrics are None when psutil is not available."""
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_monitoring_collector.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement MetricsCollector**

Create `src/matlab_mcp/monitoring/collector.py`:

```python
"""MetricsCollector — background sampling and event recording."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Optional

from matlab_mcp.monitoring.store import MetricsStore

logger = logging.getLogger(__name__)

_RING_BUFFER_SIZE = 100

# Counter increments per event type
_COUNTER_MAP = {
    "job_completed": "completed_total",
    "job_failed": "failed_total",
    "job_cancelled": "cancelled_total",
    "session_created": "total_created_sessions",
    "blocked_function": "blocked_attempts",
    "health_check_fail": "health_check_failures",
}

# Event types that count as errors
_ERROR_EVENTS = {"job_failed", "blocked_function", "engine_crash", "health_check_fail"}


def _get_system_metrics() -> tuple[Optional[float], Optional[float]]:
    """Return (memory_mb, cpu_percent) or (None, None) if psutil unavailable."""
    try:
        import psutil

        proc = psutil.Process()
        mem = proc.memory_info().rss / 1e6
        cpu = proc.cpu_percent()
        return mem, cpu
    except ImportError:
        return None, None
    except Exception:
        return None, None


class MetricsCollector:
    """Collects server metrics and records events.

    Constructed before other components in ``MatlabMCPServer.__init__()``.
    The background sampling task is started later in the lifespan.
    """

    def __init__(self, config: Any) -> None:
        self._config = config
        self.start_time: float = time.time()

        # References set after construction (before sampling starts)
        self.store: Optional[MetricsStore] = None
        self.pool: Any = None
        self.tracker: Any = None
        self.sessions: Any = None

        # In-memory counters
        self._counters = {
            "completed_total": 0,
            "failed_total": 0,
            "cancelled_total": 0,
            "total_created_sessions": 0,
            "error_total": 0,
            "blocked_attempts": 0,
            "health_check_failures": 0,
        }

        # Execution time ring buffer (last 100 jobs)
        self._exec_times: deque[float] = deque(maxlen=_RING_BUFFER_SIZE)

        # Pending events to flush to store (written async)
        self._pending_events: list[tuple[str, dict]] = []

    # ------------------------------------------------------------------
    # Event recording (called synchronously from components)
    # ------------------------------------------------------------------

    def record_event(self, event_type: str, details: dict[str, Any]) -> None:
        """Record a discrete event. Updates counters and writes to store.

        Per spec, events are written to SQLite when they occur, not batched.
        We schedule an async write via the running event loop.
        """
        # Update counters
        counter_key = _COUNTER_MAP.get(event_type)
        if counter_key:
            self._counters[counter_key] += 1
        if event_type in _ERROR_EVENTS:
            self._counters["error_total"] += 1

        # Track execution times
        if event_type == "job_completed" and "execution_ms" in details:
            self._exec_times.append(details["execution_ms"])

        # Write to store immediately (fire-and-forget async)
        if self.store:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.store.insert_event(event_type, details))
            except RuntimeError:
                # No running loop — queue for next sample_once flush
                self._pending_events.append((event_type, details))

    def get_counters(self) -> dict[str, int]:
        """Return a copy of current counters."""
        return dict(self._counters)

    def get_execution_stats(self) -> dict[str, float]:
        """Return avg and p95 execution time from ring buffer."""
        if not self._exec_times:
            return {"avg_execution_ms": 0.0, "p95_execution_ms": 0.0}
        times = sorted(self._exec_times)
        avg = sum(times) / len(times)
        p95_idx = int((len(times) - 1) * 0.95)
        p95 = times[p95_idx]
        return {"avg_execution_ms": avg, "p95_execution_ms": p95}

    # ------------------------------------------------------------------
    # Sampling (called from background task)
    # ------------------------------------------------------------------

    async def sample_once(self) -> None:
        """Sample current state and write to store."""
        if not self.store or not self.pool:
            return

        ts = datetime.now(timezone.utc).isoformat()

        # Pool metrics
        status = self.pool.get_status()
        total = status.get("total", 0)
        available = status.get("available", 0)
        busy = status.get("busy", 0)
        utilization = (busy / total * 100) if total > 0 else 0.0

        # Job metrics
        active_jobs = 0
        if self.tracker:
            from matlab_mcp.jobs.models import JobStatus

            jobs = self.tracker.list_jobs()
            active_jobs = sum(
                1
                for j in jobs
                if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
            )

        # Session metrics
        active_sessions = 0
        if self.sessions:
            active_sessions = self.sessions.session_count

        # Execution stats
        exec_stats = self.get_execution_stats()

        # System metrics
        mem, cpu = _get_system_metrics()

        # Build metrics dict
        metrics = {
            "pool.total_engines": total,
            "pool.available_engines": available,
            "pool.busy_engines": busy,
            "pool.max_engines": status.get("max", 0),
            "pool.utilization_pct": utilization,
            "jobs.active_count": active_jobs,
            "jobs.completed_total": self._counters["completed_total"],
            "jobs.failed_total": self._counters["failed_total"],
            "jobs.cancelled_total": self._counters["cancelled_total"],
            "jobs.avg_execution_ms": exec_stats["avg_execution_ms"],
            "jobs.p95_execution_ms": exec_stats["p95_execution_ms"],
            "sessions.active_count": active_sessions,
            "sessions.total_created": self._counters["total_created_sessions"],
            "errors.total": self._counters["error_total"],
            "errors.blocked_attempts": self._counters["blocked_attempts"],
            "errors.health_check_failures": self._counters["health_check_failures"],
            "system.memory_mb": mem,
            "system.cpu_percent": cpu,
            "system.uptime_seconds": time.time() - self.start_time,
        }

        await self.store.insert_metrics(ts, metrics)

        # Flush pending events
        for event_type, details in self._pending_events:
            await self.store.insert_event(event_type, details)
        self._pending_events.clear()

    async def start_sampling(self) -> None:
        """Background loop — sample at configured interval."""
        interval = self._config.monitoring.sample_interval
        logger.info("Metrics collector started (interval=%ds)", interval)
        while True:
            try:
                await asyncio.sleep(interval)
                await self.sample_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Metrics sampling error: %s", exc)

    def get_current_snapshot(self) -> dict[str, Any]:
        """Return current metrics without hitting SQLite (for /metrics endpoint)."""
        status = self.pool.get_status() if self.pool else {}
        total = status.get("total", 0)
        available = status.get("available", 0)
        busy = status.get("busy", 0)

        active_jobs = 0
        if self.tracker:
            from matlab_mcp.jobs.models import JobStatus

            jobs = self.tracker.list_jobs()
            active_jobs = sum(
                1
                for j in jobs
                if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
            )

        active_sessions = self.sessions.session_count if self.sessions else 0
        exec_stats = self.get_execution_stats()

        mem, cpu = _get_system_metrics()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pool": {
                "total": total,
                "available": available,
                "busy": busy,
                "max": status.get("max", 0),
                "utilization_pct": (busy / total * 100) if total > 0 else 0.0,
            },
            "jobs": {
                "active": active_jobs,
                "completed_total": self._counters["completed_total"],
                "failed_total": self._counters["failed_total"],
                "cancelled_total": self._counters["cancelled_total"],
                "avg_execution_ms": exec_stats["avg_execution_ms"],
                "p95_execution_ms": exec_stats["p95_execution_ms"],
            },
            "sessions": {
                "active": active_sessions,
                "total_created": self._counters["total_created_sessions"],
            },
            "errors": {
                "total": self._counters["error_total"],
                "blocked_attempts": self._counters["blocked_attempts"],
                "health_check_failures": self._counters["health_check_failures"],
            },
            "system": {
                "memory_mb": mem,
                "cpu_percent": cpu,
            },
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_monitoring_collector.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/monitoring/collector.py tests/test_monitoring_collector.py
git commit -m "feat: add MetricsCollector with sampling and event recording"
```

---

### Task 4: Implement Health Evaluation

**Files:**
- Create: `src/matlab_mcp/monitoring/health.py`
- Create: `tests/test_monitoring_health.py`

- [ ] **Step 1: Write failing tests for health evaluation**

Create `tests/test_monitoring_health.py`:

```python
"""Tests for health evaluation logic."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest


def _make_collector(
    *,
    start_time: float = None,
    error_total: int = 0,
    pool_status: dict = None,
    active_jobs: int = 0,
    active_sessions: int = 0,
):
    """Create a mock collector with configurable state."""
    from matlab_mcp.monitoring.collector import MetricsCollector
    from matlab_mcp.config import load_config

    config = load_config(None)
    collector = MetricsCollector(config)
    if start_time:
        collector.start_time = start_time

    collector._counters["error_total"] = error_total

    pool = MagicMock()
    pool.get_status.return_value = pool_status or {
        "total": 4, "available": 2, "busy": 2, "max": 10,
    }
    pool._pool_config = MagicMock()
    pool._pool_config.queue_max_size = 50
    collector.pool = pool

    tracker = MagicMock()
    from matlab_mcp.jobs.models import JobStatus

    tracker.list_jobs.return_value = [MagicMock() for _ in range(active_jobs)]
    for j in tracker.list_jobs.return_value:
        j.status = JobStatus.RUNNING
    collector.tracker = tracker

    sessions = MagicMock()
    sessions.session_count = active_sessions
    collector.sessions = sessions

    return collector


class TestHealthEvaluation:
    def test_healthy_status(self):
        """Returns healthy when everything is normal."""
        from matlab_mcp.monitoring.health import evaluate_health

        collector = _make_collector(
            start_time=time.time() - 3600,
            pool_status={"total": 4, "available": 2, "busy": 2, "max": 10},
        )
        result = evaluate_health(collector)
        assert result["status"] == "healthy"
        assert result["issues"] == []
        assert result["uptime_seconds"] >= 3599

    def test_degraded_high_utilization(self):
        """Returns degraded when pool utilization > 90%."""
        from matlab_mcp.monitoring.health import evaluate_health

        collector = _make_collector(
            pool_status={"total": 10, "available": 0, "busy": 10, "max": 10},
        )
        result = evaluate_health(collector)
        assert result["status"] == "degraded"
        assert any("utilization" in i.lower() for i in result["issues"])

    def test_unhealthy_no_engines(self):
        """Returns unhealthy when 0 engines available and at max."""
        from matlab_mcp.monitoring.health import evaluate_health

        collector = _make_collector(
            pool_status={"total": 0, "available": 0, "busy": 0, "max": 0},
        )
        result = evaluate_health(collector)
        assert result["status"] == "unhealthy"

    def test_degraded_high_error_rate(self):
        """Returns degraded when error rate > 5/min."""
        from matlab_mcp.monitoring.health import evaluate_health

        collector = _make_collector(
            start_time=time.time() - 60,  # 1 minute uptime
            error_total=10,  # 10 errors/min > 5 threshold
        )
        result = evaluate_health(collector)
        assert result["status"] == "degraded"
        assert any("error rate" in i.lower() for i in result["issues"])

    def test_response_shape(self):
        """Health response contains all required fields."""
        from matlab_mcp.monitoring.health import evaluate_health

        collector = _make_collector(active_jobs=3, active_sessions=2)
        result = evaluate_health(collector)
        assert "status" in result
        assert "uptime_seconds" in result
        assert "issues" in result
        assert "engines" in result
        assert "active_jobs" in result
        assert "active_sessions" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_monitoring_health.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement health evaluation**

Create `src/matlab_mcp/monitoring/health.py`:

```python
"""Health evaluation for MATLAB MCP Server."""
from __future__ import annotations

import time
from typing import Any


def evaluate_health(collector: Any) -> dict[str, Any]:
    """Evaluate server health from live state.

    Returns a dict with status (healthy/degraded/unhealthy),
    uptime, issues list, and current engine/job/session counts.
    """
    issues: list[str] = []

    # Pool status
    pool_status = collector.pool.get_status() if collector.pool else {}
    total = pool_status.get("total", 0)
    available = pool_status.get("available", 0)
    busy = pool_status.get("busy", 0)
    max_engines = pool_status.get("max", 0)

    utilization = (busy / total * 100) if total > 0 else 0.0

    # Job count
    active_jobs = 0
    if collector.tracker:
        from matlab_mcp.jobs.models import JobStatus

        jobs = collector.tracker.list_jobs()
        active_jobs = sum(
            1 for j in jobs if j.status in (JobStatus.PENDING, JobStatus.RUNNING)
        )

    # Session count
    active_sessions = (
        collector.sessions.session_count if collector.sessions else 0
    )

    # Uptime
    uptime = time.time() - collector.start_time

    # --- Determine status ---
    status = "healthy"

    # Unhealthy conditions
    if total == 0:
        status = "unhealthy"
        issues.append("No engines running")
    elif available == 0 and total >= max_engines:
        status = "unhealthy"
        issues.append(
            f"All {total} engines busy and pool at max capacity ({max_engines})"
        )

    # Degraded conditions (only if not already unhealthy)
    if status == "healthy":
        if utilization > 90:
            status = "degraded"
            issues.append(
                f"Pool utilization at {utilization:.0f}% — consider increasing max_engines"
            )

        counters = collector.get_counters()
        if counters.get("health_check_failures", 0) > 0:
            status = "degraded"
            issues.append(
                f"{counters['health_check_failures']} health check failure(s) detected"
            )

        # Error rate > 5/min check
        error_total = counters.get("error_total", 0)
        uptime_minutes = uptime / 60 if uptime > 0 else 1
        error_rate = error_total / uptime_minutes
        if error_rate > 5:
            status = "degraded"
            issues.append(
                f"Error rate {error_rate:.1f}/min exceeds threshold (5/min)"
            )

    return {
        "status": status,
        "uptime_seconds": round(uptime, 1),
        "issues": issues,
        "engines": {
            "total": total,
            "available": available,
            "busy": busy,
        },
        "active_jobs": active_jobs,
        "active_sessions": active_sessions,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_monitoring_health.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/monitoring/health.py tests/test_monitoring_health.py
git commit -m "feat: add health evaluation logic"
```

---

## Chunk 2: Instrument Existing Components

### Task 5: Add Collector to Existing Components

**Files:**
- Modify: `src/matlab_mcp/pool/manager.py`
- Modify: `src/matlab_mcp/jobs/executor.py`
- Modify: `src/matlab_mcp/security/validator.py`
- Modify: `src/matlab_mcp/session/manager.py`
- Modify: `tests/test_pool.py`
- Modify: `tests/test_jobs.py`
- Modify: `tests/test_security.py`
- Modify: `tests/test_session.py`

- [ ] **Step 1: Write failing tests for collector integration**

Add to `tests/test_pool.py`:

```python
class TestPoolMonitoringEvents:
    async def test_scale_up_records_event(self, app_config):
        """Pool records engine_scale_up event when scaling up."""
        from unittest.mock import MagicMock

        collector = MagicMock()
        manager = EnginePoolManager(app_config, collector=collector)
        # Patch engine creation to avoid real MATLAB
        # ... (follow existing patched_pool_manager pattern)
        # After scale-up, verify:
        # collector.record_event.assert_any_call("engine_scale_up", ...)
```

Add to `tests/test_security.py`:

```python
class TestSecurityMonitoringEvents:
    def test_blocked_function_records_event(self):
        """SecurityValidator records blocked_function event."""
        from unittest.mock import MagicMock
        from matlab_mcp.security.validator import SecurityValidator
        from matlab_mcp.config import load_config

        config = load_config(None)
        collector = MagicMock()
        validator = SecurityValidator(config.security, collector=collector)

        with pytest.raises(BlockedFunctionError):
            validator.check_code("result = system('ls')")

        collector.record_event.assert_called_once()
        call_args = collector.record_event.call_args
        assert call_args[0][0] == "blocked_function"
        assert call_args[0][1]["function"] == "system"
```

Add to `tests/test_session.py`:

```python
class TestSessionMonitoringEvents:
    def test_create_session_records_event(self):
        """SessionManager records session_created event."""
        from unittest.mock import MagicMock
        from matlab_mcp.session.manager import SessionManager
        from matlab_mcp.config import load_config

        config = load_config(None)
        collector = MagicMock()
        manager = SessionManager(config, collector=collector)

        session = manager.create_session()
        collector.record_event.assert_called_once()
        assert collector.record_event.call_args[0][0] == "session_created"

    def test_get_or_create_default_records_event_only_once(self):
        """get_or_create_default records event only on first creation."""
        from unittest.mock import MagicMock
        from matlab_mcp.session.manager import SessionManager
        from matlab_mcp.config import load_config

        config = load_config(None)
        collector = MagicMock()
        manager = SessionManager(config, collector=collector)

        manager.get_or_create_default()  # Creates
        manager.get_or_create_default()  # Returns existing

        assert collector.record_event.call_count == 1

    def test_no_collector_does_not_crash(self):
        """SessionManager works without collector."""
        from matlab_mcp.session.manager import SessionManager
        from matlab_mcp.config import load_config

        manager = SessionManager(load_config(None))
        session = manager.create_session()
        assert session is not None
```

Add to `tests/test_jobs.py`:

```python
class TestExecutorMonitoringEvents:
    async def test_completion_records_event(self):
        """JobExecutor records job_completed event on success."""
        from unittest.mock import MagicMock, AsyncMock
        from matlab_mcp.jobs.executor import JobExecutor
        from matlab_mcp.config import load_config

        config = load_config(None)
        collector = MagicMock()
        pool = MagicMock()
        pool.acquire = AsyncMock()
        tracker = MagicMock()

        executor = JobExecutor(pool=pool, tracker=tracker, config=config, collector=collector)
        # Execute a job through the sync path (follow existing test patterns for pool/tracker mocking)
        # After completion, verify:
        collector.record_event.assert_any_call("job_completed", pytest.approx({"job_id": ANY, "execution_ms": ANY}, rel=None))

    async def test_failure_records_event(self):
        """JobExecutor records job_failed event on error."""
        from unittest.mock import MagicMock, AsyncMock, ANY
        from matlab_mcp.jobs.executor import JobExecutor
        from matlab_mcp.config import load_config

        config = load_config(None)
        collector = MagicMock()
        pool = MagicMock()
        pool.acquire = AsyncMock(side_effect=RuntimeError("engine error"))
        tracker = MagicMock()

        executor = JobExecutor(pool=pool, tracker=tracker, config=config, collector=collector)
        # Execute a job that fails, then verify:
        # collector.record_event.assert_any_call("job_failed", ...)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_security.py::TestSecurityMonitoringEvents tests/test_session.py::TestSessionMonitoringEvents -v`
Expected: FAIL with `TypeError` (unexpected keyword argument 'collector')

- [ ] **Step 3: Modify SecurityValidator to accept collector**

In `src/matlab_mcp/security/validator.py`, update `__init__`:

```python
def __init__(self, security_config: Any, collector: Any = None) -> None:
    self._config = security_config
    self._collector = collector
```

In the `check_code` method, add event recording **before** each raise. There are two code paths to instrument:

**Path 1 — Shell-escape (`!`) detection** (the early `if` block):

```python
        if self._config.blocked_functions_enabled and "!" in code:
            if self._collector:
                self._collector.record_event("blocked_function", {
                    "function": "!",
                })
            raise BlockedFunctionError("Shell escape '!' is blocked by security policy")
```

**Path 2 — Regex-matched blocked functions:**

```python
        if matched:
            if self._collector:
                self._collector.record_event("blocked_function", {
                    "function": matched,
                })
            raise BlockedFunctionError(
                f"Function {matched!r} is blocked by security policy"
            )
```

Note: `session_id_short` is omitted from the event detail since `check_code()` does not receive a session ID. The spec's event table shows it, but the security validator operates at a level below session awareness. The caller (executor) can enrich the event if needed in a future iteration.

- [ ] **Step 4: Modify SessionManager to accept collector**

In `src/matlab_mcp/session/manager.py`, update `__init__`:

```python
def __init__(self, config: Any = None, collector: Any = None) -> None:
    self._config = config
    self._collector = collector
    self._sessions: Dict[str, Session] = {}
```

In `create_session()`, after creating the session object, add:

```python
        if self._collector:
            self._collector.record_event("session_created", {
                "session_id_short": session.session_id[-8:],
            })
```

In `get_or_create_default()`, when creating a new session (after the `if session is not None: return session` check), add:

```python
        if self._collector:
            self._collector.record_event("session_created", {
                "session_id_short": session.session_id[-8:],
            })
```

- [ ] **Step 5: Modify EnginePoolManager to accept collector**

In `src/matlab_mcp/pool/manager.py`, update `__init__`:

```python
def __init__(self, config: Any, collector: Any = None) -> None:
    self._config = config
    self._pool_config = config.pool
    self._workspace_config = config.workspace
    self._collector = collector
```

Add event recording at scale-up, scale-down, crash, and replacement points in `run_health_checks()` and `acquire()`:

```python
# After successful scale-up:
if self._collector:
    self._collector.record_event("engine_scale_up", {
        "engine_id": engine.engine_id,
        "total_after": len(self._engines),
    })

# After scale-down:
if self._collector:
    self._collector.record_event("engine_scale_down", {
        "engine_id": engine.engine_id,
        "total_after": len(self._engines),
    })

# On health check failure (the check itself fails — e.g., exception during ping):
if self._collector:
    self._collector.record_event("health_check_fail", {
        "engine_id": engine.engine_id,
        "error": str(exc),
    })

# On engine crash (engine found dead/unresponsive AND scheduled for replacement):
# This is a SEPARATE event from health_check_fail. health_check_fail fires
# when the check encounters an error; engine_crash fires when the engine is
# confirmed dead and added to the to_replace list. Do NOT emit both for the
# same failure — emit health_check_fail for transient check errors, and
# engine_crash when the engine is being replaced.
if self._collector:
    self._collector.record_event("engine_crash", {
        "engine_id": engine.engine_id,
        "error": "Engine not responding",
    })

# On engine replacement — zip old and new engines to pair them:
# for old_engine, new_engine in zip(to_replace, new_engines):
#     if not isinstance(new_engine, Exception):
if self._collector:
    self._collector.record_event("engine_replaced", {
        "old_id": old_engine.engine_id,
        "new_id": new_engine.engine_id,
    })
```

- [ ] **Step 6: Modify JobExecutor to accept collector**

In `src/matlab_mcp/jobs/executor.py`, update `__init__`:

```python
def __init__(self, pool: Any, tracker: JobTracker, config: Any, collector: Any = None) -> None:
    self._pool = pool
    self._tracker = tracker
    self._config = config
    self._collector = collector
```

Add event recording at completion and failure points. **Important:** Instrument BOTH the sync path (in `execute_sync()` or the main execute method) AND the async path (in `_wait_for_completion()`), since jobs that exceed `sync_timeout` complete in the background task:

```python
# Helper to record job completion/failure (DRY — called from both paths):
def _record_job_event(self, job, error=None):
    if not self._collector:
        return
    if error:
        self._collector.record_event("job_failed", {
            "job_id": job.job_id,
            "error": str(error)[:200],
        })
    else:
        elapsed = (job.completed_at - job.started_at).total_seconds() * 1000 if job.started_at and job.completed_at else 0
        self._collector.record_event("job_completed", {
            "job_id": job.job_id,
            "execution_ms": elapsed,
        })

# Call self._record_job_event(job) after successful completion in BOTH:
# 1. The sync execution path (after tracker.update_status to COMPLETED)
# 2. The _wait_for_completion() method (after the async job finishes)

# Call self._record_job_event(job, error=exc) after failure in BOTH paths.
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `pytest tests/test_security.py tests/test_session.py tests/test_pool.py tests/test_jobs.py -v`
Expected: All PASS (existing tests unaffected since collector defaults to None)

- [ ] **Step 8: Commit**

```bash
git add src/matlab_mcp/pool/manager.py src/matlab_mcp/jobs/executor.py src/matlab_mcp/security/validator.py src/matlab_mcp/session/manager.py tests/test_pool.py tests/test_jobs.py tests/test_security.py tests/test_session.py
git commit -m "feat: instrument pool, executor, security, sessions with monitoring events"
```

---

## Chunk 3: HTTP Endpoints + MCP Tools

### Task 6: Implement HTTP Routes

**Files:**
- Create: `src/matlab_mcp/monitoring/routes.py`
- Create: `tests/test_monitoring_routes.py`

- [ ] **Step 1: Write failing tests for routes**

Create `tests/test_monitoring_routes.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_monitoring_routes.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement routes**

Create `src/matlab_mcp/monitoring/routes.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_monitoring_routes.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/monitoring/routes.py tests/test_monitoring_routes.py
git commit -m "feat: add HTTP route handlers for /health and /metrics"
```

---

### Task 7: Implement MCP Monitoring Tools

**Files:**
- Create: `src/matlab_mcp/tools/monitoring.py`
- Create: `tests/test_monitoring_tools.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_monitoring_tools.py`:

```python
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

    return MagicMock(
        collector=collector,
        pool=pool,
        tracker=tracker,
        sessions=sessions,
        config=config,
    )


class TestGetServerMetrics:
    async def test_returns_metrics(self):
        from matlab_mcp.tools.monitoring import get_server_metrics_impl

        state = _make_mock_state()
        result = await get_server_metrics_impl(state)
        assert result["pool"]["total"] == 4
        assert "timestamp" in result

    async def test_disabled_returns_error(self):
        from matlab_mcp.tools.monitoring import get_server_metrics_impl

        state = _make_mock_state()
        state.collector = None
        result = await get_server_metrics_impl(state)
        assert "error" in result


class TestGetServerHealth:
    async def test_returns_health(self):
        from matlab_mcp.tools.monitoring import get_server_health_impl

        state = _make_mock_state()
        result = await get_server_health_impl(state)
        assert result["status"] == "healthy"

    async def test_disabled_returns_error(self):
        from matlab_mcp.tools.monitoring import get_server_health_impl

        state = _make_mock_state()
        state.collector = None
        result = await get_server_health_impl(state)
        assert "error" in result


class TestGetErrorLog:
    async def test_returns_events(self):
        from matlab_mcp.tools.monitoring import get_error_log_impl

        state = _make_mock_state()
        state.collector.store.get_events = AsyncMock(return_value=[
            {"timestamp": "2026-01-01T00:00:00Z", "event_type": "job_failed", "details": "{}"},
        ])

        result = await get_error_log_impl(state, limit=20)
        assert "events" in result
        assert len(result["events"]) == 1

    async def test_disabled_returns_error(self):
        from matlab_mcp.tools.monitoring import get_error_log_impl

        state = _make_mock_state()
        state.collector = None
        result = await get_error_log_impl(state, limit=20)
        assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_monitoring_tools.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement MCP tool functions**

Create `src/matlab_mcp/tools/monitoring.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_monitoring_tools.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/tools/monitoring.py tests/test_monitoring_tools.py
git commit -m "feat: add MCP monitoring tool implementations"
```

---

## Chunk 4: Dashboard

### Task 8: Implement Dashboard Sub-App and API Routes

**Files:**
- Create: `src/matlab_mcp/monitoring/dashboard.py`

- [ ] **Step 1: Implement dashboard Starlette sub-app**

Create `src/matlab_mcp/monitoring/dashboard.py`:

```python
"""Dashboard Starlette sub-app with API routes and static file serving."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from matlab_mcp.monitoring.health import evaluate_health
from matlab_mcp.monitoring.routes import (
    build_health_response,
    build_metrics_response,
    get_health_status_code,
)

STATIC_DIR = Path(__file__).parent / "static"


def create_monitoring_app(state: Any) -> Starlette:
    """Create a Starlette app for monitoring endpoints + dashboard."""

    async def health_handler(request: Request) -> JSONResponse:
        response = build_health_response(state)
        return JSONResponse(response, status_code=get_health_status_code(response))

    async def metrics_handler(request: Request) -> JSONResponse:
        return JSONResponse(build_metrics_response(state))

    async def dashboard_handler(request: Request) -> HTMLResponse:
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return HTMLResponse(index_path.read_text())
        return HTMLResponse("<h1>Dashboard not found</h1>", status_code=404)

    async def api_current(request: Request) -> JSONResponse:
        return JSONResponse(build_metrics_response(state))

    async def api_history(request: Request) -> JSONResponse:
        metric = request.query_params.get("metric", "pool.utilization_pct")
        try:
            hours = float(request.query_params.get("hours", "1"))
        except (ValueError, TypeError):
            hours = 1.0
        store = state.collector.store if state.collector else None
        if not store:
            return JSONResponse({"data": [], "warning": "metrics unavailable"})
        data = await store.get_history(metric, hours)
        return JSONResponse({"data": data})

    async def api_events(request: Request) -> JSONResponse:
        try:
            limit = int(request.query_params.get("limit", "100"))
        except (ValueError, TypeError):
            limit = 100
        event_type = request.query_params.get("type")
        store = state.collector.store if state.collector else None
        if not store:
            return JSONResponse({"events": [], "warning": "metrics unavailable"})
        events = await store.get_events(limit=limit, event_type=event_type)
        return JSONResponse({"events": events})

    routes = [
        Route("/health", health_handler),
        Route("/metrics", metrics_handler),
        Route("/dashboard", dashboard_handler),
        Route("/dashboard/api/current", api_current),
        Route("/dashboard/api/history", api_history),
        Route("/dashboard/api/events", api_events),
    ]

    # Mount static files if directory exists
    if STATIC_DIR.exists():
        routes.append(
            Mount("/dashboard/static", app=StaticFiles(directory=str(STATIC_DIR)), name="static")
        )

    return Starlette(routes=routes)
```

- [ ] **Step 2: Commit**

```bash
git add src/matlab_mcp/monitoring/dashboard.py
git commit -m "feat: add dashboard Starlette sub-app with API routes"
```

---

### Task 9: Create Dashboard Static Files

**Files:**
- Create: `src/matlab_mcp/monitoring/static/style.css`
- Create: `src/matlab_mcp/monitoring/static/dashboard.js`
- Create: `src/matlab_mcp/monitoring/static/index.html`

- [ ] **Step 1: Create style.css**

Create `src/matlab_mcp/monitoring/static/style.css`:

```css
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; }
.header { background: #1a1a2e; color: white; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
.header h1 { font-size: 18px; font-weight: 600; }
.header .status { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.header .status .dot { width: 10px; height: 10px; border-radius: 50%; }
.dot.healthy { background: #4caf50; }
.dot.degraded { background: #ff9800; }
.dot.unhealthy { background: #f44336; }
.gauges { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; padding: 16px 24px; }
.gauge-card { background: white; border-radius: 8px; padding: 16px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.gauge-card .label { font-size: 12px; color: #666; text-transform: uppercase; letter-spacing: 1px; }
.gauge-card .value { font-size: 28px; font-weight: 700; margin: 8px 0; }
.time-range { padding: 8px 24px; display: flex; gap: 8px; }
.time-range button { padding: 6px 16px; border: 1px solid #ddd; border-radius: 4px; background: white; cursor: pointer; font-size: 13px; }
.time-range button.active { background: #1a1a2e; color: white; border-color: #1a1a2e; }
.charts { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 0 24px 16px; }
.chart-card { background: white; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.chart-card h3 { font-size: 14px; margin-bottom: 8px; color: #555; }
.events-section { padding: 0 24px 24px; }
.events-card { background: white; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.events-card h3 { font-size: 14px; margin-bottom: 12px; color: #555; display: flex; justify-content: space-between; }
.events-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.events-table th { text-align: left; padding: 8px; border-bottom: 2px solid #eee; color: #666; }
.events-table td { padding: 8px; border-bottom: 1px solid #f0f0f0; }
.events-table .type { font-weight: 600; }
.type-job_failed, .type-engine_crash { color: #f44336; }
.type-blocked_function, .type-health_check_fail { color: #ff9800; }
.type-engine_scale_up, .type-job_completed { color: #4caf50; }
.type-engine_scale_down { color: #2196f3; }
@media (max-width: 768px) { .gauges, .charts { grid-template-columns: 1fr; } }
```

- [ ] **Step 2: Create dashboard.js**

Create `src/matlab_mcp/monitoring/static/dashboard.js`:

```javascript
const REFRESH_INTERVAL = 10000;
let currentRange = 1; // hours
const charts = {};

async function fetchJSON(url) {
    try {
        const res = await fetch(url);
        return await res.json();
    } catch (e) {
        console.error('Fetch error:', e);
        return null;
    }
}

function formatUptime(seconds) {
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
    if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
    return `${(seconds / 86400).toFixed(1)}d`;
}

async function updateCurrent() {
    const data = await fetchJSON('/dashboard/api/current');
    if (!data) return;

    // Health
    const health = await fetchJSON('/health');
    if (health) {
        document.getElementById('status-dot').className = `dot ${health.status}`;
        document.getElementById('status-text').textContent = health.status.charAt(0).toUpperCase() + health.status.slice(1);
        document.getElementById('uptime').textContent = `Up ${formatUptime(health.uptime_seconds)}`;
    }

    // Gauges
    document.getElementById('gauge-pool').textContent = `${data.pool.utilization_pct.toFixed(0)}%`;
    document.getElementById('gauge-jobs').textContent = data.jobs.active;
    document.getElementById('gauge-sessions').textContent = data.sessions.active;

    const errRate = data.errors.total > 0 ? (data.errors.total / (health ? health.uptime_seconds / 60 : 1)).toFixed(2) : '0';
    document.getElementById('gauge-errors').textContent = errRate;
}

async function updateCharts() {
    const metrics = [
        { id: 'chart-pool', metric: 'pool.utilization_pct', title: 'Pool Utilization (%)', type: 'scatter', fill: 'tozeroy' },
        { id: 'chart-jobs', metric: 'jobs.completed_total', title: 'Jobs Completed', type: 'bar' },
        { id: 'chart-exec', metric: 'jobs.avg_execution_ms', title: 'Avg Execution Time (ms)', type: 'scatter' },
        { id: 'chart-sessions', metric: 'sessions.active_count', title: 'Active Sessions', type: 'scatter' },
        { id: 'chart-memory', metric: 'system.memory_mb', title: 'Memory (MB)', type: 'scatter' },
    ];

    for (const m of metrics) {
        const result = await fetchJSON(`/dashboard/api/history?metric=${m.metric}&hours=${currentRange}`);
        if (!result || !result.data) continue;

        const x = result.data.map(d => d.timestamp);
        const y = result.data.map(d => d.value);

        const trace = { x, y, type: m.type, name: m.title };
        if (m.fill) trace.fill = m.fill;
        trace.line = { color: '#1a1a2e' };

        const layout = {
            margin: { t: 10, r: 10, b: 30, l: 50 },
            height: 200,
            xaxis: { type: 'date' },
            yaxis: { title: '' },
        };

        if (charts[m.id]) {
            Plotly.react(m.id, [trace], layout);
        } else {
            Plotly.newPlot(m.id, [trace], layout, { responsive: true, displayModeBar: false });
            charts[m.id] = true;
        }
    }

    // P95 overlay on execution time chart (included in Plotly.react, not addTraces)
    const p95 = await fetchJSON(`/dashboard/api/history?metric=jobs.p95_execution_ms&hours=${currentRange}`);
    if (p95 && p95.data && p95.data.length > 0) {
        const avgResult = await fetchJSON(`/dashboard/api/history?metric=jobs.avg_execution_ms&hours=${currentRange}`);
        const traces = [];
        if (avgResult && avgResult.data) {
            traces.push({
                x: avgResult.data.map(d => d.timestamp),
                y: avgResult.data.map(d => d.value),
                type: 'scatter', name: 'Avg', line: { color: '#1a1a2e' },
            });
        }
        traces.push({
            x: p95.data.map(d => d.timestamp),
            y: p95.data.map(d => d.value),
            type: 'scatter', name: 'P95', line: { color: '#f44336', dash: 'dash' },
        });
        const layout = { margin: { t: 10, r: 10, b: 30, l: 50 }, height: 200, xaxis: { type: 'date' } };
        Plotly.react('chart-exec', traces, layout);
    }
}

let currentEventFilter = '';

function filterEvents(type) {
    currentEventFilter = type;
    updateEvents();
}

async function updateEvents() {
    const typeParam = currentEventFilter ? `&type=${currentEventFilter}` : '';
    const result = await fetchJSON(`/dashboard/api/events?limit=50${typeParam}`);
    if (!result || !result.events) return;

    const tbody = document.getElementById('events-body');
    tbody.innerHTML = '';
    for (const ev of result.events) {
        const tr = document.createElement('tr');
        const ts = new Date(ev.timestamp).toLocaleTimeString();
        let details = '';
        try { details = JSON.stringify(JSON.parse(ev.details)); } catch { details = ev.details; }
        tr.innerHTML = `<td>${ts}</td><td class="type type-${ev.event_type}">${ev.event_type}</td><td>${details}</td>`;
        tbody.appendChild(tr);
    }
}

function setRange(evt, hours) {
    currentRange = hours;
    document.querySelectorAll('.time-range button').forEach(b => b.classList.remove('active'));
    evt.target.classList.add('active');
    updateCharts();
}

async function refresh() {
    await updateCurrent();
    await updateCharts();
    await updateEvents();
}

// Wait for Plotly.js to load, then start
window.plotlyReady.then(function() {
    refresh();
    setInterval(refresh, REFRESH_INTERVAL);
});
```

- [ ] **Step 3: Create index.html**

Create `src/matlab_mcp/monitoring/static/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MATLAB MCP Server Dashboard</title>
    <link rel="stylesheet" href="/dashboard/static/style.css">
    <script>
        // Load Plotly.js: local bundle first, CDN fallback
        // Uses a promise so dashboard.js can await readiness
        window.plotlyReady = new Promise(function(resolve) {
            var local = document.createElement('script');
            local.src = '/dashboard/static/vendor/plotly.min.js';
            local.onload = function() { resolve(); };
            local.onerror = function() {
                var cdn = document.createElement('script');
                cdn.src = 'https://cdn.plot.ly/plotly-2.35.0.min.js';
                cdn.onload = function() { resolve(); };
                cdn.onerror = function() { console.error('Failed to load Plotly.js'); resolve(); };
                document.head.appendChild(cdn);
            };
            document.head.appendChild(local);
        });
    </script>
</head>
<body>
    <div class="header">
        <h1>MATLAB MCP Server Dashboard</h1>
        <div class="status">
            <span class="dot healthy" id="status-dot"></span>
            <span id="status-text">Healthy</span>
            <span id="uptime">Up 0s</span>
        </div>
    </div>

    <div class="gauges">
        <div class="gauge-card">
            <div class="label">Pool Utilization</div>
            <div class="value" id="gauge-pool">0%</div>
        </div>
        <div class="gauge-card">
            <div class="label">Active Jobs</div>
            <div class="value" id="gauge-jobs">0</div>
        </div>
        <div class="gauge-card">
            <div class="label">Active Sessions</div>
            <div class="value" id="gauge-sessions">0</div>
        </div>
        <div class="gauge-card">
            <div class="label">Errors/min</div>
            <div class="value" id="gauge-errors">0</div>
        </div>
    </div>

    <div class="time-range">
        <button class="active" onclick="setRange(event, 1)">1h</button>
        <button onclick="setRange(event, 6)">6h</button>
        <button onclick="setRange(event, 24)">24h</button>
        <button onclick="setRange(event, 168)">7d</button>
    </div>

    <div class="charts">
        <div class="chart-card"><h3>Pool Utilization</h3><div id="chart-pool"></div></div>
        <div class="chart-card"><h3>Job Throughput</h3><div id="chart-jobs"></div></div>
        <div class="chart-card"><h3>Execution Time</h3><div id="chart-exec"></div></div>
        <div class="chart-card"><h3>Active Sessions</h3><div id="chart-sessions"></div></div>
        <div class="chart-card"><h3>Memory Usage</h3><div id="chart-memory"></div></div>
    </div>

    <div class="events-section">
        <div class="events-card">
            <h3>Recent Events
                <select id="event-filter" onchange="filterEvents(this.value)">
                    <option value="">All</option>
                    <option value="job_completed">job_completed</option>
                    <option value="job_failed">job_failed</option>
                    <option value="engine_scale_up">engine_scale_up</option>
                    <option value="engine_scale_down">engine_scale_down</option>
                    <option value="engine_crash">engine_crash</option>
                    <option value="blocked_function">blocked_function</option>
                    <option value="health_check_fail">health_check_fail</option>
                    <option value="session_created">session_created</option>
                </select>
            </h3>
            <table class="events-table">
                <thead><tr><th>Time</th><th>Type</th><th>Details</th></tr></thead>
                <tbody id="events-body"></tbody>
            </table>
        </div>
    </div>

    <script src="/dashboard/static/dashboard.js"></script>
</body>
</html>
```

- [ ] **Step 4: Create vendor directory for bundled Plotly.js**

```bash
mkdir -p src/matlab_mcp/monitoring/static/vendor
# Download Plotly.js minified (the implementer should download the actual file)
echo "/* Plotly.js placeholder — download from https://cdn.plot.ly/plotly-2.35.0.min.js */" > src/matlab_mcp/monitoring/static/vendor/plotly.min.js
```

Note: The implementer should download the actual Plotly.js minified file from the CDN and place it at `src/matlab_mcp/monitoring/static/vendor/plotly.min.js` for air-gapped environments. The HTML falls back to CDN if the local file is a placeholder.

- [ ] **Step 5: Commit**

```bash
git add src/matlab_mcp/monitoring/static/ src/matlab_mcp/monitoring/dashboard.py
git commit -m "feat: add monitoring dashboard with Plotly.js charts"
```

---

## Chunk 5: Server Integration + Final Tests

### Task 10: Integrate Monitoring into Server

**Files:**
- Modify: `src/matlab_mcp/server.py`

- [ ] **Step 1: Update MatlabMCPServer.__init__ — collector first**

In `src/matlab_mcp/server.py`, update `MatlabMCPServer.__init__`:

```python
def __init__(self, config: AppConfig) -> None:
    self.config = config
    # Collector and store always initialised (None when disabled)
    self.collector: Optional[Any] = None
    self.store: Optional[Any] = None  # Set in lifespan when monitoring enabled
    if config.monitoring.enabled:
        from matlab_mcp.monitoring.collector import MetricsCollector
        self.collector = MetricsCollector(config)

    self.pool = EnginePoolManager(config, collector=self.collector)
    self.tracker = JobTracker(
        retention_seconds=config.sessions.job_retention_seconds
    )
    self.executor = JobExecutor(
        pool=self.pool,
        tracker=self.tracker,
        config=config,
        collector=self.collector,
    )
    self.sessions = SessionManager(config, collector=self.collector)
    self.security = SecurityValidator(config.security, collector=self.collector)
    self.formatter = ResultFormatter(config)
```

- [ ] **Step 2: Update lifespan — start monitoring**

In the `lifespan` function, after creating directories and before starting the pool, add:

```python
        # Initialize monitoring store and connect collector
        collector_task = None
        monitoring_server = None
        monitoring_task = None

        if config.monitoring.enabled and state.collector:
            from matlab_mcp.monitoring.store import MetricsStore

            monitoring_dir = Path(config.monitoring.db_path).parent
            monitoring_dir.mkdir(parents=True, exist_ok=True)

            state.store = MetricsStore(config.monitoring.db_path)
            await state.store.initialize()

            state.collector.store = state.store
```

After pool start, wire collector references and start sampling:

```python
        # Wire collector to live components
        if state.collector:
            state.collector.pool = state.pool
            state.collector.tracker = state.tracker
            state.collector.sessions = state.sessions
            collector_task = asyncio.create_task(state.collector.start_sampling())
```

Start stdio monitoring HTTP server if needed:

```python
        # Start monitoring HTTP server for stdio transport
        if (
            config.server.transport == "stdio"
            and config.monitoring.enabled
            and state.collector
        ):
            import uvicorn
            from matlab_mcp.monitoring.dashboard import create_monitoring_app

            monitoring_app = create_monitoring_app(state)
            uvi_config = uvicorn.Config(
                monitoring_app,
                host="127.0.0.1",
                port=config.monitoring.http_port,
                log_level="warning",
            )
            monitoring_server = uvicorn.Server(uvi_config)
            monitoring_task = asyncio.create_task(monitoring_server.serve())
            logger.info(
                "Monitoring dashboard at http://127.0.0.1:%d/dashboard",
                config.monitoring.http_port,
            )
```

- [ ] **Step 3: Update cleanup_loop — add store.prune()**

In the `cleanup_loop` function, add after `state.tracker.prune()`:

```python
                    if state.store:
                        await state.store.prune(config.monitoring.retention_days)
```

- [ ] **Step 4: Update shutdown — stop monitoring**

In the `finally` block, before cancelling health/cleanup tasks, add:

```python
            # Stop monitoring (order per spec: collector → store → HTTP server)
            if collector_task:
                collector_task.cancel()
                await asyncio.gather(collector_task, return_exceptions=True)
            if state.store:
                await state.store.close()
            if monitoring_server is not None:
                monitoring_server.should_exit = True
            if monitoring_task is not None:
                await monitoring_task
```

- [ ] **Step 5: Register MCP monitoring tools**

After existing tool registrations, add:

```python
    # ------------------------------------------------------------------
    # Monitoring tools
    # ------------------------------------------------------------------

    from matlab_mcp.tools.monitoring import (
        get_error_log_impl,
        get_server_health_impl,
        get_server_metrics_impl,
    )

    @mcp.tool
    async def get_server_metrics(ctx: Context) -> dict:
        """Get comprehensive server metrics including pool, jobs, sessions, and system stats."""
        return await get_server_metrics_impl(state)

    @mcp.tool
    async def get_server_health(ctx: Context) -> dict:
        """Get server health status with issue detection. Returns healthy/degraded/unhealthy."""
        return await get_server_health_impl(state)

    @mcp.tool
    async def get_error_log(ctx: Context, limit: int = 20) -> dict:
        """Get recent server errors and notable events for diagnosing issues."""
        return await get_error_log_impl(state, limit=limit)
```

- [ ] **Step 6: Mount routes for SSE transport**

For SSE transport, mount the monitoring routes on the FastMCP app. FastMCP 2.x exposes `mcp._additional_http_routes` which accepts Starlette `Route`/`Mount` objects. After `mcp = FastMCP(...)`, add:

```python
    # Mount monitoring routes for SSE transport
    if config.server.transport == "sse" and config.monitoring.enabled:
        from starlette.routing import Mount
        from matlab_mcp.monitoring.dashboard import create_monitoring_app

        monitoring_sub_app = create_monitoring_app(state)
        # FastMCP includes _additional_http_routes in its Starlette app
        mcp._additional_http_routes.append(
            Mount("/", app=monitoring_sub_app)
        )
```

This ensures `/health`, `/metrics`, `/dashboard`, and `/dashboard/api/*` are all served on the same host:port as the SSE transport.

- [ ] **Step 7: Run all existing tests for regressions**

Run: `pytest tests/ -v`
Expected: All 273+ existing tests PASS (new optional collector param doesn't break anything)

- [ ] **Step 8: Commit**

```bash
git add src/matlab_mcp/server.py
git commit -m "feat: integrate monitoring into server lifecycle and register MCP tools"
```

---

### Task 11: Add config.yaml monitoring section and update README

**Files:**
- Modify: `config.yaml`
- Modify: `README.md`

- [ ] **Step 1: Add monitoring section to config.yaml**

Add at the end of `config.yaml`:

```yaml
monitoring:
  enabled: true
  sample_interval: 10            # seconds between metric samples
  retention_days: 7              # days to keep historical data
  db_path: "./monitoring/metrics.db"
  dashboard_enabled: true
  http_port: 8766                # dashboard/health port (stdio transport only)
```

- [ ] **Step 2: Update .gitignore**

Add to `.gitignore`:

```
monitoring/
```

- [ ] **Step 3: Update README.md**

Add a Monitoring section to the README after the Configuration section:

```markdown
## Monitoring

The server includes a built-in monitoring dashboard with historical metrics.

### Dashboard

Access at `http://localhost:8766/dashboard` (stdio) or `http://localhost:8765/dashboard` (SSE).

### Health Check

```bash
curl http://localhost:8766/health
```

### Metrics

```bash
curl http://localhost:8766/metrics
```

### MCP Tools

| Tool | Description |
|------|-------------|
| `get_server_metrics` | Comprehensive server metrics |
| `get_server_health` | Health status with issue detection |
| `get_error_log` | Recent errors and notable events |
```

- [ ] **Step 4: Commit**

```bash
git add config.yaml .gitignore README.md
git commit -m "feat: add monitoring config, update README and gitignore"
```

---

### Task 12: Run Full Test Suite and Verify

- [ ] **Step 1: Install dependencies**

```bash
pip install -e ".[dev]"
```

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/ -v --tb=short
```

Expected: All tests PASS

- [ ] **Step 3: Run with coverage**

```bash
pytest tests/ --cov=matlab_mcp --cov-report=term-missing
```

- [ ] **Step 4: Lint**

```bash
ruff check src/ tests/
```

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address test/lint issues from monitoring integration"
```

- [ ] **Step 6: Push**

```bash
git push origin master
```
