---
phase: 06-documentation-agent-onboarding
verified: 2026-04-02T06:42:50Z
status: human_needed
score: 3/3 must-haves verified
re_verification: false
human_verification:
  - test: "Follow windows-deployment.md end-to-end on a real restricted Windows 10 machine — pip install to first MATLAB tool call"
    expected: "Every step succeeds without admin rights, no UAC prompts, server starts and responds to curl test"
    why_human: "Guide correctness on a live restricted machine cannot be verified programmatically; requires a Windows 10 environment with MATLAB installed"
  - test: "Connect Claude Code using the streamable HTTP config from agent-onboarding.md"
    expected: "Claude Code lists MATLAB tools and successfully calls execute_code with disp('Hello from MATLAB')"
    why_human: "Requires a running MATLAB MCP server and an active Claude Code session; not automatable in static verification"
  - test: "Connect Codex CLI using the streamable HTTP config from agent-onboarding.md"
    expected: "Codex CLI connects, tool list appears, and execute_code call succeeds"
    why_human: "Requires Codex CLI binary and running server; can only verify config format, not actual connectivity"
---

# Phase 6: Documentation + Agent Onboarding Verification Report

**Phase Goal:** Any developer can follow written guides to deploy the server on Windows 10 without admin rights and connect Claude Code, Codex CLI, or Cursor with minimal friction
**Verified:** 2026-04-02T06:42:50Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (derived from ROADMAP success criteria)

| #   | Truth                                                                                                                      | Status     | Evidence                                                                                                                     |
| --- | -------------------------------------------------------------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 1   | A developer on a restricted Windows 10 machine can complete the deployment guide from pip install to first MATLAB tool call without needing admin rights | ✓ VERIFIED | `docs/windows-deployment.md` (454 lines) covers every step: Python user-space install, pip install matlabengine, pip install matlab-mcp-python, config.yaml, server start, curl test — all without admin. Loopback-only default documented. |
| 2   | Connection examples for Claude Code, Codex CLI, and Cursor are present, each showing the exact config including bearer_token_env_var | ✓ VERIFIED | `docs/agent-onboarding.md` (327 lines) has self-contained sections for all three agents. Every HTTP config block contains `"Authorization": "Bearer ${MATLAB_MCP_AUTH_TOKEN}"`. |
| 3   | All doc examples use the streamable HTTP transport at `/mcp`, not SSE                                                      | ✓ VERIFIED | windows-deployment.md: 5 occurrences of `streamablehttp`, 0 SSE configs. agent-onboarding.md: 14 occurrences of `streamablehttp`/`streamable-http`, 0 SSE configs. SSE appears only as a deprecated warning. |

**Score:** 3/3 truths verified

---

### Required Artifacts

| Artifact                        | Expected                                          | Lines  | Status     | Details                                                                 |
| ------------------------------- | ------------------------------------------------- | ------ | ---------- | ----------------------------------------------------------------------- |
| `docs/windows-deployment.md`    | Step-by-step Windows 10 no-admin deployment guide | 454    | ✓ VERIFIED | Exceeds 120-line minimum. All 7 required sections present plus HITL appendix. |
| `docs/agent-onboarding.md`      | Agent connection examples for 3 agents            | 327    | ✓ VERIFIED | Exceeds 100-line minimum. Claude Code, Codex CLI, Cursor sections fully self-contained. |

Both artifacts are substantive (not stubs). No TODO/FIXME/placeholder patterns found in either file.

---

### Key Link Verification

| From                           | To                          | Via                                    | Pattern Expected                      | Status     | Details                                                                        |
| ------------------------------ | --------------------------- | -------------------------------------- | ------------------------------------- | ---------- | ------------------------------------------------------------------------------ |
| `docs/windows-deployment.md`   | `config.yaml`               | config examples embedded in guide      | `transport.*streamablehttp`           | ✓ WIRED    | Lines 130, 159, 249, 252 contain `transport: "streamablehttp"`. 5 total matches. |
| `docs/agent-onboarding.md`     | `src/matlab_mcp/server.py`  | CLI flags and transport config         | `streamablehttp\|/mcp\|bearer`        | ✓ WIRED    | 24 matches across endpoint URL `http://127.0.0.1:8765/mcp`, transport name, bearer header. |

---

### Data-Flow Trace (Level 4)

Not applicable. Both artifacts are documentation files, not components rendering dynamic data. No data-flow trace required.

---

### Behavioral Spot-Checks

