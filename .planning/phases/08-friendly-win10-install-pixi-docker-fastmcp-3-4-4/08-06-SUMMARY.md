---
phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4
plan: 06
subsystem: api
tags: [fastmcp, pydantic, structured-output, mcp, schema, tool-result]

# Dependency graph
requires:
  - phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4
    provides: "08-03 TimingMiddleware registration in create_server (integrated cleanly, no conflict)"
provides:
  - "ExecuteResult/CheckResult Pydantic v2 models (schema-additive typed view of execute_code/check_code results)"
  - "execute_code/check_code tool wrappers annotated to drive FastMCP output_schema + structuredContent"
  - "ToolResult(is_error=True) for MATLAB execution errors instead of a plain status='error' dict"
  - "Wire-compat regression test suite proving the serialized key set is unchanged"
affects: [api, mcp-clients, monitoring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "FastMCP F6 structured output: annotate tool wrapper return type with the bare Pydantic model (not a Union with ToolResult) — unioning with ToolResult breaks fastmcp 3.4.4's output-schema generation entirely (PydanticSchemaGenerationError on the internal _UnserializableType placeholder). ToolResult instances still pass through untouched at runtime via Tool.convert_result's isinstance check, regardless of the declared annotation."
    - "Wire-compat via exclude_none: model every optional wire key as Optional[...]=None and dump with model_dump(exclude_none=True) (to_wire_dict()) to reproduce the exact legacy dict shape per code path, without hand-maintaining per-path dict builders."
    - "Nested error dict kept as plain dict (not nested BaseModel) so exclude_none only prunes top-level None fields — preserving legitimate None-valued keys inside error (matlab_id/stack_trace) that the legacy dict always included."

key-files:
  created:
    - tests/test_structured_output.py
  modified:
    - src/matlab_mcp/tools/core.py
    - src/matlab_mcp/server.py

key-decisions:
  - "execute_code_impl/check_code_impl keep returning plain dicts unchanged (per plan) — ExecuteResult/CheckResult are a typed view built only inside the execute_code/check_code tool wrappers in server.py."
  - "Tool wrapper return annotation is the bare model (ExecuteResult / CheckResult), not a Union with ToolResult, because unioning with ToolResult causes fastmcp's function_parsing to attempt schema generation over a Union containing an internal unserializable placeholder type, which raises PydanticSchemaGenerationError and silently drops the entire output_schema to None."
  - "MATLAB execution errors (status == 'failed') return ToolResult(content=<human summary>, structured_content=<wire dict>, is_error=True); HITL 'denied' is NOT treated as a MATLAB execution error and stays a plain dict (matches the plan's 'MATLAB execution errors' scope, distinct from HITL rejection)."
  - "Ran verification against the project's pixi 'dev' environment (.pixi/envs/dev, fastmcp 3.4.4 — matching the pinned pyproject.toml/pixi.toml version) rather than the anaconda base Python (fastmcp 3.2.0, which lacks ToolResult.is_error entirely). Installed pytest-timeout into that env (not declared in pixi.toml's dev feature) purely to run the plan's --timeout=30 verification command; this is a local environment gap, not a repo change."

requirements-completed: [D-04]

coverage:
  - id: D1
    description: "ExecuteResult/CheckResult Pydantic models added to tools/core.py, exactly reproducing every existing execute_code/check_code dict key across all code paths (completed, pending, failed pre-job, failed post-job, HITL denied, check_code issues/raw/passthrough)"
    requirement: D-04
    verification:
      - kind: unit
        ref: "tests/test_structured_output.py::TestExecuteResultWireCompat"
        status: pass
      - kind: unit
        ref: "tests/test_structured_output.py::TestCheckResultWireCompat"
        status: pass
      - kind: unit
        ref: "tests/test_tools.py (existing execute_code_impl/check_code_impl tests, unchanged, still green)"
        status: pass
    human_judgment: false
  - id: D2
    description: "execute_code/check_code tool wrappers annotated to emit a FastMCP output schema + structuredContent while preserving the exact legacy dict wire shape"
    requirement: D-04
    verification:
      - kind: unit
        ref: "tests/test_structured_output.py::TestOutputSchemaEmission::test_execute_code_emits_output_schema"
        status: pass
      - kind: unit
        ref: "tests/test_structured_output.py::TestOutputSchemaEmission::test_check_code_emits_output_schema"
        status: pass
      - kind: unit
        ref: "tests/test_structured_output.py::TestToolResultErrorPath::test_execute_code_success_returns_plain_dict_keys"
        status: pass
    human_judgment: false
  - id: D3
    description: "MATLAB execution errors return ToolResult(is_error=True) with structured_content carrying the wire-compat error dict, instead of only a status='error' style dict"
    requirement: D-04
    verification:
      - kind: unit
        ref: "tests/test_structured_output.py::TestToolResultErrorPath::test_execute_code_error_returns_tool_result_is_error"
        status: pass
      - kind: unit
        ref: "tests/test_structured_output.py::TestToolResultErrorPath::test_check_code_error_returns_tool_result_is_error"
        status: pass
    human_judgment: false

# Metrics
duration: 20min
completed: 2026-07-13
status: complete
---

# Phase 8 Plan 6: Structured Output for execute_code/check_code Summary

**FastMCP F6 adoption — ExecuteResult/CheckResult Pydantic models drive output schemas for execute_code/check_code while an exclude_none-based to_wire_dict() reproduces the exact legacy dict keys, and MATLAB errors now surface as ToolResult(is_error=True).**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-13T00:44:00+02:00 (approx, first file read)
- **Completed:** 2026-07-13T00:49:22+02:00
- **Tasks:** 2
- **Files modified:** 2 (+1 new test file)

## Accomplishments

- Added `ExecuteResult`/`CheckResult` Pydantic v2 models in `src/matlab_mcp/tools/core.py` that capture every key the executor/impl functions have ever returned (`status`, `job_id`, `message`, `text`, `variables`, `figures`, `files`, `warnings`, `errors`, `error`, `issues`, `raw`), all `Optional`, with a `to_wire_dict()` helper (`model_dump(exclude_none=True)`) that reproduces the exact per-path dict shape.
- Discovered during Task 1 read-first that the legacy `completed` dict also carries `files`/`warnings`/`errors` keys beyond the plan's headline list (`status`, `job_id`, `text`, `variables`, `figures`) — modeled all of them so the wire-compat guarantee is genuinely exhaustive, not just for the headline keys.
- Annotated `execute_code`/`check_code` tool wrappers in `server.py` with `-> ExecuteResult` / `-> CheckResult` so FastMCP 3.4.4 derives and advertises an output schema; wrappers still return the exact legacy dict (via `to_wire_dict()`) on non-failed paths.
- MATLAB execution errors (`status == "failed"`) now return `ToolResult(content=<summary>, structured_content=<wire dict>, is_error=True)` so clients get a real MCP error (`isError=True`) instead of only inspecting `status` in a 200-style payload.
- Added `tests/test_structured_output.py` covering: exact key round-trips for every `ExecuteResult`/`CheckResult` code path (including the tricky nested-`error`-dict-with-`None`-values case and the "no `job_id`" pre-job-security-rejection case), output-schema emission for both tools, and the `ToolResult(is_error=True)` error path for both tools.

## Task Commits

Each task was committed atomically:

1. **Task 1: Define ExecuteResult/CheckResult models and a wire-compat test capturing the exact current keys** - `f6f69a5` (feat)
2. **Task 2: Annotate execute_code/check_code wrappers to emit structured output and return ToolResult(is_error=True) on MATLAB errors** - `8e0a191` (feat)

_Note: no TDD test→feat→refactor split was used per-task; both tasks' verification tests were written alongside the implementation in the same commit (Task 1's tests are the wire-compat proof; Task 2 reused/extended the same test file)._

