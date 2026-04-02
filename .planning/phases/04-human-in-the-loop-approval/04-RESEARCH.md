# Phase 4: Human-in-the-Loop Approval - Research

**Researched:** 2026-04-01
**Domain:** FastMCP elicitation API, async gate patterns, Python config extension
**Confidence:** HIGH

## Summary

Phase 4 adds configurable approval gates that pause dangerous MATLAB operations until
a human confirms them, using the FastMCP 3.x `ctx.elicit()` API. The feature is
disabled by default; operators opt-in per deployment via a new `hitl` section in
`config.yaml`.

Three gate points exist: (1) execute_code against a `protected_functions` list,
(2) execute_code globally when `all_execute` is enabled, and (3) file write/delete
operations when `protect_file_ops` is enabled. Read-only tools (`get_workspace`,
`list_toolboxes`, `get_help`, etc.) are never gated. All approvals/denials are
audit-logged at INFO level.

The elicitation API is confirmed working in FastMCP 3.2.0 (already installed).
`ctx.elicit(message, HumanApproval)` returns one of `AcceptedElicitation`,
`DeclinedElicitation`, or `CancelledElicitation`. Both declined and cancelled
responses must block execution and return the denied status dict.

**Primary recommendation:** Add a `HITLConfig` Pydantic model to `config.py`, wire
it into `AppConfig`, insert async gate helpers into `execute_code_impl` and the two
file tool impl functions, and pass `ctx` through from the server layer to those
helpers.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Elicitation API Usage**
- Use `ctx.elicit(HumanApproval)` where `HumanApproval` is a Pydantic model with `approved: bool` field
- On denial: return error dict `{"status": "denied", "message": "Operation blocked by HITL approval"}` — do not execute
- No server-side timeout — wait indefinitely (agent/client decides timeout)
- Approval message: show function name, code snippet (first 200 chars), and reason for gate

**Config Structure**
- New `hitl` section in config.yaml: `enabled: false`, `protected_functions: [...]`, `protect_file_ops: false`
- Default protected functions list: empty (all disabled by default — operators opt-in)
- Config model: `HITLConfig` in config.py as Pydantic BaseModel
- Env var override: `MATLAB_MCP_HITL_ENABLED=true` — standard prefix pattern

**Implementation Scope**
- Intercept inside `execute_code_impl()` and file tool impl functions — check before execution
- Per-call approval — each dangerous call prompts independently
- Audit logging: log all approvals/denials at INFO level with function name and session
- File operations that trigger: `upload_data`, `delete_file` — write operations only (not read_script/read_data/list_files)

### Claude's Discretion
- Internal module organization for HITL logic
- Exact Pydantic model field structure for elicitation
- Test mocking approach for elicitation API

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HITL-01 | Configurable list of always-protected functions that require human approval before execution | `HITLConfig.protected_functions`; gate in `execute_code_impl` after security check |
| HITL-02 | Optional HITL toggle for all `execute_code` calls (off by default, configurable per deployment) | `HITLConfig.enabled` master switch; apply before code execution |
| HITL-03 | File operations (upload, delete, write) can require human approval (configurable toggle) | `HITLConfig.protect_file_ops`; gate in `upload_data_impl` and `delete_file_impl` |
| HITL-04 | Safe read-only tools run without approval | No gate in `get_workspace_impl`, `list_toolboxes_impl`, `get_help_impl`, `list_files_impl`, `read_*` impls |
| HITL-05 | HITL uses FastMCP 3.0 elicitation API | `ctx.elicit(message, HumanApproval)` — verified in FastMCP 3.2.0 |
| HITL-06 | HITL configuration in config.yaml with sensible defaults | `HITLConfig` model + commented block in `config.yaml` |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastMCP | 3.2.0 | Provides `ctx.elicit()` API | Already installed; elicitation confirmed available |
| Pydantic | 2.12.5 | `HITLConfig` model and `HumanApproval` elicitation schema | Project-wide config/validation standard |
| Python stdlib `re` | built-in | Protected-function detection in code | Matches existing `SecurityValidator` pattern |

### No New Dependencies Required

All required functionality is available in the existing installed packages. No `pip install` step is needed for this phase.

