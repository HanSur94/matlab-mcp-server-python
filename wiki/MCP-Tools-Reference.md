# MCP Tools Reference

The server exposes **20 built-in tools** plus any user-defined tools declared in your `custom_tools.yaml`.

Every tool also receives a framework-injected `ctx: Context` as its first argument. That is supplied by FastMCP, not by the caller, so it is omitted from the parameter tables below. See [Configuration](Configuration) for the config keys referenced here and [Installation](Installation) for setup.

**Tool categories:**

| Category | Tools |
|----------|-------|
| Code execution | `execute_code`, `check_code`, `get_workspace` |
| Job management | `get_job_status`, `get_job_result`, `cancel_job`, `list_jobs` |
| Discovery | `list_toolboxes`, `list_functions`, `get_help` |
| File management | `upload_data`, `delete_file`, `list_files` |
| File reading | `read_script`, `read_data`, `read_image` |
| Admin | `get_pool_status` |
| Monitoring | `get_server_metrics`, `get_server_health`, `get_error_log` |
| Custom | Any tool defined in `custom_tools.yaml` |

---

## Code Execution

### `execute_code`

Execute MATLAB code in the session's engine.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `code` | string | yes | MATLAB code to execute |

**Behavior:**
- Runs synchronously if it completes within `execution.sync_timeout` (default 30s).
- Auto-promotes to an async job if it exceeds the timeout — poll it with `get_job_status` / `get_job_result`.
- Code is validated against the blocked-function list before running; a violation returns a `failed` status with a structured `error` and no `job_id`.
- If human-in-the-loop approval is enabled (`hitl`), the call may return `{"status": "denied", "message": ...}`.

**Example response (completed):**
```json
{
  "status": "completed",
  "job_id": "abc123-def456",
  "text": "ans =\n    15",
  "variables": {},
  "figures": [],
  "files": []
}
```

**Example response (async promotion / pending):**
```json
{
  "status": "pending",
  "job_id": "abc123-def456"
}
```

### `check_code`

Lint MATLAB code via `checkcode` / `mlint`. The code is written to a temp `.m` file and analyzed with the bundled `mcp_checkcode` helper.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `code` | string | yes | MATLAB code to check |

**Returns:** `{"status": "completed", "issues": [...]}` when the checker output parses as JSON, otherwise `{"status": "completed", "issues": [], "raw": "<text>"}`. Pending/failed executor states pass through unchanged.

### `get_workspace`

Get variables in the current session's MATLAB workspace (runs `whos`).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | — | — | — |

---

## Job Management

### `get_job_status`

Get status, timing, and (for running jobs) progress.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `job_id` | string | yes | Job ID from `execute_code` |

**Returns:** `job_id`, `status`, `session_id`, `created_at`, `started_at`, `completed_at`, `elapsed_seconds`, and — for running jobs that write a `<job_id>.progress` file — a `progress` string. Unknown IDs return `{"job_id": ..., "status": "not_found"}`.

### `get_job_result`

Get the full result of a completed job.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `job_id` | string | yes | Job ID |

**Returns:** `{"status": "completed", "result": {...}}` for completed jobs, `{"status": "failed", "error": {...}}` for failed ones, or a `not_found` / "result not yet available" message otherwise.

### `cancel_job`

Cancel a pending or running job.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `job_id` | string | yes | Job ID |

**Returns:** `{"job_id": ..., "status": "cancelled", "cancelled": true}` on success. Jobs not in `pending`/`running` state return `cancelled: false` with an explanatory message.

### `list_jobs`

List all jobs for the current session.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | — | — | — |

**Returns:** `{"session_id": ..., "jobs": [...], "count": N}`, each job summarized with `job_id`, `status`, timestamps, and `elapsed_seconds`.

---

## Discovery

### `list_toolboxes`

List installed MATLAB toolboxes by running `ver`. Results are annotated with the configured toolbox filter (`toolboxes.mode` / `toolboxes.list`).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | — | — | — |

**Returns:** `status`, `job_id`, `text` (the `ver` output), plus `toolbox_mode` and `toolbox_list`.

### `list_functions`

List functions in a toolbox by running `help <toolbox_name>`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `toolbox_name` | string | yes | Name of the toolbox |

**Returns:** `toolbox_name`, `status`, `job_id`, `text`. Invalid names (anything outside alphanumerics, underscores, dots, slashes, spaces) return a `failed` status.

### `get_help`

Get MATLAB help text for a function by running `help <function_name>`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `function_name` | string | yes | Function name |

**Returns:** `function_name`, `status`, `job_id`, `text`.

---

## File Management

All file tools operate **only** within the session's temporary directory. Filenames are basenames — path separators are rejected by filename sanitization to prevent traversal.

### `upload_data`

