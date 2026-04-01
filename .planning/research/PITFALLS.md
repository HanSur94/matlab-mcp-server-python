# Pitfalls Research

**Domain:** Python MCP Server — FastMCP 3.0 migration, token auth, Windows no-admin deployment
**Researched:** 2026-04-01
**Confidence:** HIGH (FastMCP 3.0 breaking changes verified from official upgrade guide; Windows behavior from Microsoft docs and community reports; auth pitfalls from multiple security sources)

---

## Critical Pitfalls

### Pitfall 1: Transport Settings Passed to FastMCP Constructor Silently Accepted in 2.x, Fatal in 3.0

**What goes wrong:**
The current server code constructs `FastMCP(...)` with `host`, `port`, `log_level`, `debug`, `sse_path`, `stateless_http`, and transport-related kwargs. In FastMCP 2.x these were accepted (with deprecation warnings). In 3.0 they raise `TypeError` immediately on startup. The server never starts; error appears in logs but the upgrade "looks done."

**Why it happens:**
FastMCP 2.x deprecated these constructor kwargs over multiple minor versions with warnings rather than errors. Teams that ignore deprecation warnings in CI or whose logs are noisy miss the transition entirely. The `<3.0.0` pin in `pyproject.toml` is the only thing preventing this from happening today.

**How to avoid:**
Before unpinning `fastmcp`, audit every call to `FastMCP(...)` across the entire codebase. Move all transport/runtime parameters to `mcp.run(transport="http", host=..., port=..., ...)` or the ASGI `http_app()` call. Affected parameters include:
- `host`, `port`, `log_level`, `debug`
- `sse_path`, `streamable_http_path`, `message_path`
- `json_response`, `stateless_http`
- `on_duplicate_tools`, `on_duplicate_resources`, `on_duplicate_prompts` (now `on_duplicate=`)
- `tool_serializer`, `include_tags`, `exclude_tags`, `tool_transformations`

**Warning signs:**
- Any `DeprecationWarning` about constructor kwargs in current logs under 2.14.5
- `TypeError: FastMCP.__init__() got an unexpected keyword argument 'host'` on startup after upgrade

**Phase to address:** FastMCP 3.0 upgrade phase — must be the first change before any other migration work.

---

### Pitfall 2: `get_tools()` / `get_resources()` Return Dict in 2.x, List in 3.0 — Silent Logic Errors

**What goes wrong:**
Any code that calls `await server.get_tools()` (renamed to `list_tools()`) and then indexes the result by name (e.g., `tools["execute_code"]`) will raise a `TypeError` at runtime in 3.0. Worse, if the custom tool loading or YAML-based tool registration code indexes into the returned collection, it fails only when that code path is exercised — not at startup.

**Why it happens:**
The rename from `get_*` to `list_*` and the change in return type from `dict` to `list` are non-obvious. The method name still exists (raises `AttributeError`), making the failure obvious. But code that stored the result and indexed it later may only fail in specific workflows.

**How to avoid:**
Search for all calls to `get_tools()`, `get_resources()`, `get_prompts()`, `get_resource_templates()`. Replace with `list_*` variants. Replace dict-style access with iteration: `next((t for t in tools if t.name == "my_tool"), None)`.

**Warning signs:**
- `AttributeError: 'FastMCP' object has no attribute 'get_tools'` anywhere in logs
- YAML tool loading works at startup but fails when listing tools via the monitoring dashboard

**Phase to address:** FastMCP 3.0 upgrade phase.

---

### Pitfall 3: Context State Methods Are Now Async — Breaks Any Tool Using `ctx.get_state()` / `ctx.set_state()`

**What goes wrong:**
If any tool handler calls `ctx.set_state("key", value)` or `ctx.get_state("key")` without `await`, the call silently returns a coroutine object instead of executing. The state is never set/read; dependent logic produces wrong results or `None`. No exception is raised.

**Why it happens:**
Python does not error on calling an async method without `await` — it returns an un-awaited coroutine. This is a classic async bug that passes linting and most tests unless the test explicitly checks the return value and state effects.