**Version verification:** Confirmed FastMCP 3.2.0 installed and `ctx.elicit()` available at
`fastmcp.server.context.Context.elicit`. Elicitation result types confirmed:
`AcceptedElicitation`, `DeclinedElicitation`, `CancelledElicitation`.

---

## Architecture Patterns

### Recommended Project Structure

No new top-level modules are required. HITL logic fits within the existing layer:

```
src/matlab_mcp/
├── config.py                  # Add HITLConfig, wire into AppConfig
├── hitl/
│   ├── __init__.py            # empty
│   └── gate.py                # HITLGate helper — centralised elicitation logic
├── tools/
│   ├── core.py                # Add ctx + hitl_gate param to execute_code_impl
│   └── files.py               # Add ctx + hitl_gate param to upload_data_impl, delete_file_impl
└── server.py                  # Pass ctx and state.hitl_gate to impl functions
```

Alternatively the gate logic can live inline in `tools/core.py` and `tools/files.py`
without a separate `hitl/` package. Either works; a dedicated `hitl/gate.py` is cleaner
because it can be unit-tested independently. Claude may decide.

### Pattern 1: HITLConfig Pydantic Model

**What:** New section in `config.py`, mirrors `SecurityConfig` pattern.
**When to use:** All config additions follow this pattern.

```python
# Source: src/matlab_mcp/config.py — existing pattern
class HITLConfig(BaseModel):
    """Human-in-the-loop approval gate configuration."""

    enabled: bool = False
    protected_functions: List[str] = Field(default_factory=list)
    protect_file_ops: bool = False
```

Wire into `AppConfig`:
```python
class AppConfig(BaseModel):
    ...
    hitl: HITLConfig = Field(default_factory=HITLConfig)
```

### Pattern 2: HumanApproval Elicitation Schema

**What:** Minimal Pydantic model passed to `ctx.elicit()` as the `response_type`.
**When to use:** FastMCP elicitation protocol requires an object schema (no bare primitives).

```python
from pydantic import BaseModel

class HumanApproval(BaseModel):
    """User approval response for HITL gate."""
    approved: bool
```

Verified: FastMCP 3.2.0 accepts a `BaseModel` subclass as `response_type`. The client
receives a schema with a single boolean field; `AcceptedElicitation.data` will be typed
as `HumanApproval`.

### Pattern 3: Elicitation Gate Call

**What:** The canonical gate call pattern — call elicit, inspect result type, return denied
dict or allow execution to continue.
**When to use:** Every HITL check point.

```python
# Source: FastMCP 3.2.0 — verified via help(Context.elicit)
from fastmcp.server.context import AcceptedElicitation, Context
from pydantic import BaseModel

class HumanApproval(BaseModel):
    approved: bool

async def _request_approval(ctx: Context, message: str) -> bool:
    """Return True if approved, False if denied/cancelled."""
    result = await ctx.elicit(message, HumanApproval)
    if isinstance(result, AcceptedElicitation):
        return result.data.approved
    # DeclinedElicitation or CancelledElicitation — treat both as denial
    return False
```

Callers that get `False` return immediately:
```python
DENIED = {"status": "denied", "message": "Operation blocked by HITL approval"}
```

### Pattern 4: Protected Function Detection

**What:** Scan code for any function from the protected list before executing.
**When to use:** Inside `execute_code_impl` after the existing security check.

```python
import re

def _detect_protected_function(code: str, protected: list[str]) -> str | None:
    """Return first protected function name found in code, or None."""
    for func in protected:
        if func and re.search(rf"\b{re.escape(func)}\s*\(", code):
            return func
    return None
```

This is intentionally simpler than `SecurityValidator._strip_string_literals` because
the security blocklist hard-blocks; the HITL list only pauses for approval. False
positives (function name in a string) result in an extra confirmation prompt — an
acceptable UX trade-off.

### Pattern 5: Signature Extension for execute_code_impl

The existing `execute_code_impl` signature must be extended to receive the context and
HITL config. Two options:

**Option A — Pass ctx + hitl_config directly:**
```python
async def execute_code_impl(
    code: str,
    session_id: str,
    executor: Any,
    security: Any,
    temp_dir: Optional[str] = None,
    ctx: Optional[Any] = None,          # added
    hitl_config: Optional[Any] = None,  # added
) -> dict:
```