Upload a data file to the session temp directory.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filename` | string | yes | Target filename (basename only) |
| `content_base64` | string | yes | File content, base64-encoded |

**Limits:** max size is `security.max_upload_size_mb` (default 100 MB). Returns `{"status": "ok", "filename", "path", "size_bytes"}`. If `hitl.protect_file_ops` is enabled, may return `{"status": "denied", ...}`.

### `delete_file`

Delete a file from the session temp directory.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filename` | string | yes | File to delete (basename only) |

**Returns:** `{"status": "ok", "filename", "message"}`, or an error if the file is missing. Subject to `hitl.protect_file_ops`.

### `list_files`

List files in the session temp directory.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | — | — | — |

**Returns:** `{"files": [{"name", "size", "path"}, ...], "count": N}`.

---

## File Reading

### `read_script`

Read a MATLAB `.m` script from the session temp directory. The `.m` extension is enforced.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filename` | string | yes | `.m` file to read (basename only) |

**Returns:** `{"status": "ok", "filename", "content"}`. Content beyond `output.max_inline_text_length` (default 50000 chars) is truncated with a `message`.

### `read_data`

Read a data file from the session temp directory.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filename` | string | yes | Data file to read (basename only) |
| `format` | string | no | `summary` (default) or `raw` |

**Supported extensions:** `.mat`, `.xlsx`, `.csv`, `.txt`, `.json`, `.yaml`, `.yml`, `.xml`.

**Behavior by type:**
- `.mat`, `format=summary`: variable names/sizes/types via MATLAB `whos('-file', ...)` (requires a running engine).
- `.mat`, `format=raw` (or no executor): base64-encoded content with `encoding: "base64"` and `size_bytes`.
- `.xlsx`: always base64-encoded (binary).
- Text types (`.csv`, `.txt`, `.json`, `.yaml`, `.yml`, `.xml`): inline UTF-8 text (falls back to latin-1), truncated past `output.max_inline_text_length`.

Files larger than `security.max_upload_size_mb` are rejected.

### `read_image`

Read an image file from the session temp directory and return it as an inline image content block that renders in agent UIs.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filename` | string | yes | Image file (basename only) |

**Supported extensions:** `.png`, `.jpg`, `.jpeg`, `.gif`. Files larger than `security.max_upload_size_mb` are rejected. On success returns a FastMCP `Image`; on error returns a dict with a `message`.

---

## Admin

### `get_pool_status`

Get the current engine pool status.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | — | — | — |

**Example response:**
```json
{
  "total": 4,
  "available": 2,
  "busy": 2,
  "max": 10
}
```

---

## Monitoring

Monitoring tools require `monitoring.enabled = true`; otherwise they return `{"error": "Monitoring is disabled"}`.

### `get_server_metrics`

Snapshot of pool, jobs, sessions, and system metrics.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | — | — | — |

**Example response:**
```json
{
  "pool": {"total": 2, "available": 1, "busy": 1, "max": 10, "utilization_pct": 50.0},
  "jobs": {"active": 1, "completed_total": 47, "failed_total": 2, "avg_execution_ms": 28.5},
  "sessions": {"total_created": 5, "active": 3},
  "errors": {"total": 2, "blocked_attempts": 0},
  "system": {"uptime_seconds": 3600.1, "memory_mb": 108.8, "cpu_percent": 12.3}
}
```

### `get_server_health`

Health status with issue detection.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | — | — | — |

**Status values:** `healthy`, `degraded`, `unhealthy`.

### `get_error_log`

Recent error-class events (`job_failed`, `blocked_function`, `engine_crash`, `health_check_fail`) plus a 24-hour error count.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `limit` | integer | no | Max events to return (default 20) |

**Returns:** `{"events": [...], "total_errors_24h": N}`.

---

## Custom Tools

Beyond the 20 built-ins, you can register your own MATLAB-backed tools without writing Python. They are loaded at startup from the YAML file at `custom_tools.config_file` (default `./custom_tools.yaml`) under a top-level `tools:` list.

Each tool definition supports:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | MCP tool name |
| `matlab_function` | string | yes | MATLAB function invoked when the tool is called |
| `description` | string | no | Shown in MCP tool listings |
| `parameters` | list | no | List of parameter definitions (see below) |
| `returns` | string | no | Description of the return value |

Each entry in `parameters` has:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Parameter name (valid identifier) |
| `type` | string | no | One of `str`/`string`, `int`/`integer`, `float`/`number`, `bool`/`boolean`, `list`, `dict`, `any` (default `str`) |
| `required` | bool | no | Whether the parameter is required (default `true`) |
| `default` | any | no | Default value when not required |

At call time the arguments are converted to MATLAB literals and interpolated into `matlab_function(...)`. String values are single-quote-escaped to prevent injection.

**Example `custom_tools.yaml`:**
```yaml
tools:
  - name: compute_fft
    matlab_function: my_fft_wrapper
    description: Run an FFT over a named workspace variable
    parameters:
      - name: signal_var
        type: str
        required: true
      - name: n_points
        type: int
        required: false
        default: 1024
    returns: FFT magnitude spectrum
```