Documentation-only phase. No runnable entry points produced. Step 7b skipped.

---

### Requirements Coverage

| Requirement | Source Plan   | Description                                                                  | Status       | Evidence                                                                                                     |
| ----------- | ------------- | ---------------------------------------------------------------------------- | ------------ | ------------------------------------------------------------------------------------------------------------ |
| PLAT-04     | 06-01-PLAN.md | Windows 10 deployment guide with step-by-step instructions for restricted machines | ✓ SATISFIED  | `docs/windows-deployment.md` exists (454 lines), covers all required sections, uses 127.0.0.1 default with explicit admin note for 0.0.0.0. Commit `97fd806`. |
| PLAT-05     | 06-02-PLAN.md | Agent onboarding docs with connection examples for Claude Code, Codex CLI, and Cursor | ✓ SATISFIED  | `docs/agent-onboarding.md` exists (327 lines), all three agents covered with both stdio and HTTP configs. Commit `9ba0b3d`. |

**Note — REQUIREMENTS.md checkbox discrepancy:** PLAT-04 shows `- [ ]` (unchecked) and `Pending` status in the traceability table, even though `docs/windows-deployment.md` was created and committed. PLAT-05 correctly shows `- [x]` and `Complete`. The REQUIREMENTS.md file should be updated to mark PLAT-04 as `[x]` and `Complete` to reflect reality. This is a bookkeeping gap, not a code gap — the guide itself is complete.

**Orphaned requirements check:** No additional PLAT-04 or PLAT-05 references found in REQUIREMENTS.md that were unmapped.

---

### Anti-Patterns Found

| File                            | Line | Pattern | Severity | Impact |
| ------------------------------- | ---- | ------- | -------- | ------ |
| `docs/windows-deployment.md`    | —    | None found | — | — |
| `docs/agent-onboarding.md`      | —    | None found | — | — |

No TODO, FIXME, placeholder, or stub patterns found in either documentation file.

---

### Human Verification Required

#### 1. End-to-End Windows 10 No-Admin Deployment

**Test:** Follow `docs/windows-deployment.md` on a real restricted Windows 10 machine — install Python (user-space), install `matlabengine` via pip, install `matlab-mcp-python`, create the minimal `config.yaml`, run `matlab-mcp --transport streamablehttp`, then execute the curl test from the "First MATLAB Tool Call" section.

**Expected:** Every step completes without UAC prompts or admin dialogs. The curl test returns a JSON response with `"protocolVersion": "2024-11-05"`. Server logs show the startup banner with `HTTP endpoint: http://127.0.0.1:8765/mcp`.

**Why human:** Requires a live Windows 10 machine with MATLAB R2022b+ installed. Cannot simulate OS-level firewall behavior, UAC prompts, or MATLAB engine startup programmatically.

#### 2. Claude Code Connection via Streamable HTTP

**Test:** Copy the streamable HTTP config from the Claude Code section of `docs/agent-onboarding.md` into `.mcp.json`, set `MATLAB_MCP_AUTH_TOKEN`, start the server, and ask Claude Code: "Run `disp('Hello from MATLAB')` in MATLAB."

**Expected:** Claude Code successfully calls the `execute_code` tool and returns `Hello from MATLAB` as output. No connection errors.

**Why human:** Requires Claude Code CLI, a running MATLAB MCP server, and a live agent session. The config format can be verified statically (done above), but end-to-end connectivity requires execution.

#### 3. Codex CLI Connection via Streamable HTTP

**Test:** Copy the Codex CLI streamable HTTP config from `docs/agent-onboarding.md`, confirm Codex CLI connects and can list MATLAB tools.

**Expected:** Codex CLI establishes MCP handshake, lists tools including `execute_code`, and a simple code execution succeeds.

**Why human:** Requires Codex CLI binary. The guide specifically notes SSE incompatibility (historical root cause of connectivity failures) — verifying that the documented streamable HTTP config resolves this requires running Codex CLI.

---

### Gaps Summary

No automated gaps. All artifacts exist, are substantive, and are correctly wired. The one bookkeeping item is that REQUIREMENTS.md shows PLAT-04 as `Pending` with an unchecked checkbox, while the actual guide (`docs/windows-deployment.md`) is fully complete and committed. This should be corrected but does not block phase goal achievement.

Three items require human verification because they involve live Windows 10 environments, running MATLAB engines, and active agent sessions that cannot be tested statically.

---

_Verified: 2026-04-02T06:42:50Z_
_Verifier: Claude (gsd-verifier)_
