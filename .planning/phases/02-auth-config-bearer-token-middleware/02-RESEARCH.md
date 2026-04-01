# Phase 2: Auth Config + Bearer Token Middleware - Research

**Researched:** 2026-04-01
**Domain:** ASGI middleware (Starlette), Python `secrets`/`hmac`, FastMCP 3.2 run API
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Opaque random hex tokens (32 bytes / 64 hex chars) — no JWT, no expiry semantics
- No token expiry — static tokens, rotate by generating new token and restarting server
- Constant-time comparison via `hmac.compare_digest` to prevent timing attacks
- Single token from `MATLAB_MCP_AUTH_TOKEN` env var — no multi-token support
- Default CORS allowed origins: `*` (any origin) — agents connect from various hosts
- CORS methods: `GET, POST, OPTIONS` — standard for MCP protocol
- CORS headers: `Authorization, Content-Type, Accept` — minimum needed for bearer auth + JSON
- Skip CORS entirely on stdio transport — no HTTP layer
- Starlette ASGI middleware — intercepts before FastMCP, clean separation of concerns
- Log `WARNING` at startup if any token-like key (e.g. `security.auth_token`) exists in loaded config.yaml
- Allow `/health` without auth — load balancers need unauthenticated health checks
- Error responses: JSON body `{"error": "unauthorized", "message": "..."}` with `WWW-Authenticate: Bearer` header

### Claude's Discretion
- Internal module organization (single file vs split auth/cors modules)
- Test structure and fixtures
- Exact CLI output format for `--generate-token`

### Deferred Ideas (OUT OF SCOPE)
- Per-tool scope enforcement (AUTH scopes) — tracked as AAUTH-01 in v2 requirements
- Token rotation without restart — tracked as AAUTH-02 in v2 requirements
- Agent-readable 401 JSON with docs URL — tracked as AAUTH-03 in v2 requirements
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTH-01 | Server accepts bearer token via `Authorization: Bearer <token>` header on HTTP transport | `BearerAuthMiddleware` parses `Authorization` header; verified Starlette ASGI pattern |
| AUTH-02 | Auth token configured exclusively via `MATLAB_MCP_AUTH_TOKEN` env var (never in config.yaml) | `os.environ.get("MATLAB_MCP_AUTH_TOKEN")` in lifespan; startup warning scans loaded YAML dict |
| AUTH-03 | Invalid or missing token returns HTTP 401 with `WWW-Authenticate` header | Middleware sends raw ASGI `http.response.start` with status 401 and `www-authenticate: Bearer` header |
| AUTH-04 | CORS headers are set correctly for browser-based agent UIs | `starlette.middleware.cors.CORSMiddleware` wraps the Starlette app via `Middleware(CORSMiddleware, ...)` |
| AUTH-05 | stdio transport bypasses authentication entirely | Token read and middleware wired only when `transport != "stdio"`; stdio path unchanged |
| AUTH-06 | `--generate-token` CLI flag prints a ready-to-use signed token and env var snippet | `argparse` flag in `main()`; `secrets.token_hex(32)` generation; print then `sys.exit(0)` |
</phase_requirements>

---

## Summary

Phase 2 adds bearer token authentication to the SSE/HTTP transports by wiring two Starlette-compatible ASGI middleware classes into FastMCP 3.2's `run()` / `http_app()` call. The token lives exclusively in the `MATLAB_MCP_AUTH_TOKEN` environment variable; the server warns at startup if a token-like field is detected in config.yaml to prevent accidental credential exposure.

FastMCP 3.2 exposes a `middleware` keyword argument on `run_http_async()` (and transitively on `run()` when transport is `sse`/`http`). The middleware list is passed directly to Starlette's `StarletteWithLifespan` constructor via `create_sse_app` / `create_streamable_http_app`. This means **standard Starlette `Middleware(...)` wrappers work without any monkey-patching** — the integration point is clean and public API.

The auth middleware must be a pure ASGI class (not `BaseHTTPMiddleware`) to avoid Starlette's double-send bug with streaming responses. It reads the `Authorization` header, performs a constant-time comparison with `hmac.compare_digest`, bypasses auth for `/health`, and returns a raw ASGI 401 response with `WWW-Authenticate: Bearer` and `Content-Type: application/json` headers when the check fails.