## Files Created/Modified

- `src/matlab_mcp/tools/core.py` - Added `ExecuteResult`/`CheckResult` Pydantic models + `to_wire_dict()` helper; `execute_code_impl`/`check_code_impl` unchanged.
- `src/matlab_mcp/server.py` - Imported `ExecuteResult`/`CheckResult`/`ToolResult`; annotated `execute_code`/`check_code` wrappers, added `ToolResult(is_error=True)` branch on `status == "failed"`.
- `tests/test_structured_output.py` - New wire-compat + output-schema + error-path test suite (21 tests).

## Decisions Made

- Kept `execute_code_impl`/`check_code_impl` returning plain dicts exactly as before (per plan's explicit instruction) — the Pydantic models are a typed view constructed only inside the tool wrappers, so `tests/test_tools.py` needed zero changes.
- Annotated the tool wrappers' return type as the bare model (`ExecuteResult`/`CheckResult`), not `Model | ToolResult`. Verified empirically that annotating with a `Union` containing `ToolResult` causes fastmcp 3.4.4's schema generation to raise `PydanticSchemaGenerationError` on its internal `_UnserializableType` placeholder and silently fall back to `output_schema = None` for the *entire* tool — defeating F6. Confirmed `ToolResult` instances still pass through untouched at runtime via `Tool.convert_result`'s `isinstance(raw_value, ToolResult)` check, independent of the declared annotation, so the bare-model annotation is both correct and necessary.
- Modeled the nested `error` field as a plain `dict` rather than a nested `BaseModel`, so `model_dump(exclude_none=True)` only prunes *top-level* `None` fields on `ExecuteResult`/`CheckResult` and does not recurse into (and strip) the legitimate `None`-valued `matlab_id`/`stack_trace` keys that the legacy `error` dict always carried.
- Scoped the `ToolResult(is_error=True)` path to `status == "failed"` only — HITL `"denied"` responses are a policy rejection, not a MATLAB execution error, and the plan's threat register/acceptance criteria specifically call out "MATLAB execution errors", so `denied` stays a plain dict.
- Verified against the repo's pixi `dev` environment (`.pixi/envs/dev`, fastmcp 3.4.4, matching `pyproject.toml`/`pixi.toml`'s pin) rather than the machine's anaconda base Python (fastmcp 3.2.0, whose `ToolResult` has no `is_error` parameter at all — confirmed by inspecting both installations' `ToolResult.__init__` signatures). This matches the environment the phase is actually targeting.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test-infra gap: pixi `dev` environment lacked `pytest-timeout`**
- **Found during:** Task 1 verification (`python -m pytest ... --timeout=30`)
- **Issue:** `pixi.toml`'s `[feature.dev.pypi-dependencies]` does not declare `pytest-timeout`, so `--timeout=30` (required by this plan's `<verify>` blocks and the phase-level verification command) fails with "unrecognized arguments" in the pixi dev env.
- **Fix:** `pip install pytest-timeout` directly into `.pixi/envs/dev` (environment-only; not a `pixi.toml`/lock change, so nothing was committed for this). This is an out-of-scope environment gap for a future cleanup plan to fix properly (add `pytest-timeout` to `pixi.toml`'s dev feature and regenerate `pixi.lock`), logged here rather than fixed in the repo since it's outside this plan's `files_modified` scope.
- **Files modified:** none (repo-wise); local `.pixi/envs/dev` site-packages only.
- **Verification:** `python -m pytest tests/ -x -q --timeout=30` ran successfully afterward (939 passed, 3 skipped).

---

**Total deviations:** 1 auto-fixed (1 bug/test-infra), 0 architectural
**Impact on plan:** No scope creep — the fix was local-environment-only (not a repo change) and existed purely to run the plan's own mandated verification command with fastmcp 3.4.4 (the anaconda base Python's fastmcp 3.2.0 cannot express `ToolResult(is_error=True)` at all, so it was not a viable alternative for verifying this plan's core requirement).

## Issues Encountered

- The installed "default" Python on this machine (anaconda, used by plain `python`/`pip`) has `fastmcp==3.2.0`, while `pyproject.toml`/`pixi.toml` pin `fastmcp==3.4.4`. `fastmcp` 3.2.0's `ToolResult` has no `is_error` parameter, so this plan's core deliverable (`ToolResult(is_error=True)`) could not even be constructed there. Resolved by running all verification through the repository's own `.pixi/envs/dev` environment (`pixi install -e dev`), which correctly resolves to `fastmcp==3.4.4` per the committed `pixi.lock`. No repo changes were needed to fix this — it's purely about using the right already-configured environment.
- `mcp.list_tools()` returns FastMCP's own `FunctionTool` objects (snake_case `output_schema`), not the wire-level `mcp.types.Tool` (camelCase `outputSchema`) — adjusted test assertions accordingly after the first run surfaced an `AttributeError`.
- Calling a registered `@mcp.tool` function via `Tool.run()`/`tool.run(...)` triggers FastMCP's dependency-injection machinery for the `ctx: Context` parameter, which requires a live request context and fails outside of a real MCP call. Tests instead call the tool's raw `tool.fn(ctx=MagicMock(), code=...)` directly — the same pattern `tests/test_tools.py` already uses for `execute_code_impl`/`check_code_impl` — bypassing the injection layer while still exercising the actual wrapper closure logic (including `state._get_session_id`/`_get_temp_dir`, which pass through unaffected in stdio mode since they don't touch `ctx` when `transport == "stdio"`).

## User Setup Required

None - no external service configuration required. (Note: MCP clients that want to consume the new `structuredContent`/output schema need no action — it is purely additive; existing clients reading only `content`/`status` keep working unchanged.)

## Next Phase Readiness

- F6 (structured output) is complete and additive; no client-visible wire break. Full test suite green (939 passed, 3 skipped) and `ruff check` clean on all changed files.
- Remaining phase 8 FastMCP feature work (F12 transport default, any outstanding cleanup workstreams) is unaffected by this plan and can proceed independently.
- Flagged for a future (out-of-scope-here) chore: add `pytest-timeout` (and ideally `pytest-httpx`, `pytest-xdist` if used elsewhere) to `pixi.toml`'s `[feature.dev.pypi-dependencies]` and regenerate `pixi.lock`, so `pixi run -e dev test -- --timeout=30` works out of the box without an ad hoc `pip install`.

---
*Phase: 08-friendly-win10-install-pixi-docker-fastmcp-3-4-4*
*Completed: 2026-07-13*

## Self-Check: PASSED

- FOUND: `src/matlab_mcp/tools/core.py`
- FOUND: `src/matlab_mcp/server.py`
- FOUND: `tests/test_structured_output.py`
- FOUND commit: `f6f69a5` (Task 1)
- FOUND commit: `8e0a191` (Task 2)
