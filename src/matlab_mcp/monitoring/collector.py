"""MetricsCollector for the MATLAB MCP Server monitoring subsystem.

Holds in-memory counters and a ring buffer for execution times.
Records events synchronously (fire-and-forget async store writes).
Samples pool/job/session/system metrics on a configurable interval.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Counter map: event_type -> counter key
# ---------------------------------------------------------------------------
_COUNTER_MAP: Dict[str, str] = {
    "job_completed": "completed_total",
    "job_failed": "failed_total",
    "job_cancelled": "cancelled_total",
    "session_created": "total_created_sessions",
    "blocked_function": "blocked_attempts",
    "health_check_fail": "health_check_failures",
}

_ERROR_EVENTS = {"job_failed", "blocked_function", "engine_crash", "health_check_fail"}


def _get_system_metrics() -> Tuple[Optional[float], Optional[float]]:
    """Return (memory_mb, cpu_percent) or (None, None) if psutil unavailable."""
    try:
        import psutil  # type: ignore

        proc = psutil.Process()
        mem = proc.memory_info().rss / 1e6
        cpu = proc.cpu_percent()
        return mem, cpu
    except Exception:
        return None, None


class MetricsCollector:
    """Collects, aggregates, and persists metrics for the MATLAB MCP Server."""

    def __init__(self, config: Any) -> None:
        """Initialize the metrics collector.

        Args:
            config: Application configuration; uses ``config.monitoring``
                for sample interval and retention settings.
        """
        self._config = config
        self.start_time: float = time.time()

        # In-memory counters
        self._counters: Dict[str, int] = {
            "completed_total": 0,
            "failed_total": 0,
            "cancelled_total": 0,
            "total_created_sessions": 0,
            "error_total": 0,
            "blocked_attempts": 0,
            "health_check_failures": 0,
        }

        # Ring buffer for execution times (maxlen=100)
        self._execution_times: Deque[float] = deque(maxlen=100)

        # Pending events queue for when no running loop is available
        self._pending_events: List[Tuple[str, Dict[str, Any]]] = []

        # Component references — set externally after construction
        self.store: Optional[Any] = None
        self.pool: Optional[Any] = None
        self.tracker: Optional[Any] = None
        self.sessions: Optional[Any] = None

        # Background sampling task reference
        self._sampling_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Counter access
    # ------------------------------------------------------------------

    def get_counters(self) -> Dict[str, int]:
        """Return a snapshot of current in-memory counters."""
        return dict(self._counters)

    # ------------------------------------------------------------------
    # Execution stats
    # ------------------------------------------------------------------

    def get_execution_stats(self) -> Dict[str, Optional[float]]:
        """Return avg and p95 execution times from the ring buffer."""
        times = list(self._execution_times)
        if not times:
            return {"avg_execution_ms": None, "p95_execution_ms": None}
        avg = sum(times) / len(times)
        sorted_times = sorted(times)
        idx = int((len(sorted_times) - 1) * 0.95)
        p95 = sorted_times[idx]
        return {"avg_execution_ms": avg, "p95_execution_ms": p95}

    # ------------------------------------------------------------------
    # Event recording
    # ------------------------------------------------------------------

    def record_event(self, event_type: str, details: Dict[str, Any]) -> None:
        """Record an event synchronously; fire-and-forget async store write.

        Updates in-memory counters immediately.
        Attempts to create an async task via the running loop. Falls back to
        _pending_events queue if no loop is running.
        """
        # Update in-memory counters
        counter_key = _COUNTER_MAP.get(event_type)
        if counter_key is not None:
            self._counters[counter_key] += 1

        # Increment error_total for error events
        if event_type in _ERROR_EVENTS:
            self._counters["error_total"] += 1

        # Track execution time for job_completed
        if event_type == "job_completed" and "execution_ms" in details:
            exec_ms = details["execution_ms"]
            if exec_ms is not None:
                self._execution_times.append(float(exec_ms))

        # Fire-and-forget async store write
        if self.store is not None:
            try:
                loop = asyncio.get_running_loop()
                def _on_store_done(t: asyncio.Task) -> None:
                    if not t.cancelled() and t.exception():
                        logger.warning("Store write failed: %s", t.exception())

                task = loop.create_task(self.store.insert_event(event_type, details))
                task.add_done_callback(_on_store_done)
            except RuntimeError:
                # No running event loop — queue for later flush
                self._pending_events.append((event_type, details))

    # ------------------------------------------------------------------
    # Sampling
    # ------------------------------------------------------------------

    async def _flush_pending_events(self) -> None:
        """Flush any pending events accumulated without a running loop."""
        if not self._pending_events or self.store is None:
            return
        pending = self._pending_events
        self._pending_events = []
        for event_type, details in pending:
            await self.store.insert_event(event_type, details)

    async def sample_once(self) -> None:
        """Collect a full metrics snapshot and persist it to the store."""
        await self._flush_pending_events()

        if self.store is None:
            return

        ts = datetime.now(timezone.utc).isoformat()
        metrics: Dict[str, Any] = {}

        # Pool metrics
        if self.pool is not None:
            try:
                status = self.pool.get_status()
                total = status.get("total", 0)
                available = status.get("available", 0)
                busy = status.get("busy", 0)
                max_engines = status.get("max", 0)
                metrics["pool.total_engines"] = total
                metrics["pool.available_engines"] = available
                metrics["pool.busy_engines"] = busy
                utilization = (busy / total * 100.0) if total > 0 else 0.0
                metrics["pool.utilization_pct"] = utilization
                metrics["pool.max_engines"] = max_engines
            except Exception as exc:
                logger.warning("Failed to collect pool metrics: %s", exc)

        # Job/tracker metrics
        if self.tracker is not None:
            try:
                jobs = self.tracker.list_jobs()
                metrics["jobs.active_count"] = len(jobs)
            except Exception as exc:
                logger.warning("Failed to collect tracker metrics: %s", exc)

        # Session metrics
        if self.sessions is not None:
            try:
                metrics["sessions.active_count"] = self.sessions.session_count
            except Exception as exc:
                logger.warning("Failed to collect sessions metrics: %s", exc)

        # System metrics
        memory_mb, cpu_percent = _get_system_metrics()
        if memory_mb is not None:
            metrics["system.memory_mb"] = memory_mb
        if cpu_percent is not None:
            metrics["system.cpu_percent"] = cpu_percent

        # Uptime
        metrics["system.uptime_seconds"] = time.time() - self.start_time

        # Execution stats
        exec_stats = self.get_execution_stats()
        if exec_stats["avg_execution_ms"] is not None:
            metrics["jobs.avg_execution_ms"] = exec_stats["avg_execution_ms"]
        if exec_stats["p95_execution_ms"] is not None:
            metrics["jobs.p95_execution_ms"] = exec_stats["p95_execution_ms"]

        # Counter persistence
        metrics["jobs.completed_total"] = self._counters["completed_total"]
        metrics["jobs.failed_total"] = self._counters["failed_total"]
        metrics["jobs.cancelled_total"] = self._counters["cancelled_total"]
        metrics["sessions.total_created"] = self._counters["total_created_sessions"]
        metrics["errors.total"] = self._counters["error_total"]
        metrics["errors.blocked_attempts"] = self._counters["blocked_attempts"]
        metrics["errors.health_check_failures"] = self._counters["health_check_failures"]

        await self.store.insert_metrics(ts, metrics)

    async def start_sampling(self) -> None:
        """Background loop that calls sample_once() on the configured interval."""
        interval = self._config.monitoring.sample_interval
        while True:
            try:
                await self.sample_once()
            except Exception as exc:
                logger.warning("sample_once failed: %s", exc)
            await asyncio.sleep(interval)

    # ------------------------------------------------------------------
    # Live snapshot (no SQLite hit)
    # ------------------------------------------------------------------

    def get_current_snapshot(self) -> Dict[str, Any]:
        """Return a structured dict of live metrics for the /metrics endpoint."""
        snapshot: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Pool
        pool_data: Dict[str, Any] = {}
        if self.pool is not None:
            try:
                status = self.pool.get_status()
                pool_data["total"] = status.get("total", 0)
                pool_data["available"] = status.get("available", 0)
                pool_data["busy"] = status.get("busy", 0)
                pool_data["max"] = status.get("max", 0)
                total = status.get("total", 0)
                busy = status.get("busy", 0)
                pool_data["utilization_pct"] = (busy / total * 100.0) if total > 0 else 0.0
            except Exception as exc:
                logger.warning("get_current_snapshot pool error: %s", exc)
        snapshot["pool"] = pool_data

        # Jobs / tracker
        exec_stats = self.get_execution_stats()
        jobs_data: Dict[str, Any] = {
            "active": 0,
            "completed_total": self._counters["completed_total"],
            "failed_total": self._counters["failed_total"],
            "cancelled_total": self._counters["cancelled_total"],
            "avg_execution_ms": exec_stats["avg_execution_ms"],
        }
        if self.tracker is not None:
            try:
                jobs = self.tracker.list_jobs()
                jobs_data["active"] = len(jobs)
            except Exception as exc:
                logger.warning("get_current_snapshot tracker error: %s", exc)
        snapshot["jobs"] = jobs_data

        # Sessions
        sessions_data: Dict[str, Any] = {
            "total_created": self._counters["total_created_sessions"],
        }
        if self.sessions is not None:
            try:
                sessions_data["active"] = self.sessions.session_count
            except Exception as exc:
                logger.warning("get_current_snapshot sessions error: %s", exc)
        snapshot["sessions"] = sessions_data

        # Errors
        snapshot["errors"] = {
            "total": self._counters["error_total"],
            "blocked_attempts": self._counters["blocked_attempts"],
            "health_check_failures": self._counters["health_check_failures"],
        }

        # System
        system_data: Dict[str, Any] = {
            "uptime_seconds": time.time() - self.start_time,
        }
        memory_mb, cpu_percent = _get_system_metrics()
        if memory_mb is not None:
            system_data["memory_mb"] = memory_mb
        if cpu_percent is not None:
            system_data["cpu_percent"] = cpu_percent
        snapshot["system"] = system_data

        return snapshot
