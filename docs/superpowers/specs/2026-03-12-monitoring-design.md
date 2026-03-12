# MATLAB MCP Server — Monitoring Design Spec

## Goal

Add integrated monitoring to the MATLAB MCP server: a metrics collector with SQLite storage, HTTP health/metrics endpoints, a Plotly.js dashboard with historical trends, and enriched MCP tools for agent self-monitoring.

## Requirements Summary

- **Ops dashboard** — single-page web UI with live gauges, time-series charts, and event log
- **Health endpoint** — `/health` and `/metrics` JSON endpoints for load balancers and scripts
- **MCP tool enrichment** — `get_server_metrics`, `get_server_health`, `get_error_log` tools
- **Historical data** — SQLite time-series storage with configurable retention
- **Auth** — relies on reverse proxy (same as SSE transport recommendation)

---

## 1. Metrics Collection

### MetricsCollector

A background asyncio task that samples server state at a configurable interval (default 10 seconds).

**Sampled metrics:**

| Category | Metric | Source |
|----------|--------|--------|
| pool | total_engines | `pool.get_status()` |
| pool | available_engines | `pool.get_status()` |
| pool | busy_engines | `pool.get_status()` |
| pool | max_engines | `pool.get_status()` |
| pool | utilization_pct | `busy / total * 100` |
| jobs | active_count | `tracker.list_jobs()` filtered by PENDING/RUNNING |
| jobs | completed_total | cumulative counter |
| jobs | failed_total | cumulative counter |
| jobs | cancelled_total | cumulative counter |
| jobs | avg_execution_ms | rolling average from last 100 completed jobs |
| jobs | p95_execution_ms | 95th percentile from last 100 completed jobs |
| sessions | active_count | `sessions.session_count` |
| sessions | total_created | cumulative counter |
| errors | total | cumulative counter |
| errors | blocked_attempts | cumulative counter from security validator |
| errors | health_check_failures | cumulative counter from pool health checks |
| system | memory_mb | `psutil.Process().memory_info().rss / 1e6` |
| system | cpu_percent | `psutil.Process().cpu_percent()` |

**Cumulative counters:** The collector maintains in-memory counters that increment on events. These are persisted to SQLite each sample. On server restart, counters reset to 0 (the time-series history is preserved in SQLite).

**`avg_execution_ms` window:** Rolling average over the last 100 completed jobs (in-memory ring buffer). Resets to 0 on server restart. If fewer than 100 jobs have completed, averages over all completed jobs so far.

**`p95_execution_ms`:** 95th percentile from the same 100-job ring buffer. Stored alongside `avg_execution_ms` each sample.

**`sessions.total_created`:** Incremented via a `collector.record_event("session_created", ...)` callback from `SessionManager.create_session()`. The collector maintains the cumulative counter in memory.

**`uptime_seconds`:** Calculated as `time.time() - collector.start_time`, where `start_time` is recorded when the `MetricsCollector` is constructed.

**System metrics fallback:** If `psutil` is not installed, `memory_mb` and `cpu_percent` return `null`. No error, no warning at sample time (a single info-level log at startup noting psutil is unavailable).

### Event Recording

Discrete events are recorded to the `events` table when they occur (not on the sample interval):

| Event Type | Trigger | Details |
|------------|---------|---------|
| `engine_scale_up` | Pool starts a new engine | `{"engine_id": "...", "total_after": N}` |
| `engine_scale_down` | Pool stops an idle engine | `{"engine_id": "...", "total_after": N}` |
| `engine_crash` | Health check finds dead engine | `{"engine_id": "...", "error": "..."}` |
| `engine_replaced` | Dead engine replaced by new one | `{"old_id": "...", "new_id": "..."}` |
| `session_created` | New session created | `{"session_id_short": "a1b2c3d4"}` |
| `blocked_function` | Security validator blocks code | `{"function": "system", "session_id_short": "a1b2c3d4"}` |
| `job_completed` | Job finishes successfully | `{"job_id": "...", "execution_ms": N}` |
| `job_failed` | Job finishes with error | `{"job_id": "...", "error": "..."}` |
| `health_check_fail` | Engine health check fails | `{"engine_id": "...", "error": "..."}` |

**Session ID privacy:** Event details use `session_id_short` (last 8 characters of the session ID) to avoid leaking full session IDs in the dashboard and error logs.

**Integration — collector injection pattern:**

`MetricsCollector` is constructed in `MatlabMCPServer.__init__()` — before pool, executor, and other components. It holds the in-memory counters and the `MetricsStore` reference. The background sampling task is not started until `lifespan`, but the object exists and can receive `record_event()` calls immediately.

