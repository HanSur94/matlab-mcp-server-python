# Phase 1: FastMCP 3.0 Upgrade - Research

**Researched:** 2026-04-01
**Domain:** FastMCP 2.x → 3.2.0 migration
**Confidence:** HIGH (verified by installing and running FastMCP 3.2.0 directly)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
All implementation choices are at Claude's discretion — pure infrastructure phase.

### Claude's Discretion
All implementation choices are Claude's discretion. Key migration areas:
- FastMCP dependency pin: `fastmcp>=2.0.0,<3.0.0` → `fastmcp>=3.2.0,<4.0.0`
- Import path changes (e.g., `from fastmcp import Context`)
- Tool registration API changes (decorator signatures, parameter types)
- Custom route API for monitoring dashboard (`@mcp.custom_route()`)
- Lifespan management changes
- Any breaking changes in MCP protocol types or context objects

### Deferred Ideas (OUT OF SCOPE)
None — infrastructure phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FMCP-01 | Server runs on FastMCP 3.2.0+ with all breaking changes resolved | Pin in pyproject.toml + requirements-lock.txt; 3 test fixes needed |
| FMCP-02 | All existing MCP tools pass regression tests after upgrade | Verified: 752/755 tests pass under 3.2.0; 3 tests need _tool_manager → list_tools() fix |
| FMCP-03 | Monitoring dashboard migrated to FastMCP 3.x `@custom_route()` pattern | `@mcp.custom_route()` still works in 3.2.0; `_additional_http_routes` Mount approach also still works |
| FMCP-04 | Constructor kwargs and `run()` parameters updated to 3.x API | host/port removed from constructor; passed as run(**kwargs) instead (already handled by current code) |
| FMCP-05 | Import paths updated (`from fastmcp import Context` etc.) | `from fastmcp.server.context import Context` still works in 3.2.0; `from fastmcp import Context` also works |
</phase_requirements>

## Summary

FastMCP 3.2.0 is the latest release (as of 2026-04-01, verified via `pip index versions fastmcp`). The migration from 2.14.5 is **exceptionally low-risk** for this codebase. Direct testing confirmed that `create_server()` with all 20 tools registers correctly under 3.2.0, all import paths from the current code still resolve, and 752 of 755 tests pass with zero code changes. The only failures are 3 tests in `test_server.py` that use `mcp._tool_manager.get_tools()` — a private internal API that was removed. The fix is a 1-line change per test: replace `await mcp._tool_manager.get_tools()` with `{t.name: t for t in await mcp.list_tools()}`.

The upgrade path is: (1) change the dependency pin in `pyproject.toml`, (2) regenerate `requirements-lock.txt`, and (3) fix 3 test assertions. No production code changes are required.

**Primary recommendation:** Update `pyproject.toml` pin to `fastmcp>=3.2.0,<4.0.0`, regenerate lockfile, fix 3 tests that used `_tool_manager`. No server code changes needed.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fastmcp | 3.2.0 | MCP server framework — tool registration, transports, lifespan | Project requirement; gates Auth, Transport, HITL phases |
| mcp | >=1.24.0,<2.0 | MCP protocol implementation (pulled in by fastmcp) | FastMCP 3.2.0 hard dependency |
| pydantic | >=2.11.7 | Config validation (fastmcp requires this minimum) | FastMCP 3.2.0 requires pydantic[email]>=2.11.7 |

### Supporting (unchanged)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uvicorn | >=0.35 | ASGI server for HTTP/SSE transport | FastMCP 3.2.0 requires >=0.35 (up from >=0.20.0) |
| websockets | >=15.0.1 | WebSocket support | FastMCP 3.2.0 hard dependency |

**Installation:**
```bash
pip install "fastmcp>=3.2.0,<4.0.0"
```

**New mandatory FastMCP 3.2.0 deps (auto-pulled, but affect lockfile):**
- `authlib>=1.6.5` (new)
- `cyclopts>=4.0.0` (new)
- `opentelemetry-api>=1.20.0` (new)
- `py-key-value-aio[filetree,keyring,memory]<0.5.0,>=0.4.4` (new)
- `uncalled-for>=0.2.0` (new)
- `watchfiles>=1.0.0` (new)

**Version verification:** FastMCP 3.2.0 confirmed as latest via `pip index versions fastmcp` on 2026-04-01.

## Architecture Patterns

### What Did NOT Change (confirmed by testing)

These patterns from the current codebase work identically in FastMCP 3.2.0:

1. **Import paths** — `from fastmcp.server.context import Context` still resolves. `from fastmcp import FastMCP, Context` also works.
2. **Tool decorator** — `@mcp.tool` (no parentheses) registers tools correctly. All 20 tools register fine.
3. **Lifespan** — `@asynccontextmanager async def lifespan(mcp: FastMCP)` works unchanged. No yield value required.
4. **Constructor** — `FastMCP(name=..., lifespan=...)` is unchanged.
5. **run() for stdio** — `server.run(transport="stdio")` unchanged.
6. **run() for SSE** — `server.run(transport="sse", host=..., port=...)` still works. FastMCP 3.x passes `**transport_kwargs` to `run_http_async(host=, port=)`.
7. **_additional_http_routes** — `mcp._additional_http_routes.append(Mount(...))` still works (private but present).
8. **@mcp.custom_route()** — Works identically in 3.2.0.
9. **add_tool(callable)** — `mcp.add_tool(handler)` still accepts a callable. Returns a `Tool` object (was also returning an object in 2.x).
10. **Context properties** — `ctx.session_id`, `ctx.client_id`, `ctx.transport` all present.

### What Changed (breaking)

**1. `mcp._tool_manager` removed**

The private `_tool_manager` attribute with `.get_tools()` method no longer exists.

```python
# 2.x (broken):
tools_dict = await mcp._tool_manager.get_tools()

# 3.x fix:
tools = await mcp.list_tools()  # returns list[Tool]
tools_dict = {t.name: t for t in tools}
```

This breaks 3 tests in `tests/test_server.py` lines 332, 358, 367.

**2. 15 constructor kwargs removed from FastMCP()**

These were previously deprecated and are now hard errors. None are used in the current codebase (current code only uses `name=` and `lifespan=`):

| Removed Kwarg | Migration |
|---------------|-----------|
| `host` | Pass to `run_http_async()` or set `FASTMCP_HOST` |
| `port` | Pass to `run_http_async()` or set `FASTMCP_PORT` |
| `sse_path` | Pass `path=` to `run_http_async()` |
| `message_path` | Set `FASTMCP_MESSAGE_PATH` |
| `streamable_http_path` | Pass `path=` to `run_http_async()` |
| `json_response` | Pass to `run_http_async()` |
| `stateless_http` | Pass to `run_http_async()` |
| `debug` | Set `FASTMCP_DEBUG` |
| `log_level` | Pass to `run_http_async()` |
| `on_duplicate_tools` | Use `on_duplicate=` instead |
| `on_duplicate_resources` | Use `on_duplicate=` instead |
| `on_duplicate_prompts` | Use `on_duplicate=` instead |
| `tool_serializer` | Return `ToolResult` from tools instead |
| `include_tags` | Use `server.enable(tags=..., only=True)` |
| `exclude_tags` | Use `server.disable(tags=...)` |
| `tool_transformations` | Use `server.add_transform(ToolTransform(...))` |

**Current code uses none of these** — `FastMCP(name=config.server.name, lifespan=lifespan)` is valid in 3.x.

**3. `@mcp.tool` decorator now returns the original function (not a Tool object)**

In 3.x, decorated functions remain callable directly (like Flask/FastAPI style). This does NOT break any current code because the decorated functions are not used as callables post-registration. If old behavior is needed, set `FASTMCP_DECORATOR_MODE=object`.

**4. `ctx.set_state()` / `ctx.get_state()` are now async**

Not used in current codebase. No action needed.

**5. `sse_app()` removed, `http_app()` replaces it**

Not used directly in current code (current code uses `_additional_http_routes`). No action needed for this phase.

### Recommended Approach for This Phase

This is a minimum-footprint migration — touch only what's broken:

1. `pyproject.toml`: Change pin, bump pydantic minimum to `>=2.11.7` for correctness
2. `requirements-lock.txt`: Regenerate with `pip-compile` or `pip freeze` after upgrade
3. `tests/test_server.py`: Fix 3 tests using `_tool_manager`

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Listing registered tools | Custom reflection over server internals | `await mcp.list_tools()` | Public API, returns `list[Tool]` with `.name`, `.description`, etc. |
| Custom HTTP routes | Manually managing Starlette routing | `@mcp.custom_route('/path', methods=['GET'])` | Properly wired into FastMCP's HTTP app |
| Async lifespan | Rolling own startup/shutdown | `@asynccontextmanager` function passed as `lifespan=` to constructor | Already the pattern; unchanged in 3.x |

## Common Pitfalls

### Pitfall 1: Assuming `_tool_manager` still exists
**What goes wrong:** `AttributeError: 'FastMCP' object has no attribute '_tool_manager'` in tests.
**Why it happens:** Private internal API was refactored in 3.x with the new Provider architecture.
**How to avoid:** Use `await mcp.list_tools()` which is the public, stable API.
**Warning signs:** Tests checking tool registration by name fail immediately under 3.x.

