"""Async SQLite metrics storage for the MATLAB MCP Server monitoring subsystem."""
from __future__ import annotations

import json
import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import aiosqlite

logger = logging.getLogger(__name__)

ERROR_EVENT_TYPES = frozenset({"job_failed", "blocked_function", "engine_crash", "health_check_fail"})

_CREATE_METRICS_TABLE = """
CREATE TABLE IF NOT EXISTS metrics (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp     TEXT NOT NULL,
    category      TEXT NOT NULL,
    metric_name   TEXT NOT NULL,
    value         REAL
);
"""

_CREATE_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    details     TEXT NOT NULL
);
"""

_CREATE_METRICS_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_metrics_category_name ON metrics(category, metric_name);",
]

_CREATE_EVENTS_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);"
)


def _split_key(key: str):
    """Split 'category.metric_name' into (category, metric_name)."""
    if "." in key:
        category, _, name = key.partition(".")
    else:
        category, name = "", key
    return category, name


class MetricsStore:
    """Async SQLite-backed store for time-series metrics and structured events."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Open the database and create schema if needed."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("PRAGMA journal_mode=WAL;")
        await self._db.execute(_CREATE_METRICS_TABLE)
        await self._db.execute(_CREATE_EVENTS_TABLE)
        for idx_sql in _CREATE_METRICS_INDEXES:
            await self._db.execute(idx_sql)
        await self._db.execute(_CREATE_EVENTS_INDEX)
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db is not None:
            try:
                await self._db.close()
            except Exception:
                pass
            finally:
                self._db = None

    # ------------------------------------------------------------------
    # Write operations (log-and-swallow)
    # ------------------------------------------------------------------

    async def insert_metrics(self, timestamp: str, metrics_dict: Dict[str, Any]) -> None:
        """Batch-insert a snapshot of metrics.

        Each key in *metrics_dict* is expected to be in ``category.metric_name``
        format.  Errors are logged and swallowed so they never crash the server.
        """
        if self._db is None:
            logger.warning("insert_metrics called on closed MetricsStore — skipping")
            return
        try:
            rows = [
                (timestamp, *_split_key(key), None if value is None else float(value))
                for key, value in metrics_dict.items()
            ]
            await self._db.executemany(
                "INSERT INTO metrics (timestamp, category, metric_name, value) VALUES (?, ?, ?, ?);",
                rows,
            )
            await self._db.commit()
        except Exception as exc:
            logger.warning("insert_metrics failed: %s", exc)

    async def insert_event(self, event_type: str, details_dict: Dict[str, Any]) -> None:
        """Insert a structured event with the current UTC timestamp.

        Errors are logged and swallowed.
        """
        if self._db is None:
            logger.warning("insert_event called on closed MetricsStore — skipping")
            return
        try:
            ts = datetime.now(timezone.utc).isoformat()
            details_json = json.dumps(details_dict)
            await self._db.execute(
                "INSERT INTO events (timestamp, event_type, details) VALUES (?, ?, ?);",
                (ts, event_type, details_json),
            )
            await self._db.commit()
        except Exception as exc:
            logger.warning("insert_event failed: %s", exc)

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_latest(self) -> Dict[str, Any]:
        """Return the most recent metrics sample as a flat dict."""
        if self._db is None:
            return {}
        try:
            # Find the timestamp of the most recent sample
            cursor = await self._db.execute(
                "SELECT MAX(timestamp) FROM metrics;"
            )
            row = await cursor.fetchone()
            if row is None or row[0] is None:
                return {}
            latest_ts = row[0]

            cursor = await self._db.execute(
                "SELECT category, metric_name, value FROM metrics WHERE timestamp = ?;",
                (latest_ts,),
            )
            rows = await cursor.fetchall()
            result: Dict[str, Any] = {}
            for category, name, value in rows:
                key = f"{category}.{name}" if category else name
                result[key] = value  # value is None or float
            return result
        except Exception as exc:
            logger.warning("get_latest failed: %s", exc)
            return {}

    async def get_history(
        self, metric_key: str, hours: float
    ) -> List[Dict[str, Any]]:
        """Return time-series rows for *metric_key* within the last *hours* hours."""
        if self._db is None:
            return []
        try:
            category, name = _split_key(metric_key)
            cutoff = (
                datetime.now(timezone.utc) - timedelta(hours=hours)
            ).isoformat()
            cursor = await self._db.execute(
                """
                SELECT timestamp, value
                FROM metrics
                WHERE category = ? AND metric_name = ? AND timestamp >= ?
                ORDER BY timestamp ASC;
                """,
                (category, name, cutoff),
            )
            rows = await cursor.fetchall()
            return [{"timestamp": r[0], "value": r[1]} for r in rows]
        except Exception as exc:
            logger.warning("get_history failed: %s", exc)
            return []

    async def get_events(
        self,
        limit: int,
        event_type: Optional[str] = None,
        event_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Return recent events, optionally filtered by type.

        *event_type* filters to exactly one type; *event_types* filters to a
        set of types.  Returns rows ordered oldest-first so callers get a
        natural time series.
        """
        if self._db is None:
            return []
        try:
            if event_type is not None:
                cursor = await self._db.execute(
                    """
                    SELECT id, timestamp, event_type, details
                    FROM events
                    WHERE event_type = ?
                    ORDER BY timestamp DESC
                    LIMIT ?;
                    """,
                    (event_type, limit),
                )
            elif event_types is not None:
                placeholders = ",".join("?" for _ in event_types)
                cursor = await self._db.execute(
                    f"""
                    SELECT id, timestamp, event_type, details
                    FROM events
                    WHERE event_type IN ({placeholders})
                    ORDER BY timestamp DESC
                    LIMIT ?;
                    """,
                    (*event_types, limit),
                )
            else:
                cursor = await self._db.execute(
                    """
                    SELECT id, timestamp, event_type, details
                    FROM events
                    ORDER BY timestamp DESC
                    LIMIT ?;
                    """,
                    (limit,),
                )
            rows = await cursor.fetchall()
            return [
                {"id": r[0], "timestamp": r[1], "event_type": r[2], "details": r[3]}
                for r in rows
            ]
        except Exception as exc:
            logger.warning("get_events failed: %s", exc)
            return []

    async def get_aggregates(self, hours: float) -> Dict[str, Any]:
        """Compute aggregate statistics over the last *hours* hours.

        Returns a dict with:
        - ``job_success_rate`` — fraction of job_completed / (job_completed + job_failed)
        - ``avg_execution_ms`` — mean execution_ms from job_completed events
        - ``p95_execution_ms`` — 95th-percentile execution_ms
        - ``error_rate_per_minute`` — error events per minute in the window
        """
        if self._db is None:
            return {}
        try:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(hours=hours)
            ).isoformat()

            # Fetch all job events in window
            cursor = await self._db.execute(
                """
                SELECT event_type, details
                FROM events
                WHERE event_type IN ('job_completed', 'job_failed')
                  AND timestamp >= ?
                ORDER BY timestamp ASC;
                """,
                (cutoff,),
            )
            job_rows = await cursor.fetchall()

            completed = 0
            failed = 0
            exec_times: List[float] = []
            for event_type, details_json in job_rows:
                if event_type == "job_completed":
                    completed += 1
                    try:
                        d = json.loads(details_json)
                        if "execution_ms" in d and d["execution_ms"] is not None:
                            exec_times.append(float(d["execution_ms"]))
                    except Exception:
                        pass
                else:
                    failed += 1

            total_jobs = completed + failed
            job_success_rate = completed / total_jobs if total_jobs > 0 else 0.0

            avg_execution_ms: Optional[float] = None
            p95_execution_ms: Optional[float] = None
            if exec_times:
                avg_execution_ms = statistics.mean(exec_times)
                sorted_times = sorted(exec_times)
                idx = int(len(sorted_times) * 0.95)
                p95_execution_ms = sorted_times[min(idx, len(sorted_times) - 1)]

            # Error events per minute
            error_types = list(ERROR_EVENT_TYPES)
            placeholders = ",".join("?" for _ in error_types)
            cursor = await self._db.execute(
                f"""
                SELECT COUNT(*)
                FROM events
                WHERE event_type IN ({placeholders})
                  AND timestamp >= ?;
                """,
                (*error_types, cutoff),
            )
            row = await cursor.fetchone()
            error_count = row[0] if row else 0
            window_minutes = hours * 60.0
            error_rate_per_minute = error_count / window_minutes if window_minutes > 0 else 0.0

            return {
                "job_success_rate": job_success_rate,
                "avg_execution_ms": avg_execution_ms,
                "p95_execution_ms": p95_execution_ms,
                "error_rate_per_minute": error_rate_per_minute,
            }
        except Exception as exc:
            logger.warning("get_aggregates failed: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    async def prune(self, retention_days: int) -> None:
        """Delete metrics and events older than *retention_days* days."""
        if self._db is None:
            logger.warning("prune called on closed MetricsStore — skipping")
            return
        try:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=retention_days)
            ).isoformat()
            await self._db.execute(
                "DELETE FROM metrics WHERE timestamp < ?;", (cutoff,)
            )
            await self._db.execute(
                "DELETE FROM events WHERE timestamp < ?;", (cutoff,)
            )
            await self._db.commit()
        except Exception as exc:
            logger.warning("prune failed: %s", exc)