**How to avoid:**
After upgrading, run `grep -r "ctx\.set_state\|ctx\.get_state"` across all tool files. Add `await` to every call. Also note: state values must now be JSON-serializable. Any tool storing non-serializable objects (MATLAB engine handles, numpy arrays, etc.) must pass `serializable=False` explicitly or convert to serializable form first.

**Warning signs:**
- Tools that read session state always return `None` or default values after upgrade
- No error thrown — silent wrong behavior is the only symptom
- `RuntimeWarning: coroutine 'Context.set_state' was never awaited` in Python warnings

**Phase to address:** FastMCP 3.0 upgrade phase — add explicit integration test for session state round-trip.

---

### Pitfall 4: Windows Firewall Blocks Inbound Connections Without Admin — Agents Can't Connect

**What goes wrong:**
When the MCP server starts on Windows 10 without admin rights and binds to a port above 1024, the Windows Firewall blocks all inbound connections from other machines by default. The server appears to start successfully (no error), Python reports it is listening, but remote agents (Codex CLI, Claude Code on another host) receive connection refused or timeout. The user sees nothing wrong until they try to connect.

Additionally, the first time any Python process opens a network port, Windows Defender pops up a UAC dialog asking whether to allow it. Without admin rights, the user cannot approve this dialog, and Windows creates a block rule silently.

**Why it happens:**
Windows Firewall "Public" and "Private" network profiles both block inbound connections to non-system processes by default. Creating an exception requires admin rights. Corporate IT policies often prevent standard users from managing firewall rules at all.

**How to avoid:**
Design the auth + transport phase so that:
1. The default bind address is `127.0.0.1` (loopback), not `0.0.0.0`. Agents on the same machine work without any firewall issue. Document that remote access requires an admin to add the inbound rule once.
2. Provide a one-line PowerShell snippet for admins to create the rule (or document that IT must approve it).
3. Test on a non-admin Windows 10 account in CI before release.

For the primary use case (agent and server co-located on the same machine), loopback-only binding completely avoids the firewall problem.

**Warning signs:**
- Server starts and logs "Listening on 0.0.0.0:8080" but remote agents time out
- No error on the server side — the bind succeeds, packets are just dropped by the firewall
- `netstat -an` shows the port listening but Windows Security Center shows no inbound rule for Python

**Phase to address:** Windows compatibility phase — establish loopback-default binding in the transport configuration.

---

### Pitfall 5: Codex CLI Does Not Support Legacy SSE Transport — Only Streamable HTTP

**What goes wrong:**
Codex CLI was documented as supporting SSE endpoints but the documentation was incorrect at release. Codex CLI only supports Streamable HTTP (`/mcp` endpoint), not the legacy SSE protocol (`/sse` endpoint). Connecting Codex CLI to the existing SSE transport produces a 404 and the connection fails. This is the exact failure that motivated this milestone.

**Why it happens:**
FastMCP 2.x exposes both `/sse` (legacy) and `/mcp` (streamable HTTP) endpoints. Codex CLI's release notes falsely claimed SSE support. Users who followed the "SSE URL" convention found their setup completely broken. The fix requires switching to streamable HTTP transport, not tweaking auth.

**How to avoid:**
When adding transport support, implement Streamable HTTP (`transport="http"` in FastMCP 3.0) as the primary transport, not SSE. In configuration examples and documentation, always give agents the `/mcp` endpoint URL. Keep SSE only for backward compatibility with Claude Code Desktop (which does support SSE).

Do not invest time debugging why Codex CLI won't connect to the SSE endpoint — it is a known limitation of Codex CLI, not a server misconfiguration.

**Warning signs:**
- Codex CLI reports `404 Not Found` on the SSE endpoint URL
- `curl -N http://localhost:8080/sse` works but Codex CLI still fails
- No auth-related error message — the issue is protocol mismatch, not credentials

**Phase to address:** Transport upgrade phase — add Streamable HTTP transport as the default, test Codex CLI connectivity explicitly.

---

### Pitfall 6: Bearer Token Stored in Config File Gets Committed to Git

