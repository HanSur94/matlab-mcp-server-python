# Phase 5: Windows 10 + Platform Hardening - Research

**Researched:** 2026-04-01
**Domain:** Windows 10 compatibility, cross-platform Python, GitHub Actions CI
**Confidence:** HIGH

## Summary

Phase 5 is a focused hardening phase with three requirements: change the default bind address from
`0.0.0.0` to `127.0.0.1` (PLAT-02), ensure the server runs without admin rights on Windows 10
(PLAT-01), and add cross-platform CI coverage for Windows 10, macOS, and Linux (PLAT-03).

The codebase is already largely cross-platform due to consistent use of `pathlib.Path`. One
concrete bug exists: `session/manager.py` line 75 hard-codes `/tmp/matlab_mcp` as the fallback
temp path when no config is provided — this path is invalid on Windows. The fix is
`tempfile.gettempdir()`. The bind address change is a one-line edit in `ServerConfig`. The
`test_config.py` assertion `assert cfg.host == "0.0.0.0"` will need updating to match the new
default. The existing `test-windows` GitHub Actions job runs as admin (UAC disabled), so it does
not verify the no-admin constraint at runtime — the CI job design satisfies PLAT-03 (cross-platform
test runs) but the no-admin guarantee comes from using user-space ports and loopback binding, which
are enforced by the code change itself.

**Primary recommendation:** Change `ServerConfig.host` default to `"127.0.0.1"`, fix the
`/tmp/matlab_mcp` hardcoded fallback in `SessionManager.__init__`, update the one broken test
assertion, add macOS to the CI matrix, and document the `0.0.0.0` / firewall-rule requirement.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
None — all implementation choices are at Claude's discretion.

### Claude's Discretion
All implementation choices are at Claude's discretion — pure infrastructure/hardening phase.

Key areas to address:
- Default bind address change from 0.0.0.0 to 127.0.0.1 in ServerConfig
- Cross-platform path handling (os.path vs pathlib)
- Platform-specific test markers or skips
- CI configuration for cross-platform testing (if applicable)
- Documentation of 0.0.0.0 bind requiring admin firewall rule

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PLAT-01 | Server runs on Windows 10 without admin rights (user-space ports, loopback-only default) | Loopback binding avoids Windows Firewall UAC; user-space ports (>1023) need no admin; fix `/tmp/matlab_mcp` hardcoded path |
| PLAT-02 | Default HTTP bind address is `127.0.0.1` (avoids Windows Firewall UAC prompt) | One-line change to `ServerConfig.host`; update one test assertion; document 0.0.0.0 usage |
| PLAT-03 | Cross-platform validation passes on Windows 10, macOS, and Linux | Existing `test-windows` CI job runs on `windows-2022`/`windows-latest`; add `macos-latest` job to matrix |
</phase_requirements>

---

## Standard Stack

### Core (no new dependencies required)

All work in this phase is changes to existing code and CI configuration. No new packages are needed.

| Module | Version | Purpose | Why Standard |
|--------|---------|---------|--------------|
| `pathlib.Path` | stdlib | Cross-platform path construction | Already used consistently across codebase; handles Windows `\` separators transparently |
| `tempfile.gettempdir()` | stdlib | Platform-correct temp directory | Returns `%TEMP%` on Windows, `/tmp` on Unix; no hardcoded paths |
| `platform.system()` | stdlib | Platform detection (already imported in `config.py`) | Already used for macOS max_engines warning |

### No alternatives considered
This phase requires no new libraries. All problems are solved with stdlib.

---

## Architecture Patterns

### Pattern 1: Default Bind Address Change

**What:** Change `ServerConfig.host` default from `"0.0.0.0"` to `"127.0.0.1"`.

**Where:** `src/matlab_mcp/config.py`, line 26 of `ServerConfig`.

**Current:**
```python
host: str = "0.0.0.0"
```

**After:**
```python
host: str = "127.0.0.1"
```

**Cascading test fix required:** `tests/test_config.py`, `TestDefaultValues.test_server_defaults`:
```python
# Before (line 36):
assert cfg.host == "0.0.0.0"