**Option B — Pass a pre-built `HITLGate` helper:**
```python
async def execute_code_impl(
    ...,
    hitl_gate: Optional[Any] = None,  # HITLGate instance or None
) -> dict:
```

Both options keep the function testable without a real ctx. Claude decides which.
Existing tests pass `None` for optional kwargs and will continue to work.

### Pattern 6: Audit Logging

```python
# Approval
logger.info(
    "HITL approved: function=%s session=%s",
    func_name, session_id,
)

# Denial
logger.info(
    "HITL denied: function=%s session=%s action=%s",
    func_name, session_id, result.action,  # 'decline' or 'cancel'
)
```

### Anti-Patterns to Avoid

- **Never await elicit outside an async tool context:** `ctx.elicit()` is only valid
  during an active MCP tool request. Do not store ctx or call elicit in background tasks.
- **Do not raise exceptions on denial:** Return the `{"status": "denied", ...}` dict
  consistently with the rest of the codebase (which returns error dicts, not raises).
- **Do not gate read-only tools:** `get_workspace`, `list_toolboxes`, `get_help`,
  `list_files`, `read_script`, `read_data`, `read_image` must never prompt — verify this
  explicitly in tests.
- **Do not skip the gate when `hitl.enabled=False`:** The gate must short-circuit to
  allow immediately when HITL is disabled — this is the default and must be the zero-cost
  path.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Human approval prompt | Custom HTTP endpoint or stdin read | `ctx.elicit()` | FastMCP protocol-native; works across stdio and HTTP transports |
| Config parsing for HITL | Custom YAML section handler | Pydantic `HITLConfig` BaseModel + existing `_apply_env_overrides` | Env var override support is free with the existing 2-part split convention |
| Code scanning for protected funcs | Full MATLAB parser | Simple `re.search(r"\b{func}\s*\(")` | Good enough for the confirmation gate; false positives are harmless (extra prompt) |

**Key insight:** The elicitation protocol is the entire reason FastMCP 3.x was adopted.
Never implement a custom approval channel — it would defeat session routing and transport
abstraction.

---

## Common Pitfalls

### Pitfall 1: `ctx.elicit` is Not Available in All Transports

**What goes wrong:** If the MCP client does not support elicitation, `ctx.elicit()` raises
or returns a `CancelledElicitation`. This is not a bug — the code must handle it as a
denial.
**Why it happens:** Elicitation is an optional MCP protocol feature. stdio clients like
Claude Code support it; some older clients may not.
**How to avoid:** Always treat `CancelledElicitation` as a denial. Document in config
comments that HITL requires an elicitation-capable client.
**Warning signs:** `CancelledElicitation` action value is `"cancel"`.

### Pitfall 2: Signature Change Breaks Existing Tests

**What goes wrong:** Adding `ctx` to `execute_code_impl` breaks all existing callers that
pass positional args.
**Why it happens:** Python positional argument ordering is strict.
**How to avoid:** Use keyword-only optional parameters with default `None`. All new
parameters appended at the end of the signature (after `temp_dir`). Existing calls
continue to work unchanged.

### Pitfall 3: `_apply_env_overrides` Only Handles 2-Part Keys

**What goes wrong:** `MATLAB_MCP_HITL_ENABLED` parses correctly because the split is
`maxsplit=1`, giving `("hitl", "enabled")`. Verified by code inspection.
**Why it happens:** `remainder.lower().split("_", 1)` — the `1` means only the first
underscore is the section/key boundary.
**How to avoid:** Name the config model fields to match the env var suffix exactly. For
example, `protect_file_ops` maps to `MATLAB_MCP_HITL_PROTECT_FILE_OPS` correctly.

### Pitfall 4: Protected Functions List vs Security Blocklist Confusion

**What goes wrong:** Adding a function to `hitl.protected_functions` when it should be in
`security.blocked_functions` (or vice versa). Security blocklist = hard reject without
prompt; HITL list = pause and ask.
**Why it happens:** Both are function lists in config.
**How to avoid:** Code comments and config.yaml comments must distinguish the two lists
clearly. The HITL check runs **after** the security check in `execute_code_impl` — so a
function in both lists is hard-blocked by security before HITL can prompt.

