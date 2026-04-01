---
phase: 2
slug: auth-config-bearer-token-middleware
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-01
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x with pytest-asyncio |
| **Config file** | `pyproject.toml` (pytest section) |
| **Quick run command** | `python -m pytest tests/test_auth.py tests/test_config.py -x -q --timeout=30` |
| **Full suite command** | `python -m pytest tests/ -v --timeout=60` |
| **Estimated runtime** | ~50 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/test_auth.py tests/test_config.py -x -q --timeout=30`
- **After every plan wave:** Run `python -m pytest tests/ -v --timeout=60`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 50 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 2-01-01 | 01 | 1 | AUTH-01, AUTH-03 | unit | `python -m pytest tests/test_auth.py -v --timeout=30` | ❌ W0 | ⬜ pending |
| 2-01-02 | 01 | 1 | AUTH-02 | unit | `python -m pytest tests/test_config.py -v --timeout=30` | ✅ | ⬜ pending |
| 2-01-03 | 01 | 1 | AUTH-04 | unit | `python -m pytest tests/test_auth.py -k cors -v --timeout=30` | ❌ W0 | ⬜ pending |
| 2-01-04 | 01 | 1 | AUTH-05 | unit | `python -m pytest tests/test_server.py -k stdio -v --timeout=30` | ✅ | ⬜ pending |
| 2-01-05 | 01 | 1 | AUTH-06 | unit | `python -m pytest tests/test_server.py -k generate_token -v --timeout=30` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_auth.py` — stubs for AUTH-01, AUTH-03, AUTH-04 (bearer validation, 401 responses, CORS)
- [ ] Test fixtures for ASGI app with middleware stack

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Browser CORS pre-flight works end-to-end | AUTH-04 | Requires real browser sending OPTIONS pre-flight | Open browser dev tools, fetch from cross-origin, verify no CORS errors |
| `--generate-token` CLI output is copy-pasteable | AUTH-06 | Output readability is subjective | Run `matlab-mcp --generate-token`, copy output, set env var, verify server accepts token |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 50s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
