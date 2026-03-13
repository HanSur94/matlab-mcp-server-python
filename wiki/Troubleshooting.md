# Troubleshooting

## MATLAB Engine Won't Start

**Symptom:** `Engine start timeout` or `matlab.engine not found`

**Solutions:**

1. **Verify MATLAB Engine API is installed:**
   ```bash
   python -c "import matlab.engine; print('OK')"
   ```

2. **Install the Engine API:**
   ```bash
   cd /Applications/MATLAB_R2024a.app/extern/engines/python  # macOS
   pip install .
   ```

3. **Check MATLAB version:** Must be 2020b or later.

4. **Check PATH:** MATLAB must be on your system PATH, or set `matlab_root` in config:
   ```yaml
   pool:
     matlab_root: "/Applications/MATLAB_R2024a.app"
   ```

5. **Increase timeout:** If MATLAB is slow to start:
   ```yaml
   pool:
     engine_start_timeout: 300  # 5 minutes
   ```

## "Max engines exceeded" on macOS

**Symptom:** Warning about max engines on macOS

**Explanation:** MATLAB on macOS has a limit of ~4 concurrent engine instances. The server warns but respects your configured `max_engines`.

**Solution:** Set `max_engines: 4` on macOS:
```yaml
pool:
  max_engines: 4
```

## Connection Refused (SSE)

**Symptom:** Client can't connect to `http://localhost:8765/sse`

**Solutions:**

1. **Check the server is running:** `matlab-mcp --transport sse`
2. **Check port:** Default is 8765, verify in config
3. **Check host binding:** Use `0.0.0.0` for remote access, `127.0.0.1` for local only
4. **Firewall:** Ensure port 8765 is open

## Blocked Function Error

**Symptom:** `BlockedFunctionError: Function 'system' is blocked`

**Explanation:** The security validator blocks dangerous functions by default.

**Solutions:**

1. **Use MATLAB-native alternatives** instead of `system()`:
   - File operations: `dir`, `mkdir`, `copyfile`, `movefile`
   - Environment: `getenv`

2. **Disable blocklist** (not recommended for shared servers):
   ```yaml
   security:
     blocked_functions_enabled: false
   ```

3. **Remove specific functions from blocklist:**
   ```yaml
   security:
     blocked_functions:
       - "unix"
       - "dos"
       # system removed from list
   ```

## Job Stuck in "Running" State

**Symptom:** Job never completes, progress stops updating

**Solutions:**

1. **Cancel the job:**
   Ask your agent to call `cancel_job` with the job ID

2. **Check max execution time:**
   ```yaml
   execution:
     max_execution_time: 86400  # 24h hard limit
   ```

3. **Check MATLAB code:** Is there an infinite loop? Add progress reporting to debug:
   ```matlab
   mcp_progress(__mcp_job_id__, i/n*100, sprintf('Iteration %d', i));
   ```

## Plotly Conversion Failed

**Symptom:** No interactive plot returned, only text output

**Explanation:** The Plotly converter (`mcp_extract_props.m`) supports common plot types. Some complex or custom plot types may not convert.

**Solutions:**

1. **Check supported types:** line, scatter, bar, histogram, surface, image
2. **Simplify the plot:** Complex multi-axis or custom graphics may not convert
3. **Static fallback:** A PNG image is always generated even if Plotly conversion fails
4. **Disable Plotly:** Fall back to static images only:
   ```yaml
   output:
     plotly_conversion: false
   ```

## Large Result Truncated

**Symptom:** Output is cut off or saved to file

**Explanation:** Results exceeding `max_inline_text_length` (50,000 chars) or `large_result_threshold` (10,000 elements) are saved to file instead of returned inline.

**Solutions:**

1. **Increase limits:**
   ```yaml
   output:
     max_inline_text_length: 100000
     large_result_threshold: 50000
   ```

2. **Use `list_files` + `get_job_result`** to access the full output file

## Debug Logging

Enable debug logging to see detailed server activity:

```yaml
server:
  log_level: "debug"
  log_file: "./logs/server.log"
```

Or via environment variable:
```bash
export MATLAB_MCP_SERVER_LOG_LEVEL=debug
```

Check the log file at `./logs/server.log` for detailed error information.