Existing components receive the collector as an optional constructor argument:

```python
class MatlabMCPServer:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        # Collector created FIRST
        self.collector = MetricsCollector(config) if config.monitoring.enabled else None
        # Then components that use it
        self.pool = EnginePoolManager(config, collector=self.collector)
        self.tracker = JobTracker(...)
        self.executor = JobExecutor(pool=self.pool, tracker=self.tracker, config=config, collector=self.collector)
        self.sessions = SessionManager(config, collector=self.collector)
        self.security = SecurityValidator(config.security, collector=self.collector)
        self.formatter = ResultFormatter(config)
```

When `collector` is `None` (monitoring disabled), components skip the `record_event()` call — a simple `if self.collector:` guard at each call site.

---

## 2. SQLite Storage

### MetricsStore

Single SQLite file at `monitoring.db_path` (default `./monitoring/metrics.db`).

**Schema:**

```sql
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,          -- ISO 8601
    category TEXT NOT NULL,           -- pool, jobs, sessions, errors, system
    metric_name TEXT NOT NULL,        -- e.g. utilization_pct
    value REAL                        -- nullable (for psutil fallback)
);

CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_metrics_cat_name ON metrics(category, metric_name);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,          -- ISO 8601
    event_type TEXT NOT NULL,
    details TEXT NOT NULL             -- JSON string
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
```

**Write operations:**
- `insert_metrics(timestamp, metrics_dict)` — batch insert all sampled metrics for one timestamp
- `insert_event(event_type, details_dict)` — insert a single event

**Read operations:**
- `get_latest()` — most recent metrics sample (all metrics at the latest timestamp)
- `get_history(metric_name, hours)` — time-series for a specific metric over N hours
- `get_events(limit, event_type=None)` — recent events, optionally filtered by type
- `get_aggregates(hours)` — computed aggregates from stored metrics and events rows:
  ```python
  {
      "job_success_rate": 0.97,       # completed / (completed + failed) from events
      "avg_execution_ms": 2100,       # mean of jobs.avg_execution_ms metric samples
      "p95_execution_ms": 5400,       # mean of jobs.p95_execution_ms metric samples
      "error_rate_per_minute": 0.08   # count of error events / time window in minutes
  }
  ```

**Retention pruning:**
- `prune(retention_days)` — async method, deletes rows from both tables where `timestamp` is older than `retention_days`
- Called from the existing cleanup loop with `await store.prune(retention_days)` (the cleanup loop is already async)

**Error handling:** All `MetricsStore` write operations (`insert_metrics`, `insert_event`) catch exceptions, log a warning, and return silently — monitoring failures must never crash the server. Read failures in HTTP endpoints return an empty result set with HTTP 200 (not 500), plus a `"warning": "metrics unavailable"` field.

**Thread safety:** All SQLite access goes through `MetricsStore` which uses `aiosqlite` for async access.

**New dependency:** `aiosqlite>=0.19.0` (lightweight async SQLite wrapper).

---

## 3. Health Evaluation

### Health Logic (`health.py`)

Evaluates current server state and returns one of three statuses:

| Status | Condition |
|--------|-----------|
| `healthy` | All normal |
| `degraded` | Pool utilization > 90%, OR any engine in error state, OR error rate > 5/min |
| `unhealthy` | 0 available engines AND queue full, OR all engines in error state |

**`evaluate_health(pool, tracker, collector)`** returns:

```python
{
    "status": "healthy" | "degraded" | "unhealthy",
    "uptime_seconds": float,
    "issues": ["Pool utilization at 95%"],  # empty list if healthy
    "engines": {"total": 4, "available": 2, "busy": 2},
    "active_jobs": 3,
    "active_sessions": 2
}
```

The health evaluation reads live state (not SQLite) for real-time accuracy.

---

## 4. HTTP Endpoints

### Routes (`routes.py`)

**`GET /health`**

Returns health evaluation as JSON. HTTP status: `200` if healthy/degraded, `503` if unhealthy.

Response body: same as `evaluate_health()` output above.

**`GET /metrics`**

Returns comprehensive metrics snapshot as JSON. Always `200`.

```json
{
    "timestamp": "2026-03-12T14:30:00Z",
    "pool": {
        "total": 4, "available": 2, "busy": 2,
        "max": 10, "utilization_pct": 50.0
    },
    "jobs": {
        "active": 3, "completed_total": 142,
        "failed_total": 5, "cancelled_total": 2,
        "avg_execution_ms": 2340
    },
    "sessions": {
        "active": 2, "total_created": 15
    },
    "errors": {
        "total": 5, "blocked_attempts": 1,
        "health_check_failures": 0
    },
    "system": {
        "memory_mb": 1240.5, "cpu_percent": 12.5
    }
}
```