**Primary recommendation:** Write one new module `src/matlab_mcp/auth/middleware.py` containing `BearerAuthMiddleware` (pure ASGI class) and `_get_auth_token()`. Wire it into `server.py::main()` via the `middleware=[...]` kwarg on `server.run(transport="sse", ..., middleware=[...])`. CORS is a second `Middleware(CORSMiddleware, ...)` entry in the same list.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `starlette` (already dep) | 0.52.x | ASGI middleware base, `CORSMiddleware` | Ships with FastMCP; no new dep needed |
| `hmac` (stdlib) | 3.10+ | Constant-time token comparison | `hmac.compare_digest` is the Python-idiomatic timing-safe comparator |
| `secrets` (stdlib) | 3.10+ | Cryptographically random token generation | `secrets.token_hex(32)` produces 64-char hex token |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `os` (stdlib) | — | Read `MATLAB_MCP_AUTH_TOKEN` | In `lifespan()` and middleware init |
| `argparse` (stdlib) | — | `--generate-token` CLI flag | Already used in `main()` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pure ASGI class | `BaseHTTPMiddleware` | `BaseHTTPMiddleware` works but has a known Starlette streaming response double-send bug; raw ASGI is safer and already demonstrated in FastMCP's own `RequireAuthMiddleware` |
| `starlette.middleware.cors.CORSMiddleware` | Custom CORS logic | Never hand-roll CORS — pre-flight `OPTIONS` edge cases are complex |

**Installation:** No new dependencies required. All libraries (`starlette`, `hmac`, `secrets`, `os`, `argparse`) are already present.

---

## Architecture Patterns

### Recommended Module Structure
```
src/matlab_mcp/
└── auth/
    ├── __init__.py       # empty or re-exports BearerAuthMiddleware
    └── middleware.py     # BearerAuthMiddleware (pure ASGI), _get_auth_token()
```

Single-file is also acceptable given the scope. Separate `auth/` package is preferred for Phase 4 HITL and possible future auth expansion.

### Pattern 1: Pure ASGI Middleware Class

**What:** Intercepts HTTP requests at the ASGI level before FastMCP processes them.
**When to use:** Always for auth — avoids `BaseHTTPMiddleware` streaming bug.

```python
# Source: FastMCP source fastmcp/server/auth/middleware.py (verified pattern)
import hmac
import json
import os
from starlette.types import ASGIApp, Receive, Scope, Send

_BYPASS_PATHS = {"/health"}

class BearerAuthMiddleware:
    """Pure-ASGI bearer token authentication middleware.

    Validates Authorization: Bearer <token> header on every HTTP request,
    except paths in _BYPASS_PATHS. stdio transport never reaches this middleware.
    """

    def __init__(self, app: ASGIApp) -> None:
        self._app = app
        self._token: str | None = os.environ.get("MATLAB_MCP_AUTH_TOKEN")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        # Bypass auth for health check endpoint
        path = scope.get("path", "")
        if path in _BYPASS_PATHS:
            await self._app(scope, receive, send)
            return

        # No token configured — pass through (auth disabled)
        if not self._token:
            await self._app(scope, receive, send)
            return

        # Extract Authorization header
        headers = dict(scope.get("headers", []))
        auth_header: bytes = headers.get(b"authorization", b"")
        provided_token = ""
        if auth_header.lower().startswith(b"bearer "):
            provided_token = auth_header[7:].decode("utf-8", errors="replace")

        # Constant-time comparison
        if hmac.compare_digest(provided_token, self._token):
            await self._app(scope, receive, send)
            return

        # Reject — send 401
        body = json.dumps({"error": "unauthorized", "message": "Valid Bearer token required"}).encode()
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"www-authenticate", b"Bearer"),
            ],
        })
        await send({"type": "http.response.body", "body": body})
```

### Pattern 2: Wiring Middleware into FastMCP `run()`

**What:** Pass middleware list via `transport_kwargs` to FastMCP's `run_http_async`.
**When to use:** SSE and HTTP transports only; stdio bypasses entirely.

```python
# Source: fastmcp/server/server.py FastMCP.run_http_async (verified)
# In server.py main(), replace the sse run call:

from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from matlab_mcp.auth.middleware import BearerAuthMiddleware

middleware: list[Middleware] = [
    Middleware(BearerAuthMiddleware),          # auth first (outermost)
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept"],
    ),
]

server.run(
    transport="sse",
    host=config.server.host,
    port=config.server.port,
    middleware=middleware,
)
```

**Important:** Middleware order matters. `BearerAuthMiddleware` should be outermost (first in list) so auth runs before CORS processing.

### Pattern 3: Startup Warning for Token in Config

**What:** Scan the raw loaded YAML dict for keys that look like token storage.
**When to use:** In `lifespan()` or `main()` after `load_config()`.