### Pitfall 2: Pydantic version mismatch
**What goes wrong:** FastMCP 3.2.0 requires `pydantic[email]>=2.11.7`. If the lockfile pins an older version, import errors occur.
**Why it happens:** The `[email]` extra is now required and pydantic 2.11.7 has breaking changes vs 2.0.0.
**How to avoid:** Bump `pydantic>=2.0.0` to `pydantic>=2.11.7` in `pyproject.toml` and regenerate lockfile.
**Warning signs:** `pydantic.errors.PydanticUserError` or `email-validator` import error at startup.

### Pitfall 3: Lockfile out of sync
**What goes wrong:** Server starts but fails at runtime due to transitive dependency version mismatches (e.g., `uvicorn<0.35`, `websockets<15`, `mcp<1.24`).
**Why it happens:** `requirements-lock.txt` has pinned versions for fastmcp 2.x ecosystem.
**How to avoid:** Regenerate lockfile after upgrading fastmcp. Don't manually edit pin-by-pin.
**Warning signs:** `ImportError` for new transitive deps or version conflict errors at install time.

### Pitfall 4: SSE banner to stdout breaking stdio protocol
**What goes wrong:** FastMCP 3.x prints a server banner by default (`show_banner=True`). If this writes to stdout during stdio transport, the MCP client sees garbage before the protocol stream.
**Why it happens:** New feature in 3.x — banner wasn't present in 2.x.
**How to avoid:** Pass `show_banner=False` to `server.run(transport="stdio")`, or set `FASTMCP_SHOW_SERVER_BANNER=false`.
**Warning signs:** stdio clients report protocol parse errors on startup.

### Pitfall 5: Confusing `sse_app()` removal with `_additional_http_routes`
**What goes wrong:** Developer tries to use `mcp.sse_app()` for SSE transport → `AttributeError`.
**Why it happens:** `sse_app()` was removed; replaced by `http_app(transport='sse')`.
**How to avoid:** Current code already uses `_additional_http_routes` (not `sse_app()`), so no change needed. But if refactoring, use `mcp.http_app(transport='sse')`.
**Warning signs:** Only affects code that calls `sse_app()` directly — current codebase is safe.

## Code Examples

### Tool listing in 3.x tests
```python
# Source: verified against FastMCP 3.2.0 installed package
# Replaces: await mcp._tool_manager.get_tools()
async def test_expected_core_tools_registered(self, stdio_config: AppConfig) -> None:
    mcp = create_server(stdio_config)
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    expected = {"execute_code", "check_code", ...}
    for name in expected:
        assert name in tool_names
```

### FastMCP constructor (unchanged, valid in 3.x)
```python
# Source: verified against FastMCP 3.2.0
mcp = FastMCP(
    name=config.server.name,
    lifespan=lifespan,
)
```

### run() for SSE transport (unchanged, valid in 3.x)
```python
# Source: verified against FastMCP 3.2.0 run_http_async() signature
server.run(
    transport="sse",
    host=config.server.host,
    port=config.server.port,
)
```

### run() for stdio with banner suppressed
```python
# Source: FastMCP 3.2.0 run_stdio_async() signature
server.run(transport="stdio", show_banner=False)
```

### Custom route (unchanged in 3.x)
```python
# Source: verified against FastMCP 3.2.0
@mcp.custom_route('/health', methods=['GET'])
async def health_endpoint(request):
    return JSONResponse({'status': 'ok'})
```

