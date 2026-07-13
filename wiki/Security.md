# Security

The MATLAB MCP Server has several independent security layers: a MATLAB
function blocklist, per-session workspace isolation, an optional
human-in-the-loop (HITL) approval gate, and bearer-token authentication for the
HTTP transports. Every layer is configured under `config.yaml` (see
[Configuration](Configuration)) or via `MATLAB_MCP_*` environment variables.

## Function blocklist

Before any code runs, `SecurityValidator.check_code()`
(`src/matlab_mcp/security/validator.py`) scans it for blocked MATLAB functions
and constructs. A match raises `BlockedFunctionError` and the code never
reaches an engine.

### Default blocklist

The code default (`SecurityConfig.blocked_functions`) is:

| Function | Risk |
|----------|------|
| `system` | Execute arbitrary OS commands |
| `unix` | Execute Unix commands |
| `dos` | Execute DOS/Windows commands |
| `!` | Shell escape operator |
| `eval` | Execute an arbitrary string as code |
| `feval` | Call a function by name string |
| `evalc` | Evaluate and capture output |
| `evalin` | Evaluate in the caller/base workspace |
| `assignin` | Assign into the caller/base workspace |
| `perl` | Execute Perl scripts |
| `python` | Execute Python scripts |
| `str2func` | Build a function handle from a string |
| `builtin` | Call a built-in bypassing overloads |
| `run` | Run a script by filename |

> Note: the shipped `config.yaml` lists only the first eleven entries — it omits
> `str2func`, `builtin`, and `run`. If you rely on those three being blocked,
> either delete the `security.blocked_functions` key from your `config.yaml`
> (so the code default applies) or add them explicitly.

### How validation works

- **String literals and comments are stripped first.** `_strip_string_literals`
  removes double-quoted strings, single-quoted char arrays (while leaving the
  `'` transpose operator intact), and `%` comments before matching. This avoids
  false positives on text that merely mentions a blocked name.
- **Two match patterns per function:** a call form (`\bname\s*\(`, e.g.
  `system(...)`) and a command form (`name` at the start of a line or after `;`
  followed by an argument, e.g. `system rm`). The `!` shell escape matches any
  line whose first non-whitespace character is `!`.
- Patterns are precompiled at construction for the hot path.

```matlab
% SAFE — these do NOT trigger the blocklist:
disp('the operating system is great')   % "system" inside a string
% system('ls')                          % "system" inside a comment
msg = "unix-based systems";             % "unix" inside a string

% BLOCKED:
system('rm -rf /')                      % real system() call
!del important.txt                      % shell escape
```

String-stripping is a best-effort heuristic, not a full MATLAB parser. Treat the
blocklist as defense-in-depth, not a sandbox.

### Configuring the blocklist

```yaml
security:
  blocked_functions_enabled: true   # set false to disable checking entirely
  blocked_functions:
    - "system"
    - "unix"
    - "dos"
    - "!"
    - "eval"
    - "feval"
    - "evalc"
    - "evalin"
    - "assignin"
    - "perl"
    - "python"
    - "str2func"
    - "builtin"
    - "run"
    # add your own, e.g. "web"
```

Setting `blocked_functions_enabled: false` disables the check and allows **all**
code to execute — `load_config` warns loudly when it sees this.

## Workspace isolation

With `execution.workspace_isolation: true` (the default), engines are reset to a
clean state between uses so one session's variables, globals, function
definitions, and open file handles cannot leak into another. `reset_workspace()`
(`src/matlab_mcp/pool/engine.py`) runs, in order:

```matlab
clear all
clear global
clear functions
fclose all
restoredefaultpath
```