```python
# In lifespan() or in main() after load_config():
_TOKEN_KEY_PATTERNS = {"auth_token", "bearer_token", "api_key", "secret", "token"}

def _warn_if_token_in_config(raw_config_data: dict) -> None:
    """Emit WARNING if config.yaml contains token-like keys."""
    for section, values in raw_config_data.items():
        if not isinstance(values, dict):
            continue
        for key in values:
            if any(pat in key.lower() for pat in _TOKEN_KEY_PATTERNS):
                logger.warning(
                    "Config field '%s.%s' looks like a token/secret. "
                    "Auth tokens must be set via MATLAB_MCP_AUTH_TOKEN env var, "
                    "not config.yaml.",
                    section, key,
                )
```

This requires `load_config()` to expose (or return alongside) the raw `data` dict, or a separate YAML read. The simplest approach: add an optional `_warn_if_token_in_config(data)` call inside `load_config()` after YAML parsing, before `AppConfig.model_validate(data)`.

### Pattern 4: `--generate-token` CLI Flag

```python
# In main(), add to argparse before load_config():
parser.add_argument(
    "--generate-token",
    action="store_true",
    help="Generate a bearer token and print env var snippet, then exit",
)
args = parser.parse_args()

if args.generate_token:
    import secrets
    token = secrets.token_hex(32)
    print(f"Generated token (64 hex chars):\n  {token}")
    print(f"\nSet environment variable:")
    print(f"  export MATLAB_MCP_AUTH_TOKEN={token}")
    print(f"\nOr on Windows (cmd):")
    print(f"  set MATLAB_MCP_AUTH_TOKEN={token}")
    sys.exit(0)
```

### Anti-Patterns to Avoid

- **`BaseHTTPMiddleware` for auth:** Starlette's `BaseHTTPMiddleware` buffers the full request body and has a known streaming double-send issue. FastMCP's own auth middleware (`fastmcp/server/auth/middleware.py`) uses pure ASGI — follow that pattern.
- **Storing token in `SecurityConfig`:** Token must never be serialized to config.yaml. Do not add a `auth_token` field to any Pydantic config model.
- **Reading token inside each request handler:** The token should be read once at middleware init time (`os.environ.get(...)` in `__init__`), not on every request.
- **String equality `==` for token comparison:** Always use `hmac.compare_digest` to prevent timing oracle attacks. Even for "simple" static tokens.
- **Applying middleware to stdio transport:** stdio has no HTTP layer; passing middleware to `server.run(transport="stdio", ...)` is a no-op but confusing. Only wire middleware for HTTP/SSE paths.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| CORS headers | Custom CORS logic in middleware | `starlette.middleware.cors.CORSMiddleware` | Pre-flight `OPTIONS` requests, `Access-Control-Max-Age`, `Vary` header, credential mode edge cases are all handled |
| Cryptographic random token | `random.random()` or `uuid4()` | `secrets.token_hex(32)` | `secrets` module uses OS CSPRNG; `random` is not cryptographically secure |

**Key insight:** CORS is never "just adding a header" — pre-flight `OPTIONS` requests and wildcard-vs-credential interaction have subtle rules. Starlette's `CORSMiddleware` handles all of this correctly.

---

## Common Pitfalls

### Pitfall 1: Middleware Order (Auth vs CORS)
**What goes wrong:** CORS `OPTIONS` pre-flight requests fail with 401 if auth runs before CORS. Browsers send `OPTIONS` without credentials, so auth middleware rejects the pre-flight before CORS can respond with `200 OK`.
**Why it happens:** CORS pre-flight requests deliberately omit `Authorization` headers.
**How to avoid:** Place `BearerAuthMiddleware` so that `OPTIONS` requests bypass auth, OR place CORS outermost. Simplest fix: in `BearerAuthMiddleware.__call__`, check `scope.get("method")` — if `OPTIONS`, pass through unconditionally.
**Warning signs:** Browser console shows `401` on `OPTIONS` pre-flight; no CORS headers on error response.

```python
# Add this check before token validation:
if scope.get("method") == "OPTIONS":
    await self._app(scope, receive, send)
    return
```

### Pitfall 2: `hmac.compare_digest` Requires Same Type
**What goes wrong:** `TypeError: a and b must both be str or both be bytes` if one side is bytes from decoding and the other is str.
**Why it happens:** `hmac.compare_digest` enforces type consistency as part of its security model.
**How to avoid:** Ensure both operands are `str`. Decode the header value with `.decode("utf-8", errors="replace")` and store the env var token as `str`.
**Warning signs:** `TypeError` on valid requests.