### pyproject.toml dependency pin change
```toml
# Before:
"fastmcp>=2.0.0,<3.0.0",
"pydantic>=2.0.0",

# After:
"fastmcp>=3.2.0,<4.0.0",
"pydantic>=2.11.7",
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `mcp._tool_manager.get_tools()` | `await mcp.list_tools()` | FastMCP 3.0 | Tests only — 3 tests need updating |
| `FastMCP(host=..., port=...)` | `FastMCP()` + `server.run(host=..., port=...)` | FastMCP 2.3.4 (deprecated), removed 3.0 | Not used in codebase |
| `mcp.sse_app()` | `mcp.http_app(transport='sse')` | FastMCP 3.0 | Not used in codebase |
| `@mcp.tool` returns Tool object | `@mcp.tool` returns original function | FastMCP 3.0 | No impact — current code doesn't use return value |

**Deprecated/outdated:**
- `fastmcp>=2.0.0,<3.0.0`: Replace with `fastmcp>=3.2.0,<4.0.0`
- `pydantic>=2.0.0`: Must become `pydantic>=2.11.7` (FastMCP 3.x hard requirement)

## Open Questions

1. **stdio banner output to stdout**
   - What we know: FastMCP 3.x adds a server banner by default; `show_banner=True` is the default.
   - What's unclear: Does the banner go to stderr or stdout? If stdout, it breaks MCP stdio protocol.
   - Recommendation: Audit `run_stdio_async` in 3.2.0 source (it calls `log_server_banner`). Add `show_banner=False` to be safe, or verify banner uses `rich.console` to stderr.

2. **uvicorn>=0.35 requirement**
   - What we know: FastMCP 3.2.0 requires `uvicorn>=0.35` (up from `>=0.20.0`).
   - What's unclear: Whether `uvicorn>=0.35` has any breaking changes for the monitoring server startup.
   - Recommendation: Update `dev` and `monitoring` optional dependencies to `uvicorn>=0.35`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | Runtime | Yes | 3.11.x | — |
| pip | Package management | Yes | present | — |
| fastmcp 3.2.0 | FMCP-01 | Yes (on PyPI) | 3.2.0 | — |
| pydantic 2.12.5 | Config validation | Yes (installed) | 2.12.5 | Satisfies >=2.11.7 |
| MATLAB Engine API | Execution tests | No (not in CI) | — | Mock (`tests/mocks/matlab_engine_mock.py`) — all tests use mock |

**Missing dependencies with no fallback:** None — all required for phase 1 are available.

**Missing dependencies with fallback:** MATLAB Engine API not installed, but all tests use the existing mock (`tests/mocks/matlab_engine_mock.py`).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.0+ with pytest-asyncio |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `asyncio_mode = "auto"`) |
| Quick run command | `python3 -m pytest tests/test_server.py -q` |
| Full suite command | `python3 -m pytest tests/ --ignore=tests/test_integration_figures.py -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FMCP-01 | Server starts under 3.2.0 | smoke | `python3 -m pytest tests/test_server.py::TestCreateServer -x -q` | Yes |
| FMCP-02 | All tools respond correctly after upgrade | unit | `python3 -m pytest tests/ --ignore=tests/test_integration_figures.py -q` | Yes |
| FMCP-03 | Dashboard routes accessible | unit | `python3 -m pytest tests/test_monitoring_dashboard.py -q` | Yes |
| FMCP-04 | Constructor/run() params work | smoke | `python3 -m pytest tests/test_server.py -q` | Yes |
| FMCP-05 | Import paths resolve | smoke | `python3 -m pytest tests/test_server.py -q` | Yes |

### Current Baseline (fastmcp 2.14.5)
- Full suite: **755 passed** (excluding test_integration_figures.py)
- Under fastmcp 3.2.0 with no code changes: **752 passed, 3 failed**
- The 3 failures are all in `tests/test_server.py` using `_tool_manager`

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/test_server.py -q`
- **Per wave merge:** `python3 -m pytest tests/ --ignore=tests/test_integration_figures.py -q`
- **Phase gate:** Full suite green (755/755) under fastmcp 3.2.0 before `/gsd:verify-work`

### Wave 0 Gaps
None — existing test infrastructure covers all phase requirements. The 3 failing tests need code fixes (not new test files).

## Project Constraints (from CLAUDE.md)

- Python 3.10+ required; pyproject.toml must declare `requires-python = ">=3.10"`
- YAML config format must be preserved (no changes to config.py)
- FastMCP migration must not break existing stdio/SSE clients
- Platform: Windows 10 without admin rights (no service installation, no elevated ports)
- Naming: module files lowercase_underscores, test files `test_<module>.py`
- Code style: 100-char line length via ruff, `from __future__ import annotations` in all modules
- Logging: `logger = logging.getLogger(__name__)` per module, `%s`-style format strings
- `asyncio_mode = "auto"` in pytest config — all async tests run automatically
- Entry point: `matlab-mcp = "matlab_mcp.server:main"` must remain unchanged
- All imports must be absolute (no relative imports)

## Sources

### Primary (HIGH confidence)
- FastMCP 3.2.0 installed package (`/tmp/fastmcp32`) — direct API inspection via Python introspection
- `python3 -m pytest tests/` run against fastmcp 3.2.0 — verified 752/755 pass with 3 known failures
- `pip index versions fastmcp` — confirmed 3.2.0 is latest as of 2026-04-01
- `fastmcp.server.server._check_removed_kwargs` / `_REMOVED_KWARGS` — complete list of 15 removed constructor kwargs

### Secondary (MEDIUM confidence)
- [FastMCP Changelog](https://gofastmcp.com/changelog) — breaking change summary for 3.0
- [FastMCP 3.0 Launch Blog](https://www.jlowin.dev/blog/fastmcp-3-launch) — overview of 3.0 changes
- [FastMCP custom_route issue #556](https://github.com/jlowin/fastmcp/issues/556) — confirms custom_route fix history

### Tertiary (LOW confidence)
- Web search results about FastMCP 3.x ecosystem patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — directly installed and inspected 3.2.0
- Architecture: HIGH — tested all patterns from current codebase against 3.2.0
- Pitfalls: HIGH — discovered by running the full test suite against 3.2.0
- Specific test failures: HIGH — reproduced and documented exact failure mode

**Research date:** 2026-04-01
**Valid until:** 2026-05-01 (stable FastMCP release; low churn expected)