After the reset it re-adds the paths in `workspace.default_paths` (plus the
server's bundled helper directory) and re-runs `workspace.startup_commands`
(default `["format long"]`).

Each session also gets its own temp directory. Uploaded files land there and are
removed when the session ends if `execution.temp_cleanup_on_disconnect: true`
(default). See [Configuration](Configuration) for session lifecycle settings.

## File upload protection

`upload_data`, `delete_file`, and the other file tools operate only inside the
session temp dir and go through `SecurityValidator.sanitize_filename()`:

- **Basename only.** A filename containing `..` is rejected (`ValueError`),
  blocking path traversal such as `../../etc/passwd`.
- **Allowed characters** are `[a-zA-Z0-9._-]` only; anything else is rejected.
- **Size cap** via `security.max_upload_size_mb` (default `100`).

## Human-in-the-loop (HITL) approval

The HITL gate (`src/matlab_mcp/hitl/gate.py`) can pause an operation and ask a
human to approve it, using the MCP elicitation protocol. It is **disabled by
default** and requires a client that supports elicitation.

```yaml
hitl:
  enabled: false               # master switch
  protected_functions: []      # MATLAB names that require approval before running
  protect_file_ops: false      # require approval for upload/delete
  all_execute: false           # require approval for EVERY execute_code call
```

Gate behavior when `hitl.enabled: true`:

- **`all_execute: true`** — every `execute_code` call prompts for approval,
  regardless of content. This gate takes precedence.
- **`protected_functions`** — otherwise, `execute_code` prompts only when the
  code calls one of the listed functions (matched as `name(`).
- **`protect_file_ops: true`** — `upload_data` and `delete_file` prompt before
  acting.

If the human declines (or the client cannot elicit / the request is cancelled),
the operation is blocked and the tool returns
`{"status": "denied", "message": "Operation blocked by HITL approval"}`. Every
decision is logged with the session id for audit.

HITL is orthogonal to the blocklist: blocked functions are rejected outright and
never reach the gate, while HITL lets you require sign-off on functions you allow
but consider sensitive.

## Authentication for HTTP transports

The `sse` and `streamablehttp` transports can require a **bearer token**. The
`stdio` transport is local-only and unaffected.

- The token is read **only** from the `MATLAB_MCP_AUTH_TOKEN` environment
  variable — never from `config.yaml`. `load_config` warns if a config key looks
  like a secret (`token`, `secret`, `api_key`, `password`, `bearer`).
- `BearerAuthMiddleware` (`src/matlab_mcp/auth/middleware.py`) is a pure-ASGI
  middleware added for the HTTP transports. It checks the
  `Authorization: Bearer <token>` header with a constant-time comparison
  (`hmac.compare_digest`) to avoid timing oracles.
- On failure it returns `401` with `WWW-Authenticate: Bearer` and a JSON body.
- **Bypasses:** the `/health` path (so load balancers need no token) and CORS
  pre-flight `OPTIONS` requests.
- **If `MATLAB_MCP_AUTH_TOKEN` is unset, auth is disabled and all HTTP requests
  are accepted** — the server logs a warning at startup.

### Generate a token

```bash
matlab-mcp --generate-token      # or: pixi run generate-token
```

This prints a 64-hex-character token plus ready-to-paste env-var snippets for
Linux/macOS/Windows, then exits without starting the server. Set it before
launching an HTTP transport:

```bash
export MATLAB_MCP_AUTH_TOKEN=<token>
matlab-mcp --transport streamablehttp
```

### CORS

Cross-origin settings come from `server.cors_origins` (default `["*"]`). Allowed
methods are `GET, POST, OPTIONS`; allowed headers are `Authorization`,
`Content-Type`, `Accept`.

## streamable-http vs. SSE

- **`streamablehttp`** is the recommended HTTP transport (endpoint `/mcp`).
- **`sse`** is kept only for backward compatibility, is **deprecated**, logs a
  deprecation warning at startup, and will be removed in a future release. Prefer
  `streamablehttp` for new multi-user deployments.

For either HTTP transport, put the server behind a reverse proxy with TLS and
bind to a trusted interface. If you front the server with an external auth proxy
instead of using `MATLAB_MCP_AUTH_TOKEN`, set
`security.require_proxy_auth: true`. This is only an acknowledgement flag that
suppresses the "HTTP transport without auth" startup warning — **it does not
itself enforce anything.**

```yaml
security:
  require_proxy_auth: true   # you have set up auth at a proxy; suppresses the warning

server:
  transport: "streamablehttp"
  host: "127.0.0.1"          # bind to localhost / trusted interface
  port: 8765
```

## Session and job cleanup

- Idle sessions expire after `sessions.session_timeout` seconds (default `3600`).
- Session temp files are removed on disconnect when
  `execution.temp_cleanup_on_disconnect: true` (default).
- Finished job metadata is pruned after `sessions.job_retention_seconds`
  (default `86400`, i.e. 24 hours).

## Recommendations

| Scenario | Recommendation |
|----------|----------------|
| **Personal / local** | `stdio` transport, default blocklist. No token needed. |
| **Team server** | `streamablehttp` + `MATLAB_MCP_AUTH_TOKEN` + reverse proxy. Review the blocklist and consider enabling HITL for sensitive functions. |
| **Production** | `streamablehttp` + bearer token + TLS at a reverse proxy. Keep `workspace_isolation` on; review the blocklist; enable HITL where sign-off is required. |

See also: [Configuration](Configuration), [Architecture](Architecture).