### Transport Integration

**SSE transport:** Routes are mounted on the same Starlette/ASGI app that FastMCP uses. No extra port.

**stdio transport:** A Starlette ASGI app is started on `monitoring.http_port` (default 8766) using uvicorn in a background asyncio task. Both Starlette and uvicorn are already transitive dependencies of FastMCP — no new dependencies needed. The monitoring HTTP server is started inside the `lifespan` function using `asyncio.create_task()` to run a uvicorn `Server` instance:

```python
# Inside lifespan, after collector starts:
if config.server.transport == "stdio" and config.monitoring.enabled:
    monitoring_app = create_monitoring_app(state)
    uvi_config = uvicorn.Config(monitoring_app, host="127.0.0.1", port=config.monitoring.http_port, log_level="warning")
    monitoring_server = uvicorn.Server(uvi_config)
    monitoring_task = asyncio.create_task(monitoring_server.serve())
```

On shutdown, `monitoring_server.should_exit = True` and the task is awaited.

If `dashboard_enabled: false`, only `/health` and `/metrics` are served (no static files).

---

## 5. Dashboard

### Static Web UI (`dashboard.py` + `static/`)

Served at `GET /dashboard`. Single HTML page with inline or co-located JS/CSS.

**Plotly.js** loaded from CDN by default (`https://cdn.plot.ly/plotly-2.35.0.min.js`). For air-gapped/enterprise environments, a minified copy of Plotly.js is also bundled in `static/vendor/plotly.min.js`. The dashboard HTML tries the local copy first, falls back to CDN. No build step.

**Layout:**

```
┌──────────────────────────────────────────────────┐
│  MATLAB MCP Server Dashboard    ● Healthy  Up 2h │
├──────────┬──────────┬──────────┬─────────────────┤
│ Pool     │ Active   │ Active   │ Errors/min      │
│ 50%      │ Jobs: 3  │ Sess: 2  │ 0.2             │
│ [gauge]  │          │          │                 │
├──────────┴──────────┴──────────┴─────────────────┤
│ Time range: [1h] [6h] [24h] [7d]                 │
├──────────────────────┬───────────────────────────┤
│ Pool Utilization     │ Job Throughput             │
│ [area chart]         │ [bar chart]               │
├──────────────────────┼───────────────────────────┤
│ Execution Time       │ Active Sessions            │
│ [line: avg, p95]     │ [line chart]              │
├──────────────────────┼───────────────────────────┤
│ Memory Usage         │                           │
│ [line chart]         │                           │
├──────────────────────┴───────────────────────────┤
│ Recent Events                          [filter ▼]│
│ 14:30:02  engine_scale_up  Engine 5 started      │
│ 14:28:15  job_completed    Job abc123 (2.3s)     │
│ 14:25:01  blocked_function system() blocked      │
│ ...                                              │
└──────────────────────────────────────────────────┘
```

**Dashboard API routes** (JSON, consumed by the frontend):

| Route | Description |
|-------|-------------|
| `GET /dashboard/api/current` | Latest metrics snapshot (same as `/metrics`) |
| `GET /dashboard/api/history?metric=<name>&hours=<N>` | Time-series data for one metric |
| `GET /dashboard/api/events?limit=<N>&type=<type>` | Recent events, optionally filtered |

**Auto-refresh:** Frontend polls `/dashboard/api/current` every 10 seconds. Charts refresh when new data arrives. Time range selector re-fetches history for selected range.

### Dashboard Serving

`dashboard.py` creates a Starlette sub-application:
- `GET /dashboard` → serves `index.html`
- `GET /dashboard/static/{path}` → serves JS/CSS files
- `GET /dashboard/api/*` → JSON API routes

This sub-app is mounted on the main ASGI app (SSE) or the monitoring HTTP server (stdio).

---

## 6. MCP Tool Enrichment

Three new tools registered in `server.py`:

### `get_server_metrics`

```python
@mcp.tool
async def get_server_metrics(ctx: Context) -> dict:
    """Get comprehensive server metrics including pool, jobs, sessions, and system stats."""
```

Returns the same structure as `GET /metrics`. Reads from the collector's current state + SQLite for cumulative counters.

### `get_server_health`

```python
@mcp.tool
async def get_server_health(ctx: Context) -> dict:
    """Get server health status with issue detection. Returns healthy/degraded/unhealthy."""
```