# After:
assert cfg.host == "127.0.0.1"
```

No other test assertions hard-code `"0.0.0.0"` as the expected default — verified by grep.

### Pattern 2: Fix Hardcoded `/tmp` Path in SessionManager

**What:** Replace the hardcoded `/tmp/matlab_mcp` fallback in `SessionManager.__init__` with a
cross-platform temp directory.

**Where:** `src/matlab_mcp/session/manager.py`, line 75.

**Current:**
```python
# When config is None, fallback is Unix-only:
base_temp = "/tmp/matlab_mcp"
```

**After:**
```python
import tempfile
# ...
base_temp = str(Path(tempfile.gettempdir()) / "matlab_mcp")
```

`tempfile.gettempdir()` returns `%TEMP%` on Windows (e.g., `C:\Users\user\AppData\Local\Temp`)
and `/tmp` or `/var/folders/...` on macOS/Linux. `Path` handles separator differences.

### Pattern 3: Cross-Platform CI Matrix

**What:** Extend GitHub Actions CI to run tests on macOS in addition to the existing Linux and
Windows jobs.

**Where:** `.github/workflows/ci.yml`

**Current state:**
- `test` job: `ubuntu-latest` only, Python 3.10 and 3.12
- `test-windows` job: `windows-2022` and `windows-latest`, Python 3.10 and 3.12

**Gap:** No macOS job. PLAT-03 requires validation on Windows 10, macOS, and Linux.

**Add a `test-macos` job:**
```yaml
test-macos:
  needs: lint
  runs-on: macos-latest
  strategy:
    fail-fast: false
    matrix:
      python-version: ["3.10", "3.12"]
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}
    - run: pip install -e ".[dev,monitoring]"
    - run: pytest tests/ -v -k "not matlab" -W ignore::pytest.PytestUnraisableExceptionWarning
```

**Note on macOS pool warning:** `config.py` already emits a `warnings.warn` when
`max_engines > 4` on macOS. Tests use `max_engines=2` (via `sample_config_path` fixture or
`_make_config` helper), so no warning suppression is needed in the test matrix.

### Pattern 4: Document `0.0.0.0` / Firewall Rule Requirement

Per PLAT-02 success criterion 3: "Changing `bind_address: 0.0.0.0` in config is documented as
requiring an admin-created firewall rule."

**Where to add documentation:**
1. A comment in `ServerConfig` above the `host` field in `config.py`.
2. The startup banner in `server.py::main()` — log a warning when `host != "127.0.0.1"` on
   Windows.

**Config comment pattern (matches existing codebase style):**
```python
# On Windows 10 without admin rights, keep the default 127.0.0.1.
# Binding to 0.0.0.0 will trigger a Windows Firewall UAC prompt on first run,
# and requires a manually created inbound firewall rule (admin required).
host: str = "127.0.0.1"
```

**Startup banner warning:**
```python
import platform
if platform.system() == "Windows" and config.server.host not in ("127.0.0.1", "localhost"):
    logger.warning(
        "Server is bound to %s on Windows. Binding to a non-loopback address "
        "requires an admin-created inbound firewall rule and may trigger a "
        "Windows Firewall UAC prompt.",
        config.server.host,
    )