**What goes wrong:**
The natural way to configure auth is to add `auth_token: "secret"` to `config.yaml`. If the config file is not in `.gitignore`, or if users copy the example config and forget to scrub the token, real tokens end up in version history. The MATLAB MCP server targets corporate environments where the codebase may be shared internally — leaked tokens give any colleague full MATLAB code execution access.

**Why it happens:**
Convenience — the config.yaml pattern is already established in the codebase. Tokens feel like configuration, not secrets. The distinction between "config values that can be committed" and "secrets that must not" is easy to overlook.

**How to avoid:**
Never read auth tokens directly from `config.yaml`. Support only two secure patterns:
1. Environment variable: `MATLAB_MCP_AUTH_TOKEN` (document this as the canonical approach)
2. A separate secrets file (e.g., `.env`) that is `.gitignore`-d by default and documented clearly

The `config.yaml` may contain a `auth_token_env_var` key pointing to the environment variable name, but never the token value itself. Add a startup check that warns if a token value (rather than env var reference) appears in the config.

**Warning signs:**
- Token value appears in `config.yaml` in any example, test fixture, or commit
- `git log --all -S "auth_token"` reveals tokens in history
- CI environment exposes the token in build logs

**Phase to address:** Auth implementation phase — establish the env-var-only pattern before writing any token validation code.

---

### Pitfall 7: OAuth Storage Default Changed to FileTreeStore — Existing Deployments Re-Register Clients on Upgrade

**What goes wrong:**
FastMCP 3.0 changed the default OAuth client storage from `DiskStore` (backed by diskcache/pickle) to `FileTreeStore` due to CVE-2025-69872 (pickle deserialization RCE). Any deployment that used the default DiskStore will have all registered clients wiped on the first startup after upgrade. Agents that cached their client registration silently fail to authenticate until they re-register.

**Why it happens:**
This is a deliberate security fix that breaks existing state. The FastMCP upgrade guide documents that re-registration is automatic and harmless — but it still causes a one-time auth failure that looks like a server misconfiguration.

**How to avoid:**
Since this project is implementing token-based auth (not OAuth), this pitfall is lower risk. However, if OAuth flows are ever added later, document the expected re-registration on first upgrade. In the v2.0 milestone, avoid using FastMCP's OAuth machinery entirely — use simpler bearer token validation via middleware instead.

**Warning signs:**
- After upgrade, agents report "client not registered" or 401 errors on first connection
- Resolved by the agent re-initiating the handshake (often automatically)
- DiskStore explicitly in code means re-introducing the CVE-2025-69872 vulnerable dependency

**Phase to address:** FastMCP 3.0 upgrade phase — document in upgrade notes, do not use DiskStore.

---

### Pitfall 8: MATLAB Engine API Python Package Requires Admin or PYTHONPATH Gymnastics on Windows

**What goes wrong:**
On Windows 10 without admin rights, installing `matlabengine` via `pip install matlabengine` into a system Python location fails with permission errors. Installing into a user-local virtualenv works, but only if the virtualenv is on a drive/path accessible to the MATLAB process. In corporate environments, home drives (`%USERPROFILE%`) are often redirected to network shares with slow I/O, causing MATLAB engine startup to time out.

Additionally, MATLAB's JIT compiler and COM server registration happen at install time and may require elevation. Antivirus software in corporate environments (McAfee, Crowdstrike, Defender ATP) is known to slow or block MATLAB process spawning, causing engine pool startup to appear hung.