### Pitfall 3: Token Read Timing
**What goes wrong:** Token read at import time (module level) won't pick up env var set after process start (e.g., in test fixtures that set `os.environ`).
**Why it happens:** Module-level code runs once at import.
**How to avoid:** Read `os.environ.get("MATLAB_MCP_AUTH_TOKEN")` inside `BearerAuthMiddleware.__init__`, which is called during server construction (after env is set).
**Warning signs:** Tests that set env var in a fixture see `None` for the token.

### Pitfall 4: Starlette `Middleware` Wrapper is a Class Factory
**What goes wrong:** `Middleware(BearerAuthMiddleware)` does NOT instantiate the middleware immediately — Starlette instantiates it lazily when building the app.
**Why it happens:** `starlette.middleware.Middleware` is a descriptor, not an instance.
**How to avoid:** Pass the class (not an instance) as the first argument. All constructor kwargs go as additional keyword args to `Middleware(...)`.
**Warning signs:** `TypeError: 'Middleware' object is not callable` if you pass an instance.

### Pitfall 5: FastMCP `run()` and `middleware` kwarg routing
**What goes wrong:** Passing `middleware=` to `server.run(transport="sse", ...)` does nothing for the current codebase — `run()` delegates to `run_http_async()` via `**transport_kwargs`, which accepts `middleware`. But the current `server.py` calls `server.run(transport="sse", host=..., port=...)` without `middleware`. The parameter must be added explicitly.
**Why it happens:** The existing code path was written pre-auth.
**How to avoid:** Build the middleware list conditionally (only for SSE/HTTP) and pass it as a kwarg to `server.run(...)`.
**Warning signs:** Middleware is constructed but auth is never enforced.

---

## Code Examples

### Token Generation (verified — stdlib `secrets`)
```python
# Source: Python docs secrets module (stdlib, Python 3.10+)
import secrets
token = secrets.token_hex(32)  # 64-character hex string, 256 bits of entropy
```

### CORS Middleware Wiring (verified — Starlette source)
```python
# Source: starlette.middleware.cors.CORSMiddleware (Starlette 0.52.x)
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

Middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)
```

### FastMCP SSE run with middleware (verified — fastmcp/server/server.py)
```python
# Source: fastmcp.server.server.FastMCP.run_http_async (FastMCP 3.2.0)
server.run(
    transport="sse",
    host=config.server.host,
    port=config.server.port,
    middleware=[
        Middleware(BearerAuthMiddleware),
        Middleware(CORSMiddleware, allow_origins=["*"], ...),
    ],
)
```