```

### Anti-Patterns to Avoid

- **Hardcoded `/tmp`:** Never use `/tmp/...` as a path literal anywhere in the codebase. Use
  `tempfile.gettempdir()` or `pathlib.Path(config.execution.temp_dir)`.
- **`os.path.join` with Unix separators:** All path construction is already done via `pathlib.Path`
  — keep it that way. Do not introduce `os.path.join("/tmp", ...)` style.
- **Platform-skip markers on existing tests:** Do not add `@pytest.mark.skipif(sys.platform !=
  "win32", ...)` to existing tests — they should all pass on all platforms without skips.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Platform temp directory | `"/tmp/matlab_mcp"` literal | `tempfile.gettempdir()` | Returns correct OS temp dir; no custom logic needed |
| Path separator normalization | Manual `str.replace("\\", "/")` | `pathlib.Path` (already in use) | `Path` handles separators across platforms |
| Admin rights detection | Custom UAC check code | N/A — avoid the need entirely | Loopback + user-space ports simply don't require admin on Windows |

**Key insight:** The Windows no-admin constraint is satisfied architecturally (loopback binding +
port > 1023), not by runtime privilege checks.

---

## Common Pitfalls

### Pitfall 1: GitHub Actions Windows Runners Are Admin
**What goes wrong:** The `test-windows` CI job runs on a GitHub-hosted Windows VM where UAC is
disabled and the job runs as administrator. Tests that bind sockets on `0.0.0.0` will succeed in CI
even though they would fail (or prompt a UAC dialog) for a real non-admin Windows 10 user.

**Why it happens:** GitHub Actions Windows VMs are configured with full admin rights for
convenience.

**How to avoid:** The no-admin guarantee comes from the code change (default to loopback), not from
a CI test that validates admin rights. This is acceptable — PLAT-01/PLAT-02 are satisfied by the
config default, not by a CI non-admin environment.

**Warning signs:** If someone adds a test that asserts "server starts on `0.0.0.0` without
triggering UAC" — that test would always pass in CI regardless of the code, making it useless.

### Pitfall 2: `/tmp` Fallback Only Triggered When `config=None`
**What goes wrong:** The hardcoded `/tmp/matlab_mcp` path is only reached in
`SessionManager.__init__` when `config is None` (line 73). In production, `config` is always
provided. But in tests that construct `SessionManager()` without arguments, this fallback fires and
will fail on Windows.

**Why it happens:** The fallback was written for Unix and not updated when Windows support was
targeted.

**How to avoid:** Fix the fallback to use `tempfile.gettempdir()`. All existing tests that pass
`config=None` to `SessionManager` will then work on Windows without other changes.

### Pitfall 3: macOS `max_engines > 4` Warning in Tests
**What goes wrong:** `AppConfig()` with default pool settings (`max_engines=10`) triggers a
`UserWarning` on macOS because of the validator in `config.py`. This can cause `pytest -W
error::UserWarning` runs to fail.

**Why it happens:** The macOS warning fires in `AppConfig.validate_pool()`.

**How to avoid:** Tests that construct `AppConfig()` directly without specifying pool settings
should use `pool=PoolConfig(min_engines=1, max_engines=2)`. Inspect existing test fixtures — the
`sample_config_path` fixture already uses `max_engines: 2`, and `_make_config` in `test_server.py`
uses `max_engines=2`. Direct `AppConfig()` in `test_config.py::TestDefaultValues.test_app_config_defaults`
does not set pool — this will emit a warning on macOS but not fail the test (no `-W error` flag in
`pyproject.toml`). Accept this as acceptable behavior.

### Pitfall 4: `_apply_env_overrides` Key Parsing for `MATLAB_MCP_SERVER_HOST`
**What goes wrong:** A developer might worry that `MATLAB_MCP_SERVER_HOST` parses incorrectly
because `host` is a short key.

**Why it's actually fine:** `remainder.lower().split("_", 1)` with maxsplit=1 on `"SERVER_HOST"`
produces `["server", "host"]` — correct two-part split. Verified by code inspection and manual
test.

---

## Code Examples

### Change 1: `config.py` — Default host

```python
# Source: src/matlab_mcp/config.py, ServerConfig
class ServerConfig(BaseModel):
    """General server settings (name, transport, host/port, logging, drain)."""

    name: str = "matlab-mcp-server"
    transport: Literal["stdio", "sse", "streamablehttp"] = "stdio"
    # On Windows 10 without admin rights, keep the default 127.0.0.1.
    # Binding to 0.0.0.0 will trigger a Windows Firewall UAC prompt on first
    # run and requires a manually created inbound firewall rule (admin required).
    host: str = "127.0.0.1"
    port: int = 8765
    # ... rest unchanged
