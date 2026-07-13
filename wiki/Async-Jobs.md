# Async Jobs

Every `execute_code` call is tracked as a **job**. Short code returns its result inline; long-running code is automatically promoted to a background job that you poll for. This page documents the real state machine, the promotion rule, and the job-management tools.

See also: [MCP Tools Reference](MCP-Tools-Reference), [Configuration](Configuration).

## Sync vs. auto-async

`execute_code` uses a hybrid model. Internally, *every* call creates a job, acquires an engine, and starts the MATLAB code in the background. The difference is only how long the server waits before handing control back to you:

1. You call `execute_code` with your MATLAB code.
2. The server creates a job (`j-<uuid>`), acquires an engine, and starts execution.
3. It waits up to `execution.sync_timeout` seconds (default **30**) for the code to finish.
   - **Finishes in time** → the full result is returned inline with `status: "completed"`. No polling needed.
   - **Still running at the timeout** → the job is **promoted to async**: you immediately get back `status: "pending"` and a `job_id`, and execution continues in the background.
4. For a promoted job, poll `get_job_status` and then fetch the result with `get_job_result`.

Special case: if `sync_timeout` is set to `0`, the job is promoted to async immediately without any inline wait.

> Note: the `status` field in the `execute_code` *response* is a coarse hint (`completed` / `pending` / `failed`). It is not the same as the job's lifecycle status. A promoted job's response says `pending`, but the job is actually already `running` (see below) — that is what `get_job_status` will report.

## Job lifecycle

A job (`src/matlab_mcp/jobs/models.py`) moves through five states. `COMPLETED`, `FAILED`, and `CANCELLED` are terminal.

```
PENDING ──> RUNNING ──> COMPLETED
   │           │──────> FAILED
   │           └──────> CANCELLED
   └──────────────────> CANCELLED
```

The only valid transitions are:

| From | To |
|------|-----|
| `PENDING` | `RUNNING`, `CANCELLED` |
| `RUNNING` | `COMPLETED`, `FAILED`, `CANCELLED` |
| terminal states | (none) |

| State | Meaning |
|-------|---------|
| `pending` | Job created, engine not yet acquired. |
| `running` | Engine acquired, MATLAB code executing. Every job — even one that returns inline — passes through this state. |
| `completed` | Finished successfully; `result` is populated. |
| `failed` | Raised an error or the engine failed to start execution; `error` (type / message / matlab_id / stack_trace) is populated. |
| `cancelled` | Cancelled via `cancel_job` or during server shutdown. |

Each job also records timestamps (`created_at`, `started_at`, `completed_at`) and exposes `elapsed_seconds`.

## Promotion & timeouts

- **Inline wait:** `execution.sync_timeout` (default `30` s). The wait is bounded by the MATLAB future's own `result(timeout=...)`, with an asyncio safety net one second longer.
- **Background limit:** once promoted, the background task waits up to `execution.max_execution_time` (default `86400` s = 24 h) for the future to resolve. Exceeding it marks the job `failed`.
- The engine is released back to the pool in every case — completion, failure, or cancellation.

## Job-management tools

All four tools live in `src/matlab_mcp/tools/jobs.py` and operate on the current session.

| Tool | Params | Returns |
|------|--------|---------|
| `get_job_status` | `job_id` | `status` plus `session_id`, timestamps, `elapsed_seconds`, and — for a running job — an optional `progress` string. |
| `get_job_result` | `job_id` | Full `result` when `completed`; `error` when `failed`; otherwise a message that the result is not yet available. |
| `cancel_job` | `job_id` | Cancels a `pending`/`running` job (cancels the underlying future, then marks it `cancelled`). Returns `cancelled: true/false`. |
| `list_jobs` | none | `jobs` array of summaries (id, status, timestamps, elapsed) plus `count`, for the current session. |

Notes:

- Querying an unknown `job_id` returns `status: "not_found"`.
- `cancel_job` on a job that is already terminal returns `cancelled: false` with an explanatory message.
- Jobs are retained after reaching a terminal state so you can still poll them; they are pruned once older than `sessions.job_retention_seconds` (default **86400** s = 24 h).

## Progress reporting

> **Currently non-operational.** The `mcp_progress` helper is shipped but does nothing as wired today. `mcp_progress.m` reads the target directory from the `MCP_TEMP_DIR` *environment variable* (`getenv('MCP_TEMP_DIR')`), but the server never sets that variable in the MATLAB process. The executor instead injects the temp dir as a *workspace variable* (`__mcp_temp_dir__`, via `engine.set_workspace_var`), which the helper does not read. As a result `mcp_progress` always hits its `isempty(temp_dir)` branch, warns `MCP_TEMP_DIR not set`, and writes no `.progress` file — so `get_job_status` will never surface a `progress` string. The rest of this section describes the intended design; treat it as not-yet-working until the code is fixed (e.g. `setenv('MCP_TEMP_DIR', temp_dir)` before execution).

For long jobs, the intent is that your MATLAB code reports progress with the bundled `mcp_progress` helper, and `get_job_status` surfaces whatever the job last wrote.

```matlab
mcp_progress(__mcp_job_id__, percentage, message)
```

- `__mcp_job_id__` — the job id, auto-injected into the workspace by the server for every job.
- `percentage` — clamped to 0–100.
- `message` — optional status string.

### Example

```matlab
n = 1e6;
results = zeros(n, 1);
for i = 1:n
    results(i) = process_item(i);
    if mod(i, 1e5) == 0
        mcp_progress(__mcp_job_id__, i/n*100, ...
            sprintf('Processed %d/%d items', i, n));
    end
end
disp(mean(results));
```

### How it works

1. `mcp_progress.m` writes a small JSON document (`percentage`, `message`, `timestamp`) to `<MCP_TEMP_DIR>/<job_id>.progress`. The target directory comes from the `MCP_TEMP_DIR` environment variable in the MATLAB process; if it is unset, the helper warns and does nothing.
2. When the job is `running`, `get_job_status` reads that file (from the session temp dir) and returns its contents as the raw `progress` string. The server does not re-parse it into fields — you receive the JSON text as written.
3. The server does not automatically delete the `.progress` file.

## Configuration

```yaml
execution:
  sync_timeout: 30          # Seconds to wait inline before promoting to async (0 = always async)
  max_execution_time: 86400 # Hard limit for a background job (24h)

sessions:
  job_retention_seconds: 86400  # Keep terminal-job metadata for 24h, then prune
```

## Tips

- **Fast code (< `sync_timeout`):** results come back inline; no `job_id` handling needed.
- **Slower code:** it auto-promotes at the timeout — capture the `job_id` and poll `get_job_status`, then `get_job_result`.
- **Very long code:** add `mcp_progress()` calls so the agent can report intermediate status.
- **Stopping work:** call `cancel_job` to abort a `pending`/`running` job.
- **Tuning:** raise `sync_timeout` (e.g. `60`) if most of your code lands just above the default, or set it to `0` to force everything through the background path.