**How to avoid:**
1. Always test in a virtualenv located on a local drive (e.g., `C:\Users\<user>\venvs\`), not a network-mapped drive.
2. In installation documentation, specify `pip install --user matlabengine` as the no-admin path, with explicit PYTHONPATH configuration instructions.
3. Make engine startup timeout configurable (`pool.engine_start_timeout`), with a generous default (120s) on Windows.
4. Provide a diagnostic mode (`--inspect`) — already implemented — and document it prominently for Windows users who cannot get engines to start.

**Warning signs:**
- `matlab.engine.start_matlab()` hangs indefinitely on Windows without timing out
- `PermissionError` during pip install of matlabengine
- Engine pool reports 0 healthy engines after startup on network-mapped drives

**Phase to address:** Windows compatibility phase — test engine startup on a no-admin Windows 10 VM with a locally-hosted virtualenv.

---

### Pitfall 9: Auth Provider Auto-Loading from Environment Variables Removed in FastMCP 3.0

**What goes wrong:**
FastMCP 2.x auth providers (e.g., `GitHubProvider`) auto-loaded credentials from `FASTMCP_SERVER_AUTH_GITHUB_*` environment variables. In 3.0, providers raise an error if credentials are not passed explicitly. Any code that relied on env-var auto-loading will fail silently if the provider is constructed without arguments — or raise a configuration error that looks like a missing dependency.

**Why it happens:**
The "magic" environment variable loading was considered too implicit and was removed to give developers explicit control. The failure mode is not obvious because the error surfaces at first authentication attempt, not at server startup.

**How to avoid:**
For v2.0, avoid FastMCP's built-in auth providers entirely. Implement a simple bearer token middleware that reads from `os.environ["MATLAB_MCP_AUTH_TOKEN"]` and validates incoming `Authorization: Bearer <token>` headers. This is simpler, more transparent, and not affected by FastMCP auth provider changes.

**Warning signs:**
- `TypeError: GitHubProvider.__init__() missing required argument 'client_id'` after upgrade
- Auth that worked in 2.x silently does nothing after upgrade
- Startup succeeds but all requests return 401

**Phase to address:** Auth implementation phase — define the auth interface before the FastMCP 3.0 upgrade so auth code does not depend on FastMCP's provider system.

---

### Pitfall 10: Decorator Return Value Change Breaks Any Code Inspecting Tool `.name` or `.description`

**What goes wrong:**
In FastMCP 2.x, `@mcp.tool()` returned a component object with `.name`, `.description`, and other attributes. In 3.0, it returns the original function unchanged. Any code that stored the decorated result and accessed `.name` or `.description` on it raises `AttributeError`. This likely affects the custom YAML tool loading code, which introspects registered tools to validate or display them.

**How to avoid:**
Search for any code that accesses attributes on the return value of `@mcp.tool`, `@mcp.resource`, or `@mcp.prompt` decorators. Remove those attribute accesses. Use `server.list_tools()` to inspect registered tools instead. As a temporary escape hatch during migration, set `FASTMCP_DECORATOR_MODE=object` — but do not ship with this env var set permanently.

**Warning signs:**
- `AttributeError: 'function' object has no attribute 'name'` in YAML tool loader or test fixtures
- Custom tool registration code that stored decorated functions and later called `.name` on them

**Phase to address:** FastMCP 3.0 upgrade phase — verify YAML custom tool loading still works after upgrade.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hardcode auth token in config.yaml for testing | Faster local dev setup | Token leaks into git history, CI logs | Never — use env vars from day one |
| Bind to `0.0.0.0` as default transport host | Works immediately for remote agents | Firewall prompt on Windows, network exposure without auth | Never as default; opt-in only |
| Keep `FASTMCP_DECORATOR_MODE=object` after migration | Avoid decorator refactor | Permanently suppresses v3.0 behavior; breaks on next major | MVP/transition only, remove within same phase |
| Skip testing on non-admin Windows VM | Saves CI setup time | Ships with firewall/permission bugs invisible in dev | Never for v2.0 milestone |
| Reuse existing `require_proxy_auth` flag for new token auth | Minimal code change | Proxy auth and bearer token auth are different models; confuses users | Never — implement cleanly |
| Auto-load token from `FASTMCP_SERVER_AUTH_*` env vars | Less config to write | Removed in FastMCP 3.0; breaks on upgrade | Never — use explicit env var name |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Codex CLI + MCP server | Pointing Codex at the `/sse` endpoint URL | Use the `/mcp` Streamable HTTP endpoint; Codex CLI does not support legacy SSE |
| Claude Code + MCP server | Assuming all agents handle bearer tokens identically | Claude Code supports `Authorization: Bearer` headers in HTTP transport; verify per-agent header passing in config |
| Windows Defender Firewall + Python server | Assuming loopback access always works without admin | Loopback (`127.0.0.1`) bypasses firewall; remote access (`0.0.0.0`) requires admin-created inbound rule |
| MATLAB Engine API + corporate Windows | Installing matlabengine on a network-mapped home drive | Install virtualenv on local `C:\` drive; network drives cause startup timeouts |
| FastMCP 3.0 + existing SSE clients | Keeping `/sse` endpoint for backward compat but testing only with new clients | Keep SSE running in parallel during migration; existing Claude Code Desktop users depend on it |
| FastMCP 3.0 auth middleware + stateless HTTP | Writing auth middleware that stores per-request state | Stateless HTTP mode creates a new session per request; middleware must be stateless too |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Synchronous auth token validation on every request | P99 latency spikes under load | Pre-load and cache the expected token hash at startup; compare hashes not strings | At >10 concurrent agent requests |
| Engine pool health check blocks all acquisitions (existing bug) | All job submissions freeze for up to 60s | Already documented in CONCERNS.md; fix before multi-user production | At >2 concurrent users during health check interval |
| SQLite WAL files on network drive | Intermittent metric write failures; orphaned `.wal` files | Keep SQLite store on local filesystem; document this requirement | Always on network drives — not scale-dependent |
| Blocking MATLAB engine startup in async event loop | Server hangs during engine pool initialization | Use `asyncio.to_thread()` for engine startup calls; already partially done | On first startup with slow MATLAB license check |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Accepting bearer tokens via URL query parameter (`?token=...`) | Token appears in server access logs, proxy logs, browser history | Accept tokens only via `Authorization: Bearer` header |
| Logging the full `Authorization` header on auth failure | Token leaks into log files | Log only "Authorization header present: yes/no" and masked token prefix (first 8 chars) |
| Single shared static token for all agents | No per-agent revocation; one compromised agent invalidates all | Support multiple named tokens in config; allow per-token revocation |
| Not validating token on every request (caching auth result by IP) | IP spoofing bypasses auth | Validate token on every request; IP caching is never safe |
| Returning `403 Forbidden` vs `401 Unauthorized` incorrectly | Clients that auto-retry on 401 get confused; Codex CLI may not retry | Return `401` with `WWW-Authenticate: Bearer` when no token present; `403` when token is invalid/expired |
| Enabling SSE transport without auth during the transition period | Any network-local agent can execute MATLAB code without credentials | The existing `require_proxy_auth` warning (CONCERNS.md) must be converted to a hard startup error for SSE with no auth configured |

---

## "Looks Done But Isn't" Checklist

- [ ] **FastMCP 3.0 upgrade:** Constructor kwargs removed from `FastMCP(...)` call — verify by grepping `FastMCP(` in `server.py` and confirming no transport kwargs are present
- [ ] **Auth implementation:** Token is read from environment variable, not config.yaml — verify `grep -r "auth_token"` shows no raw values in yaml files
- [ ] **Streamable HTTP transport:** Codex CLI successfully connects end-to-end with a real bearer token — not just that the server starts
- [ ] **Windows compatibility:** Tested on a non-admin Windows 10 account with Python in a local-drive virtualenv — not just on macOS or admin Windows
- [ ] **SSE backward compat:** Existing Claude Code Desktop connections survive the FastMCP upgrade — test before declaring migration complete
- [ ] **Decorator behavior:** YAML custom tool loader works after `@mcp.tool` returns a plain function — run custom tool loading tests explicitly
- [ ] **State methods async:** All `ctx.get_state()` / `ctx.set_state()` calls have `await` — verify with `grep -n "ctx\.set_state\|ctx\.get_state"` and confirm no un-awaited calls
- [ ] **Firewall guidance:** README documents that Windows remote access requires admin to add a firewall rule — and provides the PowerShell command to do so
- [ ] **Auth error messages:** 401 vs 403 distinction is correct and clients (especially Codex CLI) behave correctly on each response code

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Constructor kwargs breaking upgrade | LOW | Revert to 2.14.5 pin, fix kwargs, re-upgrade |
| Token committed to git | HIGH | Rotate token immediately, use `git filter-repo` to scrub history, audit access logs for unauthorized use |
| Windows firewall blocking agents | LOW | Switch default bind to `127.0.0.1`; document admin step for remote access |
| State methods missing await | MEDIUM | Tools silently return stale state; must audit all tool files and add integration test for state round-trip |
| Codex CLI connecting to SSE endpoint | LOW | Update agent config to point to `/mcp` endpoint instead of `/sse` |
| OAuth storage migration breaks existing clients | LOW | Clients auto-re-register on next connection; no user action needed |
| MATLAB engine startup hangs on Windows network drive | MEDIUM | Move virtualenv to local drive; increase `engine_start_timeout`; use `--inspect` mode to verify server starts |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Constructor kwargs removed in 3.0 | FastMCP 3.0 upgrade phase | `python -c "from src.matlab_mcp.server import create_server"` succeeds with fastmcp 3.x installed |
| `get_tools()` dict → `list_tools()` list | FastMCP 3.0 upgrade phase | All tool-listing code paths exercised in unit tests |
| Context state methods require await | FastMCP 3.0 upgrade phase | Integration test: set state in one tool call, read in next, assert correct value |
| Windows firewall blocks inbound | Windows compatibility phase | Non-admin Windows 10 VM: agent connects to server on loopback without firewall prompt |
| Codex CLI only supports Streamable HTTP | Transport upgrade phase | Codex CLI e2e test: connects to `/mcp` endpoint, executes code, returns result |
| Bearer token in config.yaml | Auth implementation phase | `git log --all -S "auth_token" -- "*.yaml"` returns no results |
| OAuth DiskStore CVE / re-registration | FastMCP 3.0 upgrade phase | Do not use DiskStore; verify no diskcache in `pip list` |
| MATLAB engine on network drive | Windows compatibility phase | Engine pool starts within 30s on non-admin Windows 10 with local virtualenv |
| Auth provider env-var auto-loading removed | Auth implementation phase | Auth does not use FastMCP provider system; plain middleware validates env var |
| Decorator return value change | FastMCP 3.0 upgrade phase | YAML custom tool loading integration test passes |

---

## Sources

- FastMCP 3.0 upgrade guide (official): https://gofastmcp.com/getting-started/upgrading/from-fastmcp-2
- FastMCP HTTP deployment documentation: https://gofastmcp.com/deployment/http
- FastMCP 3.0 announcement: https://www.jlowin.dev/blog/fastmcp-3-whats-new
- CVE-2025-69872 (diskcache pickle vulnerability): https://nvd.nist.gov/vuln/detail/CVE-2025-69872
- FastMCP diskcache CVE issue: https://github.com/PrefectHQ/fastmcp/issues/3166
- Codex CLI SSE support bug (documentation error): https://github.com/openai/codex/issues/5634
- Codex CLI token refresh limitation: https://github.com/openai/codex/issues/7318
- MCP server security research 2025: https://astrix.security/learn/blog/state-of-mcp-server-security-2025/
- MCP auth best practices: https://toolradar.com/blog/mcp-server-security-best-practices
- Windows firewall admin requirement: https://learn.microsoft.com/en-us/answers/questions/292450/what-port(s)-doesnt-need-administrator-privilege-t
- MATLAB Engine API Python no-admin install: https://gist.github.com/hagenw/85f00620067dd01daee7db916d94a7ea
- MATLAB antivirus interference: https://www.mathworks.com/matlabcentral/answers/2163100-how-to-detect-and-prevent-antivirus-from-affecting-matlab-and-simulink-performance
- Project codebase concerns: `.planning/codebase/CONCERNS.md`

---
*Pitfalls research for: MATLAB MCP Server v2.0 — FastMCP 3.0 migration + auth + Windows no-admin*
*Researched: 2026-04-01*