```

### Change 2: `session/manager.py` — Fix hardcoded `/tmp`

```python
# Source: src/matlab_mcp/session/manager.py, SessionManager.__init__
import tempfile
# ...
if config is not None:
    self._max_sessions: int = config.sessions.max_sessions
    self._session_timeout: int = config.sessions.session_timeout
    base_temp: str = config.execution.temp_dir
else:
    self._max_sessions = 50
    self._session_timeout = 3600
    base_temp = str(Path(tempfile.gettempdir()) / "matlab_mcp")
```

### Change 3: `server.py` — Windows non-loopback warning

```python
# Source: src/matlab_mcp/server.py, main() startup banner section
import platform
# Add after existing transport logging:
if platform.system() == "Windows" and config.server.host not in ("127.0.0.1", "localhost"):
    logger.warning(
        "Server is bound to %s on Windows. Binding to a non-loopback address "
        "requires an admin-created inbound firewall rule and may trigger a "
        "Windows Firewall UAC prompt.",
        config.server.host,
    )
```

### Change 4: `ci.yml` — Add macOS job

```yaml
# Source: .github/workflows/ci.yml
test-macos:
  needs: lint
  runs-on: macos-latest
  strategy:
    fail-fast: false
    matrix:
      python-version: ["3.10", "3.12"]
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: ${{ matrix.python-version }}
    - run: pip install -e ".[dev,monitoring]"
    - run: pytest tests/ -v -k "not matlab" -W ignore::pytest.PytestUnraisableExceptionWarning
```

### Change 5: `test_config.py` — Update default host assertion

```python
# Source: tests/test_config.py, TestDefaultValues.test_server_defaults
def test_server_defaults(self):
    cfg = ServerConfig()
    assert cfg.name == "matlab-mcp-server"
    assert cfg.transport == "stdio"
    assert cfg.host == "127.0.0.1"   # was "0.0.0.0"
    assert cfg.port == 8765
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `host: str = "0.0.0.0"` | `host: str = "127.0.0.1"` | Phase 5 | Avoids Windows Firewall UAC on first run |
| `/tmp/matlab_mcp` literal | `tempfile.gettempdir() / "matlab_mcp"` | Phase 5 | Correct temp dir on all platforms |
| Linux-only CI | Linux + Windows + macOS CI | Phase 5 | PLAT-03 satisfied |

---

## Open Questions

1. **macOS `max_engines` warning in CI test run**
   - What we know: `AppConfig()` default emits `UserWarning` on macOS when `max_engines > 4`.
     Tests in `test_config.py::TestDefaultValues.test_app_config_defaults` call `AppConfig()` with
     no pool override.
   - What's unclear: Whether the macOS CI run should suppress or capture this warning.
   - Recommendation: Add `-W ignore::UserWarning:matlab_mcp.config` to the macOS pytest command, or
     accept the warning (it does not fail tests). The simpler choice is acceptance.

2. **Windows `test-windows` job uses `install.bat` — macOS job should not**
   - What we know: The `test-windows` CI job calls `install.bat` and activates a `.venv`. The macOS
     job should use direct `pip install -e ".[dev,monitoring]"` instead (no `.bat` equivalent).
   - What's unclear: None — this is straightforward.
   - Recommendation: macOS job uses `pip install` directly, matching the Linux `test` job pattern.

---

## Environment Availability

This phase is purely code/config changes (one-line config default, one path fix, CI YAML edits,
one test assertion fix). No external tools beyond the existing dev stack are required.

