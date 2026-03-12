# Configuration

All settings are in `config.yaml` with sensible defaults. Every setting can be overridden via environment variables with the `MATLAB_MCP_` prefix.

## Config File Location

The server looks for `config.yaml` in the current working directory by default. Override with:

```bash
matlab-mcp --config /path/to/my_config.yaml
```

## Environment Variable Overrides

Any config value can be set via environment variable using the pattern `MATLAB_MCP_<SECTION>_<KEY>`:

```bash
export MATLAB_MCP_POOL_MIN_ENGINES=4
export MATLAB_MCP_POOL_MAX_ENGINES=16
export MATLAB_MCP_EXECUTION_SYNC_TIMEOUT=60
export MATLAB_MCP_SERVER_TRANSPORT=sse
export MATLAB_MCP_SERVER_PORT=9000
```

## Full Configuration Reference

### Server

```yaml
server:
  name: "matlab-mcp-server"        # Server name reported to MCP clients
  transport: "stdio"                # stdio | sse
  host: "0.0.0.0"                  # Bind address (SSE only)
  port: 8765                       # Port (SSE only)
  log_level: "info"                # debug | info | warning | error
  log_file: "./logs/server.log"    # Log file path
  result_dir: "./results"          # Where to store result files
  drain_timeout_seconds: 300       # Max wait for running jobs during shutdown
```

### Pool

```yaml
pool:
  min_engines: 2                   # Always keep this many engines warm
  max_engines: 10                  # Hard ceiling (capped at 4 on macOS)
  scale_down_idle_timeout: 900     # Seconds idle before scaling down (15 min)
  engine_start_timeout: 120        # Seconds to wait for MATLAB to start
  health_check_interval: 60        # Seconds between health pings
  proactive_warmup_threshold: 0.8  # Utilization ratio to trigger warmup
  queue_max_size: 50               # Max pending requests in queue
  matlab_root: null                # Auto-detect, or set explicit MATLAB path
```

**macOS Note:** MATLAB on macOS has a 4-engine limit. The server will log a warning if `max_engines > 4` on macOS but still respects the configured value.

### Execution

```yaml
execution:
  sync_timeout: 30                 # Seconds before auto-promoting to async
  max_execution_time: 86400        # Hard limit per job (24h = 86400s)
  workspace_isolation: true        # Clear workspace between sessions
  engine_affinity: false           # Pin session to specific engine
  temp_dir: "./temp"               # Temporary file directory
  temp_cleanup_on_disconnect: true # Delete temp files when session ends
```

**sync_timeout:** When code runs longer than this, the server automatically promotes it to an async job and returns a `job_id` for polling. Increase this for environments where most code is expected to take 30-60 seconds.

### Workspace

```yaml
workspace:
  default_paths:                   # Added to MATLAB path on engine start
    - "/shared/custom_libs"
    - "/shared/data"
  startup_commands:                # Run on each engine start
    - "format long"
```

### Toolboxes

```yaml
toolboxes:
  mode: "whitelist"                # whitelist | blacklist | all
  list:
    - "Signal Processing Toolbox"
    - "Optimization Toolbox"
    - "Statistics and Machine Learning Toolbox"
    - "Image Processing Toolbox"
```

| Mode | Behavior |
|------|----------|
| `whitelist` | Only listed toolboxes are reported to agents |
| `blacklist` | All toolboxes EXCEPT listed ones are reported |
| `all` | All installed toolboxes are reported |

### Custom Tools

```yaml
custom_tools:
  config_file: "./custom_tools.yaml"  # Path to custom tools YAML
```

See [[Custom Tools]] for the full custom tools format.

### Security

```yaml
security:
  blocked_functions_enabled: true
  blocked_functions:
    - "system"
    - "unix"
    - "dos"
    - "!"
  max_upload_size_mb: 100
  require_proxy_auth: false        # Set true for production SSE deployments
```

**blocked_functions:** These MATLAB functions are blocked from execution. The security validator strips string literals and comments before scanning, so `disp('system')` won't trigger a false positive.

### Code Checker

```yaml
code_checker:
  enabled: true
  auto_check_before_execute: false  # Run checkcode before every execution
  severity_levels: ["error", "warning"]
```

### Output

```yaml
output:
  plotly_conversion: true          # Convert MATLAB figures to Plotly JSON
  static_image_format: "png"       # png | jpg | svg
  static_image_dpi: 150
  thumbnail_enabled: true
  thumbnail_max_width: 400
  large_result_threshold: 10000    # Elements — save large results to file
  max_inline_text_length: 50000    # Chars — save long text to file
```

### Sessions

```yaml
sessions:
  max_sessions: 50
  session_timeout: 3600            # Seconds of inactivity before cleanup (1h)
  job_retention_seconds: 86400     # Keep completed job metadata for 24h
```

## Example Configurations

See the [`examples/`](https://github.com/HanSur94/matlab-mcp-server-python/tree/master/examples) directory for ready-to-use configurations:

- `config_minimal.yaml` — Single user, minimal settings
- `config_multiuser.yaml` — Multi-user SSE with larger pool and stricter security
