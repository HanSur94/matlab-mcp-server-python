# Phase 3: Streamable HTTP Transport + Session Routing - Research

**Researched:** 2026-04-01
**Domain:** FastMCP 3.2.0 streamable HTTP transport, session routing, SSE deprecation
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Transport Configuration**
- New transport value `"streamablehttp"` in config — FastMCP 3.x `run(transport="streamable-http")` maps to `/mcp`
- SSE deprecation: log WARNING at startup "SSE transport is deprecated, use streamable-http", keep working
- Default transport remains `"stdio"` — backward compatible
- Stateless mode via `server.stateless_http: true/false` config key (default false)

**Session Routing on HTTP**
- Session ID source: `ctx.session_id` with fallback to `ctx.client_id` when None — matches STATE.md known issue (#956)
- Stateless mode: each request gets its own ephemeral temp dir — no state between requests
- Session cleanup: same idle timeout as SSE (1hr default) — reuse existing SessionManager
- Max sessions: reuse existing `sessions.max_sessions` config (default 10)

**Middleware & Auth Wiring**
- Auth: same BearerAuthMiddleware from Phase 2 — already ASGI, works for any HTTP transport
- CORS: same CORSMiddleware config as SSE
- Monitoring routes: register same routes — dashboard works on both SSE and streamable HTTP
- `/mcp` endpoint: hardcoded path per MCP spec standard

### Claude's Discretion
- Internal refactoring of transport selection logic in `main()`
- Test structure for session isolation tests
- Exact deprecation warning text

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TRNS-01 | Server supports streamable HTTP transport at `/mcp` endpoint | FastMCP 3.2.0 `run(transport="streamable-http")` binds to `/mcp` by default — verified in source |
| TRNS-02 | stdio transport continues to work unchanged with no auth | Current `else: server.run(transport="stdio", show_banner=False)` path unchanged — zero risk |
| TRNS-03 | SSE transport logs a deprecation warning when selected | Add `logger.warning(...)` in the `transport == "sse"` startup banner block |
| TRNS-04 | Stateless HTTP mode available for load-balancer-friendly deployments | FastMCP `run_http_async` accepts `stateless_http=True`; needs new `ServerConfig.stateless_http` field |
| TRNS-05 | Session routing works correctly on HTTP transport (`ctx.session_id` fallback to `ctx.client_id`) | `ctx.session_id` in FastMCP 3.2.0 reads `mcp-session-id` HTTP header for streamable-http; falls back to generated UUID — need `ctx.client_id` as additional fallback for issue #956 |
</phase_requirements>

---

## Summary

FastMCP 3.2.0 is already installed and fully supports streamable HTTP. The `run(transport="streamable-http")` call routes to `/mcp` by default (verified via `fastmcp.settings.streamable_http_path = "/mcp"`). The `run_http_async` method accepts `stateless_http: bool` and `middleware: list` parameters — the same middleware list format used by the current SSE path can be reused verbatim for streamable HTTP.

The `ctx.session_id` property in FastMCP 3.2.0 reads the `mcp-session-id` HTTP header for streamable HTTP clients, caches it on the session object, and for non-HTTP transports generates a UUID. It does NOT return `None` in normal operation — it raises `RuntimeError` if called outside a request context. The fallback to `ctx.client_id` (per STATE.md issue #956 concern) should be implemented as a try/except around the entire `ctx.session_id` call rather than a None check, since the property throws rather than returning None when the header is absent.

The scope of change is narrow: `config.py` needs one new bool field on `ServerConfig`, the `main()` function in `server.py` needs a new transport branch, the `_get_session_id` method needs to cover `"streamablehttp"` transport alongside `"sse"`, and the `--transport` CLI argument needs `"streamablehttp"` added to its choices. All existing tests pass (781 passed) and will remain green because the changes are additive.

**Primary recommendation:** Model the `"streamablehttp"` transport branch in `main()` as a near-copy of the SSE branch with `stateless_http=config.server.stateless_http` added to the `server.run()` call.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastmcp | 3.2.0 (installed) | MCP server framework, streamable HTTP transport | Already installed; `transport="streamable-http"` is the framework's first-class transport |
| starlette | 0.52.1 (installed) | Middleware types for BearerAuth + CORS | Already used; `Middleware` class is same for all HTTP transports |
| uvicorn | 0.42.0 (installed) | ASGI server running the HTTP app | Already in use; no changes needed |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| mcp (SDK) | 1.26.0 (installed) | `StreamableHTTPSessionManager` backing `stateless` mode | Transitive via fastmcp — no direct import needed |

**Installation:** No new packages required. All dependencies already installed.

---

## Architecture Patterns

### Recommended Project Structure

No new directories needed. All changes are within existing modules:

```
src/matlab_mcp/
├── config.py          # Add ServerConfig.stateless_http field
└── server.py          # Update _get_session_id(), main() transport branch, CLI arg
```

### Pattern 1: Streamable HTTP Transport Branch in main()

**What:** Mirror the existing SSE branch with transport string changed and `stateless_http` forwarded.

**When to use:** When `config.server.transport == "streamablehttp"`

**Example:**
```python
# Source: FastMCP 3.2.0 run_http_async signature (verified via inspect)
if transport == "streamablehttp":
    from starlette.middleware import Middleware
    from starlette.middleware.cors import CORSMiddleware
    from matlab_mcp.auth.middleware import BearerAuthMiddleware

    middleware: list[Middleware] = [
        Middleware(BearerAuthMiddleware),
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "Accept"],
        ),
    ]

    server.run(
        transport="streamable-http",   # FastMCP's canonical string
        host=config.server.host,
        port=config.server.port,
        middleware=middleware,
        stateless_http=config.server.stateless_http,
    )
```

Note: config value is `"streamablehttp"` (no hyphen, matching YAML-friendly naming); FastMCP canonical string is `"streamable-http"` (with hyphen). The transport selection logic converts between them.

### Pattern 2: Updated _get_session_id() for Streamable HTTP

**What:** Extend the session routing method to treat `"streamablehttp"` the same as `"sse"`, with an extra `client_id` fallback.

**When to use:** Every tool call under streamable HTTP transport.

**Example:**
```python
def _get_session_id(self, ctx: Context) -> str:
    """Return session ID for the current request."""
    transport = self.config.server.transport
    if transport in ("sse", "streamablehttp"):
        try:
            sid = ctx.session_id
            if sid:
                return sid
        except Exception:
            pass
        # Fallback for issue #956: try client_id when session_id unavailable
        try:
            cid = ctx.client_id
            if cid:
                return cid
        except Exception:
            pass
    # stdio or fallback
    session = self.sessions.get_or_create_default()
    return session.session_id
```

### Pattern 3: Stateless HTTP — Ephemeral Temp Dir

**What:** In stateless mode each request must NOT reuse a persistent session. The `_get_temp_dir` path already handles this because `_get_session_id` will return a UUID-based ID from `ctx.session_id` (FastMCP generates a fresh UUID for each stateless request since there is no `mcp-session-id` header in stateless mode). No special code needed in `_get_temp_dir`.

**When to use:** `server.stateless_http: true` in config.

**Verification:** The `mcp.server.streamable_http_manager.StreamableHTTPSessionManager` is initialised with `stateless=True` when FastMCP calls `create_streamable_http_app(stateless_http=True, ...)`. In stateless mode the MCP session manager creates a fresh transport per request, which means each request's `ctx.session_id` resolves to a fresh UUID (no cached `_fastmcp_state_prefix`). Existing SessionManager idle-timeout cleanup will eventually evict these ephemeral sessions.

### Pattern 4: SSE Deprecation Warning

**What:** Log a WARNING in the startup banner block where `transport == "sse"` is already detected.

**Example:**
```python
if transport == "sse":
    logger.warning(
        "SSE transport is deprecated; use 'streamablehttp' instead. "
        "SSE support will be removed in a future release."
    )
```

Place this immediately after the `logger.info("  SSE endpoint: ...")` line — before the auth token check — so it appears prominently in startup output.

### Pattern 5: ServerConfig.stateless_http Field

**What:** Single bool field on `ServerConfig`, default `False`.

**Example:**
```python
class ServerConfig(BaseModel):
    name: str = "matlab-mcp-server"
    transport: Literal["stdio", "sse", "streamablehttp"] = "stdio"
    host: str = "0.0.0.0"
    port: int = 8765
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    log_file: str = "./logs/server.log"
    result_dir: str = "./results"
    drain_timeout_seconds: int = 300
    stateless_http: bool = False
```

Environment override automatically works: `MATLAB_MCP_SERVER_STATELESS_HTTP=true` maps to `data["server"]["stateless_http"]` via the existing `_apply_env_overrides` logic (splits on first `_`, rest is `stateless_http`).

### Pattern 6: CLI --transport Choices Update

**What:** Add `"streamablehttp"` to the `choices` list of the `--transport` argument.

**Example:**
```python
parser.add_argument(
    "--transport",
    default=None,
    choices=["stdio", "sse", "streamablehttp"],
    help="Override transport from config",
)
```

### Anti-Patterns to Avoid

- **Using `ctx.session_id is None` as a None-guard:** The property raises `RuntimeError` when outside a request context; it does not return `None`. Always use `try/except Exception`.
- **Using `"streamable-http"` as the config YAML value:** Hyphens are awkward in YAML keys. Config value should be `"streamablehttp"` (no hyphen); map to FastMCP's `"streamable-http"` at call site.
- **Forgetting `show_banner=False` for stdio:** Already handled in current code; must not be removed.
- **Passing `stateless_http` when transport is `"sse"`:** FastMCP raises `ValueError("SSE transport does not support stateless mode")`. Guard this at the config validation layer.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| `/mcp` endpoint routing | Custom Starlette Route + handler | `server.run(transport="streamable-http")` | FastMCP handles StreamableHTTPSessionManager, session tracking, POST/GET/DELETE methods |
| Stateless request isolation | Custom per-request context injection | `stateless_http=True` in `run()` | MCP SDK's `StreamableHTTPSessionManager(stateless=True)` creates fresh transport per request |
| Session ID extraction from HTTP header | Parse `mcp-session-id` header manually | `ctx.session_id` | FastMCP 3.2.0 reads and caches `mcp-session-id` header automatically |
| SSE keep-alive or event store | Custom SSE event buffer | Not needed for this phase | SSE is being deprecated; no investment in SSE features |

**Key insight:** FastMCP 3.2.0 already implements the full MCP streamable HTTP spec. The transport switch is a single string change in the `run()` call.

---

## Common Pitfalls

### Pitfall 1: Config Transport String Mismatch
**What goes wrong:** Config YAML uses `"streamablehttp"` but `run()` needs `"streamable-http"`. If the raw config string is passed to `server.run()`, FastMCP raises `ValueError: Unknown transport`.
**Why it happens:** FastMCP's canonical transport names use hyphens; YAML keys avoid hyphens.
**How to avoid:** Map at call site: `server.run(transport="streamable-http", ...)` regardless of config string. Or add a mapping dict: `_TRANSPORT_MAP = {"streamablehttp": "streamable-http", "sse": "sse", "stdio": "stdio"}`.
**Warning signs:** `ValueError: Unknown transport: streamablehttp` at startup.

### Pitfall 2: Literal type in Pydantic not updated
**What goes wrong:** `ServerConfig.transport` is typed as `Literal["stdio", "sse"]`. Adding `"streamablehttp"` requires updating the Literal; Pydantic will reject unknown values at config parse time with a `ValidationError`.
**Why it happens:** Pydantic Literal types enforce at validation time.
**How to avoid:** Update `transport: Literal["stdio", "sse", "streamablehttp"] = "stdio"` in `config.py`.
**Warning signs:** `ValidationError: transport value is not a valid enumeration member` when loading config with `transport: streamablehttp`.

### Pitfall 3: _get_temp_dir transport guard not updated
**What goes wrong:** `_get_temp_dir` checks `if self.config.server.transport == "sse"` to decide whether to create a new session vs. reuse default. If this check is not extended to include `"streamablehttp"`, HTTP clients get the default stdio session and contaminate each other's workspaces.
**Why it happens:** The transport string check only covers SSE in the current implementation.
**How to avoid:** Update `_get_temp_dir` to check `if self.config.server.transport in ("sse", "streamablehttp")`.
**Warning signs:** Multiple HTTP-transport agents share variables in their MATLAB workspaces (TRNS-05 test fails).

### Pitfall 4: Auth warning block not extended to streamable HTTP
**What goes wrong:** The startup auth warning (`"SSE transport enabled without MATLAB_MCP_AUTH_TOKEN set..."`) only fires for `transport == "sse"`. New streamable HTTP users get no warning when running without auth.
**Why it happens:** Auth check is transport-specific, only covering `"sse"`.
**How to avoid:** Extend the auth check condition to `if transport in ("sse", "streamablehttp")`.
**Warning signs:** No auth warning at startup for `transport: streamablehttp` without a token set.

### Pitfall 5: Dashboard port log only shown for SSE
**What goes wrong:** The startup banner shows `"Dashboard: http://{host}:{port}/dashboard"` only in the `transport == "sse"` path. Streamable HTTP users see the dashboard URL for stdio only (port 8766).
**Why it happens:** Dashboard URL log condition checks exact transport string.
**How to avoid:** Extend the `if transport == "sse":` dashboard URL log to `if transport in ("sse", "streamablehttp"):`.

### Pitfall 6: ctx.session_id raises RuntimeError (not returns None) in edge cases
**What goes wrong:** The current `_get_session_id` for SSE uses `try/except Exception` which correctly catches the RuntimeError. But a naive implementation checking `if sid is None` after calling `ctx.session_id` would miss the `RuntimeError` and propagate an unhandled exception.
**Why it happens:** FastMCP's `session_id` property raises RuntimeError (not returns None) when outside a request context.
**How to avoid:** Always wrap `ctx.session_id` in try/except — already done in existing SSE code, just extend it to cover `"streamablehttp"` in the transport check.

---

## Code Examples

### Startup banner auth check extended to streamable HTTP
```python
# Source: server.py main() — extend existing pattern
if transport in ("sse", "streamablehttp"):
    if os.environ.get("MATLAB_MCP_AUTH_TOKEN"):
        logger.info("  Auth:            Bearer token enabled")
    else:
        logger.warning(
            "%s transport enabled without MATLAB_MCP_AUTH_TOKEN set. "
            "All HTTP requests will be accepted without authentication.",
            transport,
        )
```

### FastMCP run() for streamable-http (verified signature)
```python
# Source: fastmcp.FastMCP.run_http_async (inspected from installed 3.2.0)
server.run(
    transport="streamable-http",
    host=config.server.host,
    port=config.server.port,
    middleware=middleware,
    stateless_http=config.server.stateless_http,
    # path defaults to fastmcp.settings.streamable_http_path = "/mcp"
)
```

### Config YAML example for streamable HTTP
```yaml
server:
  transport: streamablehttp
  host: 127.0.0.1
  port: 8765
  stateless_http: false
```

### Config YAML example for stateless HTTP
```yaml
server:
  transport: streamablehttp
  host: 127.0.0.1
  port: 8765
  stateless_http: true
```

### Environment override for stateless HTTP
```bash
export MATLAB_MCP_SERVER_STATELESS_HTTP=true
```
This maps via `_apply_env_overrides`: prefix stripped → `SERVER_STATELESS_HTTP` → split at first `_` → `section=server, key=stateless_http`.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SSE (persistent `/sse` stream) | Streamable HTTP at `/mcp` (POST/GET/DELETE) | MCP spec April 2026 | SSE is deprecated in the MCP spec; new clients default to streamable HTTP |
| `transport="sse"` as HTTP transport | `transport="streamable-http"` | FastMCP 3.x | SSE kept working but `"http"` and `"streamable-http"` are the new first-class HTTP transports |

**Deprecated/outdated:**
- `transport: sse` in config: Keep working, but log WARNING. MCP spec deprecated SSE in April 2026.

---

## Open Questions

1. **`ctx.session_id` stability under Codex CLI (issue #956)**
   - What we know: In FastMCP 3.2.0, `ctx.session_id` for streamable HTTP reads the `mcp-session-id` HTTP header. If the client sends this header consistently across requests, session routing works correctly.
   - What's unclear: Whether Codex CLI sends `mcp-session-id` on every request or only on initialization. The fallback to `ctx.client_id` is already decided; `client_id` comes from `request_context.meta.client_id` and may also not be set by all clients.
   - Recommendation: Implement both fallbacks. If both are absent, FastMCP generates a fresh UUID per request — this means stateful sessions effectively degrade to stateless behavior for non-conforming clients, which is acceptable.

2. **Behavior of `ctx.session_id` in stateless mode**
   - What we know: `StreamableHTTPSessionManager(stateless=True)` creates a new transport per request. FastMCP's `session_id` property caches `_fastmcp_state_prefix` on the session object — but in stateless mode each request has a fresh session object, so there is no cross-request cache.
   - What's unclear: Whether FastMCP's stateless mode sends a `mcp-session-id` response header (which would allow the client to re-send it). If it does, clients might accidentally maintain session continuity in "stateless" mode.
   - Recommendation: Test empirically. For this phase, stateless mode is opt-in and documented as "no state between requests."

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| fastmcp | Streamable HTTP transport | ✓ | 3.2.0 | — |
| mcp SDK | `StreamableHTTPSessionManager` (transitive) | ✓ | 1.26.0 | — |
| uvicorn | ASGI server | ✓ | 0.42.0 | — |
| starlette | Middleware types | ✓ | 0.52.1 | — |
| Python 3.11 | Runtime | ✓ | 3.11.x | — |
| pytest | Test runner | ✓ | 7.x (781 tests passing) | — |

**Missing dependencies with no fallback:** None.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.x with pytest-asyncio |
| Config file | `pyproject.toml` (`asyncio_mode = "auto"`) |
| Quick run command | `python -m pytest tests/test_server.py tests/test_config.py -q` |
| Full suite command | `python -m pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TRNS-01 | `server.run(transport="streamable-http")` called when config transport is `"streamablehttp"` | unit | `pytest tests/test_server.py -k "streamable" -x` | ❌ Wave 0 |
| TRNS-02 | stdio branch unchanged — `server.run(transport="stdio", show_banner=False)` still called | unit | `pytest tests/test_server.py -k "stdio" -x` | ✅ existing |
| TRNS-03 | `logger.warning(...)` called at startup when transport is `"sse"` | unit | `pytest tests/test_server.py -k "sse_deprecation" -x` | ❌ Wave 0 |
| TRNS-04 | `ServerConfig.stateless_http` field accepts `True/False`; forwarded to `server.run()` | unit | `pytest tests/test_config.py -k "stateless" -x` | ❌ Wave 0 |
| TRNS-05 | Two simultaneous HTTP sessions get distinct `session_id` values; no workspace cross-contamination | unit | `pytest tests/test_server.py -k "session_isolation" -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_server.py tests/test_config.py -q`
- **Per wave merge:** `python -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_server.py` — add `TestStreamableHTTPTransport` class with:
  - `test_streamablehttp_config_calls_run_with_streamable_http_transport`
  - `test_sse_startup_logs_deprecation_warning`
  - `test_get_session_id_streamablehttp_uses_ctx_session_id`
  - `test_get_session_id_streamablehttp_falls_back_to_client_id`
  - `test_get_temp_dir_streamablehttp_creates_session`
  - `test_session_isolation_two_http_sessions_get_different_dirs`
- [ ] `tests/test_config.py` — add `TestStatelessHttpConfig`:
  - `test_stateless_http_defaults_to_false`
  - `test_stateless_http_can_be_set_true`
  - `test_stateless_http_env_override`
  - `test_transport_accepts_streamablehttp`
  - `test_transport_rejects_unknown_value`

---

## Sources

### Primary (HIGH confidence)
- FastMCP 3.2.0 installed package — `inspect.getsource(FastMCP.run_http_async)` — confirmed `stateless_http`, `middleware`, `transport` parameters
- FastMCP 3.2.0 installed package — `inspect.getsource(Context.session_id.fget)` — confirmed HTTP header reading, UUID fallback, caching behavior
- FastMCP 3.2.0 installed package — `inspect.getsource(Context.client_id.fget)` — confirmed `Optional[str]` from meta
- FastMCP 3.2.0 installed package — `fastmcp.settings.streamable_http_path` = `"/mcp"` — confirmed default path
- FastMCP 3.2.0 installed package — `inspect.getsource(FastMCP.http_app)` — confirmed `create_streamable_http_app` call with `stateless_http` forwarding
- MCP SDK 1.26.0 installed package — `inspect.getsource(StreamableHTTPSessionManager.__init__)` — confirmed `stateless` parameter behavior
- `/Users/hannessuhr/matlab-mcp-server-python/src/matlab_mcp/server.py` — confirmed current transport selection, `_get_session_id`, `_get_temp_dir` patterns
- `/Users/hannessuhr/matlab-mcp-server-python/src/matlab_mcp/config.py` — confirmed `ServerConfig` fields, `_apply_env_overrides` split logic
- `python -m pytest tests/ -q` — 781 passed, 2 skipped — baseline test suite green

### Secondary (MEDIUM confidence)
- MCP spec context (REQUIREMENTS.md `Out of Scope` table): "Persistent SSE as primary transport — SSE deprecated in MCP spec April 2026" — confirms SSE deprecation timing

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — FastMCP 3.2.0 installed and introspected directly
- Architecture: HIGH — verified via source inspection, not documentation alone
- Pitfalls: HIGH — derived from direct code reading of config.py and server.py

**Research date:** 2026-04-01
**Valid until:** 2026-05-01 (FastMCP is actively developed; verify if upgrading past 3.2.0)
