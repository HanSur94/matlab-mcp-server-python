# MCP Tools Reference

The server exposes 14 built-in tools plus any custom tools defined in your `custom_tools.yaml`.

## Code Execution

### `execute_code`

Execute MATLAB code in the session's engine.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `code` | string | yes | MATLAB code to execute |

**Behavior:**
- Runs synchronously if it completes within `sync_timeout` (default 30s)
- Auto-promotes to async if it exceeds the timeout
- Returns inline result for sync, or `job_id` for async

**Example response (sync):**
```json
{
  "status": "completed",
  "output": "ans =\n    15",
  "execution_time": 0.23
}
```

**Example response (async promotion):**
```json
{
  "status": "running",
  "job_id": "abc123-def456",
  "message": "Job promoted to async execution"
}
```

### `check_code`

Lint MATLAB code using `checkcode`/`mlint`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `code` | string | yes | MATLAB code to check |

**Example response:**
```json
{
  "issues": [
    {
      "line": 3,
      "column": 5,
      "message": "Variable 'x' might be unused",
      "severity": "warning"
    }
  ],
  "summary": "1 warning(s), 0 error(s)"
}
```

### `get_workspace`

Get variables in the current MATLAB workspace.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | — | — | — |

Returns the output of MATLAB's `whos` command.

## Async Job Management

### `get_job_status`

Get status and progress of a running job.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `job_id` | string | yes | Job ID from `execute_code` |

**Example response:**
```json
{
  "job_id": "abc123",
  "status": "running",
  "progress": 65.0,
  "message": "Trial 650000/1000000",
  "elapsed_seconds": 120.5
}
```

### `get_job_result`

Get the full result of a completed job.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `job_id` | string | yes | Job ID |

### `cancel_job`

Cancel a pending or running job.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `job_id` | string | yes | Job ID |

### `list_jobs`

List all jobs in the current session.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | — | — | — |

## Discovery

### `list_toolboxes`

List available MATLAB toolboxes (filtered by config).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | — | — | — |

### `list_functions`

List functions in a specific toolbox.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `toolbox_name` | string | yes | Name of the toolbox |

### `get_help`

Get MATLAB help text for any function.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `function_name` | string | yes | Function name |

## File Management

### `upload_data`

Upload a data file to the session's temp directory.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filename` | string | yes | Target filename |
| `content_base64` | string | yes | File content, base64-encoded |

**Limits:** Max upload size is configurable (default 100MB). Filenames are sanitized to prevent path traversal.

### `delete_file`

Delete a file from the session's temp directory.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `filename` | string | yes | File to delete |

### `list_files`

List files in the session's temp directory.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | — | — | — |

## Admin

### `get_pool_status`

Get the current engine pool status.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | — | — | — |

**Example response:**
```json
{
  "total_engines": 4,
  "available": 2,
  "busy": 2,
  "max_engines": 10
}
```