### Startup Token-in-Config Warning (verified pattern — existing logger usage in codebase)
```python
# In load_config() after yaml.safe_load(), before AppConfig.model_validate():
_SENSITIVE_KEY_PATTERNS = {"token", "secret", "api_key", "password", "bearer"}

for section, section_data in data.items():
    if not isinstance(section_data, dict):
        continue
    for key in section_data:
        if any(pat in key.lower() for pat in _SENSITIVE_KEY_PATTERNS):
            logger.warning(
                "Config key '%s.%s' may contain a secret. "
                "Use MATLAB_MCP_AUTH_TOKEN env var for auth tokens.",
                section, key,
            )
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `require_proxy_auth` flag (delegate to reverse proxy) | Direct bearer token middleware | Phase 2 (this phase) | Server is self-authenticating; no proxy required |
| `BaseHTTPMiddleware` for ASGI auth | Pure ASGI class middleware | Starlette ~0.20 (2022) | No streaming double-send bug |

**Deprecated/outdated:**
- `config.security.require_proxy_auth`: This field remains in `SecurityConfig` for backward compatibility but is superseded by `MATLAB_MCP_AUTH_TOKEN`. The startup warning code should check if both are configured simultaneously.

---

## Open Questions

1. **`--generate-token` exact output format**
   - What we know: User decision says "print ready-to-use token and env var snippet"
   - What's unclear: Whether to include both `export` (POSIX) and `set` (Windows cmd) and `$env:` (PowerShell) variants
   - Recommendation: Print all three variants — Windows 10 is a first-class platform per CLAUDE.md constraints. This is Claude's discretion.

2. **Token env var absence behavior**
   - What we know: Middleware should pass through if no token is configured (auth disabled)
   - What's unclear: Whether to log an INFO or WARNING when server starts with no token configured on HTTP transport
   - Recommendation: Log `WARNING` when transport is SSE/HTTP and `MATLAB_MCP_AUTH_TOKEN` is not set — silent security-disabled state is dangerous.

---

## Environment Availability

Step 2.6: SKIPPED — this phase is purely code/config changes. All required libraries (`starlette`, `hmac`, `secrets`, `os`, `argparse`) are stdlib or already-installed project dependencies. No external tools or services required.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.0+ with pytest-asyncio 0.21+ |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `asyncio_mode = "auto"`) |
| Quick run command | `pytest tests/test_auth_middleware.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-01 | Valid `Authorization: Bearer <token>` passes through | unit | `pytest tests/test_auth_middleware.py::TestBearerAuthMiddleware::test_valid_token_passes -x` | Wave 0 |
| AUTH-01 | Missing auth header returns 401 | unit | `pytest tests/test_auth_middleware.py::TestBearerAuthMiddleware::test_missing_token_rejected -x` | Wave 0 |
| AUTH-02 | Token read from `MATLAB_MCP_AUTH_TOKEN` env var only | unit | `pytest tests/test_auth_middleware.py::TestBearerAuthMiddleware::test_token_from_env_var -x` | Wave 0 |
| AUTH-02 | Startup warning fires when token-like key in config | unit | `pytest tests/test_config.py::TestTokenWarning::test_token_key_in_config_logs_warning -x` | Wave 0 |
| AUTH-03 | 401 response includes `WWW-Authenticate: Bearer` header | unit | `pytest tests/test_auth_middleware.py::TestBearerAuthMiddleware::test_401_has_www_authenticate_header -x` | Wave 0 |
| AUTH-03 | 401 response body is JSON `{"error": "unauthorized", ...}` | unit | `pytest tests/test_auth_middleware.py::TestBearerAuthMiddleware::test_401_body_is_json -x` | Wave 0 |
| AUTH-04 | CORS headers present on HTTP responses | unit | `pytest tests/test_auth_middleware.py::TestCORSIntegration::test_cors_headers_present -x` | Wave 0 |
| AUTH-04 | CORS OPTIONS pre-flight passes without auth | unit | `pytest tests/test_auth_middleware.py::TestBearerAuthMiddleware::test_options_bypass_auth -x` | Wave 0 |
| AUTH-05 | stdio transport does not wire auth middleware | unit | `pytest tests/test_server.py::TestMain::test_main_stdio_no_middleware -x` | Extend existing |
| AUTH-06 | `--generate-token` prints token + env var snippet then exits | unit | `pytest tests/test_server.py::TestMain::test_generate_token_flag -x` | Wave 0 |
| AUTH-06 | Generated token is 64 hex characters | unit | `pytest tests/test_server.py::TestMain::test_generate_token_format -x` | Wave 0 |
| AUTH-01 | `/health` path bypasses auth | unit | `pytest tests/test_auth_middleware.py::TestBearerAuthMiddleware::test_health_bypass -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_auth_middleware.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_auth_middleware.py` — covers AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05 middleware unit tests
- [ ] Extend `tests/test_server.py` — add `test_main_stdio_no_middleware` and `test_generate_token_flag`, `test_generate_token_format`
- [ ] Extend `tests/test_config.py` — add `TestTokenWarning` covering AUTH-02 config warning

---

## Sources

### Primary (HIGH confidence)
- FastMCP 3.2.0 source — `fastmcp/server/server.py` `run_http_async()` signature: `middleware: list[ASGIMiddleware] | None = None` (verified by introspection)
- FastMCP 3.2.0 source — `fastmcp/server/http.py` `create_sse_app()` / `create_streamable_http_app()`: middleware list passed to `create_base_app()` → `StarletteWithLifespan` (verified by source read)
- FastMCP 3.2.0 source — `fastmcp/server/auth/middleware.py`: demonstrates pure ASGI class pattern for `RequireAuthMiddleware` (verified)
- Starlette 0.52.x source — `starlette.middleware.cors.CORSMiddleware` constructor signature (verified by introspection)
- Python stdlib — `hmac.compare_digest` available in Python 3.10+ (verified)
- Python stdlib — `secrets.token_hex(32)` produces 64-char hex (verified by execution)

### Secondary (MEDIUM confidence)
- FastMCP 3.2.0 `http_app()` source: `middleware` kwarg threaded through to `create_sse_app` and `create_streamable_http_app` (verified by source read)

### Tertiary (LOW confidence)
- CORS pre-flight `OPTIONS` bypass requirement: standard CORS spec behavior, not independently verified against Starlette docs but consistent with W3C CORS spec.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified by live introspection of installed packages
- Architecture: HIGH — FastMCP 3.2 middleware integration point verified by reading actual source
- Pitfalls: HIGH — CORS pre-flight/auth interaction is well-known; `hmac.compare_digest` type constraint verified by reading stdlib source
- Test map: HIGH — test file names and patterns match existing codebase conventions

**Research date:** 2026-04-01
**Valid until:** 2026-05-01 (FastMCP minor updates could change `run_http_async` signature; re-verify before upgrading FastMCP)
