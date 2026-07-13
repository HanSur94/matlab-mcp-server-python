# Configuration

All settings live in `config.yaml` with sensible defaults. The file is optional — if it is absent, the built-in defaults are used. Every setting can be overridden via `MATLAB_MCP_*` environment variables.

The schema is defined by Pydantic models in `src/matlab_mcp/config.py`. Unknown keys in `config.yaml` are silently ignored, so a typo (or a key that is not a real field) has no effect.

## Config file location

The server looks for `./config.yaml` in the current working directory. Override the path with:

```bash
matlab-mcp --config /path/to/my_config.yaml
```

Relative paths in `server.result_dir`, `server.log_file`, `execution.temp_dir`, `custom_tools.config_file`, and `monitoring.db_path` are resolved to absolute paths **relative to the config file's directory** at startup.

## Environment-variable overrides

Any config value can be set via an environment variable using the pattern `MATLAB_MCP_<SECTION>_<KEY>`:

```bash
export MATLAB_MCP_POOL_MIN_ENGINES=4
export MATLAB_MCP_POOL_MAX_ENGINES=16
export MATLAB_MCP_EXECUTION_SYNC_TIMEOUT=60
export MATLAB_MCP_SERVER_TRANSPORT=streamablehttp
export MATLAB_MCP_SERVER_PORT=9000
```

Values are coerced in the order int → float → bool (`true`/`false`) → string.

**Section splitting:** the text after `MATLAB_MCP_` is lowercased and split on the **first** underscore into `section` and `key`. This works for every single-word section (`server`, `pool`, `execution`, `security`, `sessions`, `monitoring`, `output`, `workspace`, `toolboxes`, `hitl`), but multi-word sections such as `code_checker` and `custom_tools` cannot be reached this way (`MATLAB_MCP_CODE_CHECKER_ENABLED` would parse as section `code`, key `checker_enabled`). Use the config file for those.

**Auth token is not a config key.** The bearer token is read only from the `MATLAB_MCP_AUTH_TOKEN` environment variable — never from `config.yaml`. `load_config` logs a warning if any config key looks like a secret (contains `token`, `secret`, `api_key`, `password`, or `bearer`). See [Security](Security) for details.

## Full configuration reference

### server

General server settings.

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `name` | str | `"matlab-mcp-server"` | Server name reported to MCP clients |
| `transport` | enum | `"stdio"` | `stdio` \| `sse` \| `streamablehttp` |
| `host` | str | `"127.0.0.1"` | Bind address for HTTP transports (shipped `config.yaml` sets `0.0.0.0`) |
| `port` | int | `8765` | Port for HTTP transports |
| `log_level` | enum | `"info"` | `debug` \| `info` \| `warning` \| `error` |
| `log_file` | str | `"./logs/server.log"` | Log file path |
| `result_dir` | str | `"./results"` | Where result files are stored |
| `drain_timeout_seconds` | int | `300` | Max wait for running jobs during graceful shutdown |
| `stateless_http` | bool | `false` | Run streamable-http in stateless mode |
| `cors_origins` | list[str] | `["*"]` | Allowed CORS origins for HTTP transports |

`streamablehttp` is the recommended HTTP transport; `sse` is kept only for back-compat and logs a deprecation warning at startup.

### pool

MATLAB engine pool sizing and timeouts.

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `min_engines` | int | `2` | Always keep this many engines warm |
| `max_engines` | int | `10` | Hard ceiling |
| `scale_down_idle_timeout` | int | `900` | Seconds idle before scaling down (15 min) |
| `engine_start_timeout` | int | `120` | Seconds to wait for a MATLAB engine to start |
| `health_check_interval` | int | `60` | Seconds between health pings |
| `queue_max_size` | int | `50` | Max pending requests in the queue |
| `matlab_root` | str \| null | `null` | Auto-detect, or set an explicit MATLAB path |

`min_engines` must not exceed `max_engines` (validated at load; raises `ValueError` otherwise).

**macOS note:** the shipped `config.yaml` comment says "capped at 4 on macOS", but the code only **warns** when `max_engines > 4` on macOS (running more than 4 `matlab.engine` instances in one Python process on macOS is unstable). It does not hard-cap the value.

> The shipped `config.yaml` also includes `proactive_warmup_threshold`, but that is **not** a modeled field — it is ignored and has no effect.

### execution

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `sync_timeout` | int | `30` | Seconds before a job is auto-promoted to async |
| `max_execution_time` | int | `86400` | Hard per-job limit (24 h) |
| `workspace_isolation` | bool | `true` | Clear workspace between sessions |
| `engine_affinity` | bool | `false` | Pin a session to an engine for workspace persistence |
| `temp_dir` | str | `"./temp"` | Temporary file directory |
| `temp_cleanup_on_disconnect` | bool | `true` | Delete temp files when a session ends |

**`sync_timeout`:** when code runs longer than this, the server promotes it to an async job and returns a `job_id` for polling. Increase it if most of your code is expected to take 30–60 s.

