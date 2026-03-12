# Async Jobs

Long-running MATLAB code is automatically handled through the async job system.

## How It Works

1. You call `execute_code` with your MATLAB code
2. The server starts executing synchronously
3. If execution exceeds `sync_timeout` (default 30 seconds), the job is **promoted to async**
4. You get back a `job_id` immediately
5. Poll `get_job_status` for progress updates
6. Call `get_job_result` when the job completes

## Job Lifecycle

```
PENDING → RUNNING → COMPLETED
                  → FAILED
                  → CANCELLED
```

## Progress Reporting

Use the `mcp_progress()` helper function in your MATLAB code to report progress back to the agent:

```matlab
mcp_progress(__mcp_job_id__, percentage, message)
```

- `__mcp_job_id__` — automatically injected into the workspace by the server
- `percentage` — number from 0 to 100
- `message` — optional status message

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

The agent sees:
```
get_job_status → {progress: 10, message: "Processed 100000/1000000 items"}
get_job_status → {progress: 50, message: "Processed 500000/1000000 items"}
get_job_status → {progress: 100, message: "Processed 1000000/1000000 items"}
get_job_result → {output: "0.5023", status: "completed"}
```

## How Progress Works Internally

1. `mcp_progress.m` writes a JSON file to `MCP_TEMP_DIR/<job_id>.progress`
2. `get_job_status` reads this file and includes progress in the response
3. The file is cleaned up when the job completes

## Job Management Tools

| Tool | Description |
|------|-------------|
| `get_job_status` | Current status + progress percentage |
| `get_job_result` | Full result of a completed job |
| `cancel_job` | Cancel a pending or running job |
| `list_jobs` | List all jobs in the session |

## Configuration

```yaml
execution:
  sync_timeout: 30           # Seconds before async promotion
  max_execution_time: 86400  # Hard limit (24h)

sessions:
  job_retention_seconds: 86400  # Keep job metadata for 24h
```

## Tips

- **Short code (< 30s):** Results return inline, no job ID needed
- **Medium code (30s - minutes):** Auto-promoted, poll with `get_job_status`
- **Long code (hours):** Add `mcp_progress()` calls so the agent can report status
- **Cancel:** Call `cancel_job` if you need to stop a running job
- **Increase timeout:** Set `sync_timeout: 60` if most of your code takes 30-60s