### Pitfall 5: HITL Gate With `protect_file_ops` Applied Before Validation

**What goes wrong:** If the HITL gate fires before filename sanitization, the approval
message may show an unsanitized filename.
**Why it happens:** Wrong insertion order in the function body.
**How to avoid:** Insert the HITL gate **after** `security.sanitize_filename()` succeeds.
This way the approval message always shows the safe filename, and if sanitization fails,
the error is returned before the prompt appears.

---

## Code Examples

Verified patterns from official sources:

### ctx.elicit Signature (FastMCP 3.2.0)

```python
# Source: help(fastmcp.server.context.Context.elicit) — verified locally
async def elicit(
    self,
    message: str,
    response_type: type[T] | list[str] | dict | None = None,
) -> AcceptedElicitation[T] | DeclinedElicitation | CancelledElicitation:
    ...
```

### Full Gate Pattern — execute_code

```python
# Insert after security.check_code(), before executor.execute()
if hitl_config is not None and hitl_config.enabled and ctx is not None:
    matched_func = _detect_protected_function(code, hitl_config.protected_functions)
    if matched_func is not None:
        snippet = code[:200]
        message = (
            f"MATLAB code calls protected function '{matched_func}'.\n"
            f"Code snippet: {snippet!r}\n"
            f"Approve to execute?"
        )
        result = await ctx.elicit(message, HumanApproval)
        approved = isinstance(result, AcceptedElicitation) and result.data.approved
        logger.info(
            "HITL %s: function=%s session=%s",
            "approved" if approved else "denied",
            matched_func, session_id,
        )
        if not approved:
            return {"status": "denied", "message": "Operation blocked by HITL approval"}
```

### Full Gate Pattern — upload_data

```python
# Insert after sanitize_filename succeeds, before writing to disk
if hitl_config is not None and hitl_config.protect_file_ops and ctx is not None:
    message = f"Agent wants to upload file '{safe_name}'. Approve?"
    result = await ctx.elicit(message, HumanApproval)
    approved = isinstance(result, AcceptedElicitation) and result.data.approved
    logger.info("HITL upload %s: file=%s", "approved" if approved else "denied", safe_name)
    if not approved:
        return {"status": "denied", "message": "Operation blocked by HITL approval"}
```

### HITLConfig in config.yaml (commented block to add)