Returns the same structure as `GET /health`. Uses `evaluate_health()` from `health.py`.

### `get_error_log`

```python
@mcp.tool
async def get_error_log(ctx: Context, limit: int = 20) -> dict:
    """Get recent server errors and notable events for diagnosing issues."""
```

Returns only error-class events, filtered to types: `job_failed`, `blocked_function`, `engine_crash`, `health_check_fail`. Operational events (`engine_scale_up`, `job_completed`, etc.) are excluded.

```json
{
    "events": [
        {"timestamp": "...", "event_type": "job_failed", "details": {...}},
        {"timestamp": "...", "event_type": "blocked_function", "details": {...}}
    ],
    "total_errors_24h": 5
}
```

Reads from the `events` table via `MetricsStore` with a type filter.

---

## 7. Configuration

New `monitoring` section in `config.yaml`:

```yaml
monitoring:
  enabled: true                  # Master switch — disables all monitoring
  sample_interval: 10            # Seconds between metric samples
  retention_days: 7              # Days to keep historical data
  db_path: "./monitoring/metrics.db"
  dashboard_enabled: true        # Serve the web dashboard
  http_port: 8766                # Dashboard/health port (stdio transport only)
```

Environment variable overrides follow existing pattern:
```bash
MATLAB_MCP_MONITORING_ENABLED=true
MATLAB_MCP_MONITORING_SAMPLE_INTERVAL=5
MATLAB_MCP_MONITORING_RETENTION_DAYS=30
MATLAB_MCP_MONITORING_DB_PATH=/var/data/metrics.db
MATLAB_MCP_MONITORING_DASHBOARD_ENABLED=false
MATLAB_MCP_MONITORING_HTTP_PORT=9090
```

When `monitoring.enabled: false`, no background collector runs, no SQLite database is created, no HTTP endpoints are mounted, and the three MCP tools return `{"error": "Monitoring is disabled"}`.

---

## 8. Module Structure

```
src/matlab_mcp/monitoring/
├── __init__.py
├── collector.py          # MetricsCollector background task + event recording
├── store.py              # MetricsStore — async SQLite read/write/prune
├── health.py             # evaluate_health() logic
├── routes.py             # HTTP route handlers (/health, /metrics)
├── dashboard.py          # Dashboard sub-app + API routes
└── static/
    ├── index.html        # Dashboard page
    ├── dashboard.js      # Plotly.js chart rendering, polling, time range
    ├── style.css         # Dashboard styling
    └── vendor/
        └── plotly.min.js # Bundled Plotly.js for air-gapped environments
```

**Integration changes to existing files:**

| File | Change |
|------|--------|
| `config.py` | Add `MonitoringConfig` pydantic model + add to `AppConfig`. Add `self.monitoring.db_path` to `resolve_paths()` |
| `server.py` | Construct `MetricsCollector` in `MatlabMCPServer.__init__()` (before other components). Start sampling task in lifespan. Mount routes. Register 3 MCP tools |
| `server.py` cleanup_loop | Add `await store.prune(retention_days)` call |
| `pool/manager.py` | Accept optional `collector` arg. Call `collector.record_event()` on scale up/down/crash/replace |
| `security/validator.py` | Accept optional `collector` arg. Call `collector.record_event()` on blocked function |
| `jobs/executor.py` | Accept optional `collector` arg. Call `collector.record_event()` on job completion/failure |
| `session/manager.py` | Accept optional `collector` arg. Call `collector.record_event("session_created", ...)` in `create_session()` |
| `pyproject.toml` | Add `aiosqlite>=0.19.0` dependency, `psutil` as optional |

---

## 9. New Dependencies

| Package | Required | Purpose |
|---------|----------|---------|
| `aiosqlite>=0.19.0` | yes | Async SQLite access |
| `psutil>=5.9.0` | optional | System metrics (memory, CPU) |

`psutil` is listed as an optional extra in `pyproject.toml`:
```toml
[project.optional-dependencies]
monitoring = ["psutil>=5.9.0"]
```

---

## 10. Startup & Shutdown

**Startup (when monitoring enabled):**
1. Create monitoring directory (`db_path` parent)
2. Initialize `MetricsStore` (create tables if not exists)
3. Start `MetricsCollector` background task
4. Mount HTTP routes on ASGI app (SSE) or start monitoring HTTP server (stdio)

**Shutdown:**
1. Stop collector background task
2. Flush any pending writes
3. Close SQLite connection
4. Stop monitoring HTTP server (stdio only)
