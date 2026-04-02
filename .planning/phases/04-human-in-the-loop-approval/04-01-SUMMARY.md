---
phase: 04-human-in-the-loop-approval
plan: "01"
subsystem: hitl
tags: [hitl, config, gate, elicitation, pydantic]
dependency_graph:
  requires: []
  provides: [HITLConfig, hitl/gate.py, HumanApproval, request_execute_approval, request_file_approval]
  affects: [src/matlab_mcp/config.py, src/matlab_mcp/hitl/gate.py]
tech_stack:
  added: [src/matlab_mcp/hitl/gate.py, src/matlab_mcp/hitl/__init__.py]
  patterns: [FastMCP elicitation protocol, Pydantic BaseModel, async gate helpers]
key_files:
  created:
    - src/matlab_mcp/hitl/__init__.py
    - src/matlab_mcp/hitl/gate.py
    - tests/test_hitl.py
  modified:
    - src/matlab_mcp/config.py
    - config.yaml
    - tests/test_config.py
decisions:
  - HITLConfig defaults to all-disabled (enabled=False) so HITL is zero-cost unless explicitly turned on
  - Gate functions return None (proceed) or DENIED dict (block) to allow simple if-check integration in tool handlers
  - _detect_protected_function uses word-boundary regex to prevent substring false positives (e.g., "my_deleter" does not match "delete")
  - all_execute gate checked before protected_functions gate to avoid double-elicit calls
metrics:
  duration_minutes: 12
  completed_date: "2026-04-01"
  tasks_completed: 2
  files_changed: 5
---

# Phase 04 Plan 01: HITLConfig and Gate Module Summary

**One-liner:** HITLConfig Pydantic model wired into AppConfig with gate.py providing HumanApproval elicitation helpers for execute_code and file operations, all disabled by default.

## What Was Built

### HITLConfig (src/matlab_mcp/config.py)

New Pydantic model with four fields:
- `enabled: bool = False` — master switch, zero-cost default path
- `protected_functions: List[str] = []` — MATLAB functions requiring approval
- `protect_file_ops: bool = False` — gate for file upload/delete
- `all_execute: bool = False` — gate for every execute_code call (HITL-02)

Wired into `AppConfig` as `hitl: HITLConfig = Field(default_factory=HITLConfig)`.

### hitl/gate.py (src/matlab_mcp/hitl/gate.py)

Self-contained gate module with:
- `HumanApproval(BaseModel)` — Pydantic model with `approved: bool` field used as elicitation response schema
- `DENIED` — canonical denial dict `{"status": "denied", "message": "..."}`
- `_request_approval(ctx, message)` — calls `ctx.elicit(message, HumanApproval)`, returns True only for `AcceptedElicitation` with `approved=True`
- `_detect_protected_function(code, protected)` — regex word-boundary scan returning first match or None
- `request_execute_approval(code, session_id, ctx, hitl_config)` — checks all_execute then protected_functions gates
- `request_file_approval(operation, filename, session_id, ctx, hitl_config)` — checks protect_file_ops gate

All functions short-circuit immediately when `hitl_config.enabled is False`.

### config.yaml

Appended commented HITL configuration block for operator reference (HITL-06 requirement).

### Tests

- `tests/test_config.py` — 5 new tests in `TestHITLConfig` covering defaults and env var overrides
- `tests/test_hitl.py` — 26 tests across 5 test classes:
  - `TestDisabledDefault` — disabled-by-default short-circuit
  - `TestProtectedFunctions` — regex detection and protected function gate
  - `TestAllExecuteGate` — all_execute=True prompts for every call
  - `TestFileOpsGate` — file upload/delete gate behavior
  - `TestElicitCall` — AcceptedElicitation, DeclinedElicitation, CancelledElicitation handling

## Commits

| Hash | Description |
|------|-------------|
| 1b4a463 | feat(04-01): add HITLConfig, hitl/gate.py, and config.yaml HITL block |
| a594ec2 | test(04-01): add HITL unit tests for gate logic and HITLConfig |

## Verification Results

All 58 tests pass (27 existing + 31 new).

```
python -m pytest tests/test_hitl.py tests/test_config.py -x -q
58 passed, 18 warnings in 0.53s
```

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED

- src/matlab_mcp/hitl/__init__.py: FOUND
- src/matlab_mcp/hitl/gate.py: FOUND
- tests/test_hitl.py: FOUND
- HITLConfig in config.py: FOUND (grep class HITLConfig)
- hitl field in AppConfig: FOUND (grep hitl: HITLConfig)
- hitl: in config.yaml: FOUND
- Commits 1b4a463, a594ec2: FOUND in git log
