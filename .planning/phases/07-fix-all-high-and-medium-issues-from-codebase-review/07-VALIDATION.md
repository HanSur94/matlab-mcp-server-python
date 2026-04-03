---
phase: 7
slug: fix-all-high-and-medium-issues-from-codebase-review
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-03
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x with pytest-asyncio |
| **Config file** | pyproject.toml |
| **Quick run command** | `python -m pytest tests/ -x -q --timeout=30` |
| **Full suite command** | `python -m pytest tests/ -v --timeout=60` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q --timeout=30`
- **After every plan wave:** Run `python -m pytest tests/ -v --timeout=60`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | Security centralization | unit | `pytest tests/test_security.py -v` | ✅ | ⬜ pending |
| 07-01-02 | 01 | 1 | Blocklist expansion | unit | `pytest tests/test_security.py -v` | ✅ | ⬜ pending |
| 07-01-03 | 01 | 1 | Session ID sanitization | unit | `pytest tests/test_session.py -v` | ✅ | ⬜ pending |
| 07-02-01 | 02 | 2 | Pool resource leak fix | unit | `pytest tests/test_pool.py -v` | ✅ | ⬜ pending |
| 07-02-02 | 02 | 2 | Engine timeout enforcement | unit | `pytest tests/test_pool.py -v` | ✅ | ⬜ pending |
| 07-03-01 | 03 | 3 | Job state machine guards | unit | `pytest tests/test_jobs.py -v` | ✅ | ⬜ pending |
| 07-03-02 | 03 | 3 | TOCTOU fix | unit | `pytest tests/test_session.py -v` | ✅ | ⬜ pending |
| 07-04-01 | 04 | 4 | Server/config fixes | unit | `pytest tests/test_config.py -v` | ✅ | ⬜ pending |
| 07-04-02 | 04 | 4 | Monitoring fixes | unit | `pytest tests/test_monitoring*.py -v` | ✅ | ⬜ pending |
| 07-05-01 | 05 | 5 | Test quality improvements | unit | `pytest tests/ -v` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. Test framework (pytest + pytest-asyncio) and fixtures are already in place.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| MATLAB engine pool under load | Pool race conditions | Requires live MATLAB engines | Start server, run concurrent requests, verify no engine leaks |
| Custom tool security | Blocked function bypass | Requires MATLAB Engine API | Create custom tool with numeric injection, verify blocked |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