### workspace

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `default_paths` | list[str] | `[]` | Added to the MATLAB path on engine start/reset |
| `startup_commands` | list[str] | `["format long"]` | Run on each engine start and after a workspace reset |

The server also auto-inserts its bundled `matlab_helpers` directory onto the MATLAB path.

### toolboxes

Controls which toolboxes `list_toolboxes` reports to agents.

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `mode` | enum | `"whitelist"` | `whitelist` \| `blacklist` \| `all` |
| `list` | list[str] | `[]` | Toolbox names for the whitelist/blacklist |

| Mode | Behavior |
|------|----------|
| `whitelist` | Only listed toolboxes are reported |
| `blacklist` | All toolboxes EXCEPT listed ones are reported |
| `all` | All installed toolboxes are reported |

### custom_tools

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `config_file` | str | `"./custom_tools.yaml"` | Path to the custom-tools YAML file |

See [Custom Tools](Custom-Tools) for the file format.

### security

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `blocked_functions_enabled` | bool | `true` | Master switch for the blocklist |
| `blocked_functions` | list[str] | see below | MATLAB functions blocked from execution |
| `max_upload_size_mb` | int | `100` | Max size for `upload_data` |
| `require_proxy_auth` | bool | `false` | Acknowledge that an external auth proxy fronts the server (suppresses the "HTTP without auth" warning); does not itself enforce auth |

The code default `blocked_functions` list is:

```
system, unix, dos, !, eval, feval, evalc, evalin, assignin,
perl, python, str2func, builtin, run
```

The shipped `config.yaml` overrides this with a shorter list that omits the last three (`str2func`, `builtin`, `run`). The security validator strips string literals and comments before scanning, so `disp('system')` does not trigger a false positive.

Setting `blocked_functions_enabled: false` makes **all** code execution unrestricted and logs a warning at load.

### code_checker

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `enabled` | bool | `true` | Enable the `check_code` linter |
| `auto_check_before_execute` | bool | `false` | Run `checkcode` before every execution |
| `severity_levels` | list[str] | `["error", "warning"]` | Severities to report |

### output

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `plotly_conversion` | bool | `true` | Convert MATLAB figures to Plotly JSON |
| `static_image_format` | enum | `"png"` | `png` \| `jpg` \| `svg` |
| `static_image_dpi` | int | `150` | DPI for static image export |
| `thumbnail_enabled` | bool | `true` | Generate figure thumbnails |
| `thumbnail_max_width` | int | `400` | Max thumbnail width (px) |
| `large_result_threshold` | int | `10000` | Elements — above this, save tabular/matrix data to file |
| `max_inline_text_length` | int | `50000` | Chars — above this, save text output to file |

### sessions

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `max_sessions` | int | `50` | Max concurrent sessions |
| `session_timeout` | int | `3600` | Seconds of inactivity before cleanup (1 h) |
| `job_retention_seconds` | int | `86400` | How long completed job metadata is kept (24 h) |

### monitoring

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `enabled` | bool | `true` | Enable metrics collection |
| `sample_interval` | int | `10` | Seconds between metric samples |
| `retention_days` | int | `7` | Days of historical data to keep |
| `db_path` | str | `"./monitoring/metrics.db"` | SQLite database path |
| `dashboard_enabled` | bool | `true` | Enable the web dashboard |
| `http_port` | int | `8766` | Dashboard/health port (stdio transport only) |

Under `stdio` transport the dashboard/health app runs on `127.0.0.1:8766`. Under `sse`/`streamablehttp` the monitoring routes are mounted on the main MCP app instead (port `8765`). Monitoring needs the optional `psutil` and `uvicorn` dependencies:

```bash
pip install "matlab-mcp-python[monitoring]"
```

### hitl

Human-in-the-loop approval gate. Disabled by default; when enabled, matching operations pause and prompt for approval via the MCP elicitation protocol before proceeding. In the shipped `config.yaml` this whole section is commented out.

| Key | Type | Default | Notes |
|-----|------|---------|-------|
| `enabled` | bool | `false` | Master switch — no HITL prompts appear when false |
| `protected_functions` | list[str] | `[]` | MATLAB function names that require approval before execution |
| `protect_file_ops` | bool | `false` | Require approval for file upload/delete |
| `all_execute` | bool | `false` | Require approval for **all** `execute_code` calls |

```yaml
hitl:
  enabled: true
  protected_functions: ["delete", "rmdir", "fclose", "ftp"]
  protect_file_ops: true
  all_execute: false
```

## Example configurations

See the [`examples/`](https://github.com/HanSur94/matlab-mcp-server-python/tree/master/examples) directory for ready-to-use configs:

- `config_minimal.yaml` — single user, minimal settings
- `config_multiuser.yaml` — multi-user HTTP with a larger pool and stricter security

## See also

- [Installation](Installation)
- [Security](Security)
- [Custom Tools](Custom-Tools)