```yaml
# hitl:
#   enabled: false                  # Master switch — set true to enable any HITL gate
#   protected_functions: []         # MATLAB functions that require approval before execution
#     # Example: ["delete", "rmdir", "fclose", "ftp"]
#   protect_file_ops: false         # Require approval for file upload and delete
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No HITL in MCP servers | `ctx.elicit()` in FastMCP 3.x | FastMCP 3.0 | Protocol-native; works with any compliant client |
| Synchronous approval via stdin | Async `await ctx.elicit()` | MCP spec elicitation draft | Non-blocking; other sessions continue |

---

## Open Questions

1. **HITL-02: "Optional HITL toggle for all execute_code calls"**
   - What we know: `HITLConfig.enabled` is the master switch; `protected_functions` is
     the per-function list. But HITL-02 says "all execute_code calls" — does this mean a
     separate `all_execute: bool` field, or does setting `enabled: true` with an empty
     `protected_functions` imply all-execute gating?
   - What's unclear: CONTEXT.md says `enabled: false` is the master switch and
     `protected_functions: [...]` is the per-function list — no explicit `all_execute`
     field is mentioned.
   - Recommendation: Interpret HITL-02 as satisfied by `enabled: true` + a non-empty
     `protected_functions`. If the planner wants a stricter "gate every execute_code call
     regardless of code content" toggle, add `all_execute: bool = False` to `HITLConfig`.

2. **ctx availability in _impl functions during tests**
   - What we know: Existing `_impl` functions are called with `None` for optional args;
     tests pass.
   - What's unclear: Some test setups may construct `ctx` via `MagicMock()` and pass it
     in; others may omit it entirely.
   - Recommendation: Gate all HITL logic behind `if ctx is not None and hitl_config is
     not None` — zero cost when disabled, fully testable with mock ctx.

---

## Environment Availability

Step 2.6: SKIPPED — no external dependencies beyond the existing Python/FastMCP stack.
All required libraries (FastMCP 3.2.0, Pydantic 2.x, stdlib re) are confirmed installed.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.0+ with pytest-asyncio |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `pytest tests/test_config.py tests/test_tools.py tests/test_tools_files.py -x -q` |
| Full suite command | `pytest tests/ -q --tb=short` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HITL-01 | Protected function in code triggers approval prompt | unit | `pytest tests/test_hitl.py::TestProtectedFunctions -x` | Wave 0 |
| HITL-02 | `enabled: false` (default) — no prompts appear | unit | `pytest tests/test_hitl.py::TestDisabledDefault -x` | Wave 0 |
| HITL-03 | File upload/delete paused when `protect_file_ops: true` | unit | `pytest tests/test_hitl.py::TestFileOpsGate -x` | Wave 0 |
| HITL-04 | Read-only tools never prompt | unit | `pytest tests/test_hitl.py::TestReadOnlyBypass -x` | Wave 0 |
| HITL-05 | `ctx.elicit(message, HumanApproval)` called with correct args | unit | `pytest tests/test_hitl.py::TestElicitCall -x` | Wave 0 |
| HITL-06 | `HITLConfig` loads from config.yaml; env var override works | unit | `pytest tests/test_config.py -k hitl -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_hitl.py tests/test_config.py -x -q`
- **Per wave merge:** `pytest tests/ -q --tb=short`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_hitl.py` — covers HITL-01 through HITL-05; all test classes listed above
- [ ] Tests for `HITLConfig` in `tests/test_config.py` — add test class `TestHITLConfig` (HITL-06)

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 4 |
|-----------|-------------------|
| Python 3.10+ | Use `Optional[T]` or `T \| None` syntax; avoid 3.11+ only features |
| `from __future__ import annotations` at top of every module | Required for all new files |
| FastMCP `>=2.0.0,<3.0.0` in pyproject.toml, but `==3.2.0` in lock file | Lock file wins at runtime; elicitation is a 3.x feature confirmed present |
| `logger = logging.getLogger(__name__)` per module | Required in any new `hitl/gate.py` |
| Docstrings required for all public classes/functions (NumPy style) | `HITLConfig`, `HumanApproval`, `HITLGate` if extracted |
| `snake_case` for functions, `PascalCase` for classes | `HumanApproval`, `HITLConfig`, `HITLGate` |
| Implementation functions end with `_impl` | Gate helper is not a tool impl — no `_impl` suffix needed |
| Line length 100 chars (ruff) | Keep approval message strings within limit |
| No GSD workflow bypass — use `/gsd:execute-phase` | Not applicable to research output |
| `asyncio_mode = "auto"` in pytest | All `async def test_*` methods work without explicit marks |

---

## Sources

### Primary (HIGH confidence)
- `fastmcp.server.context.Context.elicit` — verified via `help()` locally; confirmed
  `AcceptedElicitation`, `DeclinedElicitation`, `CancelledElicitation` import paths
- `fastmcp==3.2.0` in `requirements-lock.txt` — confirmed installed version
- `src/matlab_mcp/config.py` — direct read; all Pydantic patterns confirmed
- `src/matlab_mcp/tools/core.py` — direct read; `execute_code_impl` signature confirmed
- `src/matlab_mcp/tools/files.py` — direct read; `upload_data_impl`, `delete_file_impl` confirmed
- `src/matlab_mcp/security/validator.py` — direct read; regex patterns confirmed
- `.planning/phases/04-human-in-the-loop-approval/04-CONTEXT.md` — user decisions locked

### Secondary (MEDIUM confidence)
- `_apply_env_overrides` in `config.py` — code inspection verified 2-part split handles
  `MATLAB_MCP_HITL_*` env vars correctly

### Tertiary (LOW confidence)
- None — all claims verified against installed code.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — FastMCP 3.2.0 elicitation API verified locally
- Architecture: HIGH — Pydantic config and impl function patterns confirmed from source
- Pitfalls: HIGH — derived from direct code inspection of existing patterns
- Test architecture: HIGH — pytest-asyncio `asyncio_mode = "auto"` confirmed in pyproject.toml

**Research date:** 2026-04-01
**Valid until:** 2026-05-01 (FastMCP 3.x API is stable; Pydantic 2.x config patterns stable)
