---
phase: 3
slug: streamable-http-transport-session-routing
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-01
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x with pytest-asyncio |
| **Config file** | `pyproject.toml` (pytest section) |
| **Quick run command** | `python -m pytest tests/test_server.py tests/test_config.py -x -q --timeout=30` |
| **Full suite command** | `python -m pytest tests/ -v --timeout=60` |
| **Estimated runtime** | ~55 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_server.py tests/test_config.py -x -q --timeout=30`
- **After every plan wave:** Run `python -m pytest tests/ -v --timeout=60`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 55 seconds

---

## Wave 0 Requirements

Existing test infrastructure covers base requirements. New transport tests will be added inline.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Codex CLI connects via streamable HTTP | TRNS-01 | Requires live Codex CLI client | Start server with `transport: streamablehttp`, connect Codex CLI to `http://localhost:8765/mcp` |
| Two simultaneous agents get isolated workspaces | TRNS-05 | Requires two concurrent MCP clients | Connect two agents simultaneously, each creates a file, verify no cross-contamination |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 55s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
