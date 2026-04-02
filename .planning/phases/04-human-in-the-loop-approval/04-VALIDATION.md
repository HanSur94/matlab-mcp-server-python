---
phase: 4
slug: human-in-the-loop-approval
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-02
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x with pytest-asyncio |
| **Config file** | `pyproject.toml` (pytest section) |
| **Quick run command** | `python -m pytest tests/test_hitl.py tests/test_config.py -x -q --timeout=30` |
| **Full suite command** | `python -m pytest tests/ -v --timeout=60` |
| **Estimated runtime** | ~55 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_hitl.py tests/test_config.py -x -q --timeout=30`
- **After every plan wave:** Run `python -m pytest tests/ -v --timeout=60`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 55 seconds

---

## Wave 0 Requirements

- [ ] `tests/test_hitl.py` — stubs for HITL-01 through HITL-06

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Elicitation prompt appears in agent UI | HITL-01 | Requires real MCP client showing elicitation | Connect Claude Code, call a protected function, verify approval dialog appears |
| Approval denial blocks execution | HITL-01 | Requires human interaction with prompt | Deny the approval, verify MATLAB code was not executed |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 55s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