Step 2.6: SKIPPED (no new external dependencies identified — all changes use stdlib `tempfile`
and existing CI infrastructure).

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7.0+ with pytest-asyncio |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/test_config.py tests/test_session.py -x` |
| Full suite command | `pytest tests/ -v -k "not matlab"` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PLAT-01 | `SessionManager(config=None)` uses platform-correct temp dir | unit | `pytest tests/test_session.py -x -k "test_default_temp_dir_is_cross_platform"` | Wave 0 |
| PLAT-02 | `ServerConfig()` default host is `127.0.0.1` | unit | `pytest tests/test_config.py::TestDefaultValues::test_server_defaults -x` | Exists (needs assertion update) |
| PLAT-02 | `main()` logs a warning when host is not loopback on Windows | unit | `pytest tests/test_server.py -x -k "test_main_warns_non_loopback_on_windows"` | Wave 0 |
| PLAT-02 | `MATLAB_MCP_SERVER_HOST` env var override still works | unit | `pytest tests/test_config.py -x -k "test_server_host_env_override"` | Wave 0 |
| PLAT-03 | Full test suite passes on macOS in CI | CI | `.github/workflows/ci.yml test-macos job` | Wave 0 (CI YAML edit) |

### Sampling Rate

- **Per task commit:** `pytest tests/test_config.py tests/test_session.py -x`
- **Per wave merge:** `pytest tests/ -v -k "not matlab"`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_session.py` — add `test_default_temp_dir_is_cross_platform` to verify
  `SessionManager(config=None)` uses `tempfile.gettempdir()`, not `/tmp`
- [ ] `tests/test_config.py` — add `test_server_host_env_override` for
  `MATLAB_MCP_SERVER_HOST=0.0.0.0` env override
- [ ] `tests/test_server.py` — add `test_main_warns_non_loopback_on_windows` (mock
  `platform.system` to return `"Windows"`, assert warning logged when host is `0.0.0.0`)
- [ ] `.github/workflows/ci.yml` — add `test-macos` job

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 5 |
|-----------|-------------------|
| Python 3.10+ | stdlib `tempfile` and `pathlib` are available on all supported versions |
| No breaking changes to `config.yaml` format | `host` key in `config.yaml` still works — only the default value changes |
| Keep backward compat with existing config.yaml | Users with explicit `host: 0.0.0.0` in their YAML are unaffected |
| Windows 10 without admin rights as hard constraint | Exactly what PLAT-01/PLAT-02 address |
| `from __future__ import annotations` at top of all modules | Must be present in any modified/new module |
| Logger per module: `logger = logging.getLogger(__name__)` | Already present in all modules being changed |
| Line length 100 characters (ruff) | Warning message strings must respect 100-char limit |
| Type hints on all function parameters and return values | New test functions must be fully typed |
| `async def test_*` for tests calling async code | New tests for sync functions use `def test_*` |

---

## Sources

### Primary (HIGH confidence)

- Direct code inspection: `src/matlab_mcp/config.py` — `ServerConfig.host` default, env override
  parser, macOS pool warning
- Direct code inspection: `src/matlab_mcp/session/manager.py` — line 75 hardcoded `/tmp/matlab_mcp`
- Direct code inspection: `.github/workflows/ci.yml` — existing jobs, Windows/Linux matrix,
  missing macOS
- Direct code inspection: `tests/test_config.py` — `assert cfg.host == "0.0.0.0"` on line 36
- Python stdlib docs: `tempfile.gettempdir()` — returns OS-appropriate temp directory

### Secondary (MEDIUM confidence)

- WebSearch (GitHub Actions docs): GitHub-hosted Windows runners run as admin with UAC disabled.
  Source: [GitHub-hosted runners reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- WebSearch: Windows Firewall behavior — loopback traffic (127.0.0.1) does not trigger the
  "Windows Security Alert" dialog; binding to non-loopback addresses with no existing rule may
  trigger a dialog on first run.

### Tertiary (LOW confidence)

- None.

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — no new dependencies; all stdlib
- Architecture: HIGH — all changes identified by direct code inspection; patterns are minimal
- Pitfalls: HIGH — GitHub Actions admin-by-default is documented; `/tmp` bug is confirmed by source

**Research date:** 2026-04-01
**Valid until:** 2026-06-01 (stable stdlib APIs and CI patterns; FastMCP not touched in this phase)
