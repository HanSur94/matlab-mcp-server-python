---
phase: 06-documentation-agent-onboarding
plan: "02"
subsystem: docs
tags: [mcp, streamablehttp, bearer-token, claude-code, codex-cli, cursor, onboarding]

# Dependency graph
requires:
  - phase: 02-auth-bearer-token
    provides: bearer token middleware and MATLAB_MCP_AUTH_TOKEN env var
  - phase: 03-streamable-http-transport
    provides: streamablehttp transport and /mcp endpoint
provides:
  - Copy-pasteable agent connection configs for Claude Code, Codex CLI, and Cursor
  - Troubleshooting guide for common connectivity issues
  - Security notes for bearer token management
affects: [future agents, deployment guides, README]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Self-contained per-agent documentation sections for direct navigation"
    - "Both stdio and HTTP options shown for each agent"

key-files:
  created:
    - docs/agent-onboarding.md
  modified: []

key-decisions:
  - "Document both stdio and streamable HTTP for each agent so developers can choose based on use case"
  - "SSE transport gets deprecation notice and migration instruction — no SSE configs provided as working examples"
  - "Each agent section is fully self-contained so readers can jump directly to their tool"

patterns-established:
  - "Agent onboarding docs: show both transports, stdio first (simpler), HTTP second (production)"
  - "All HTTP examples use bearer token header with env var reference, not hardcoded token"

requirements-completed: [PLAT-05]

# Metrics
duration: 2min
completed: 2026-04-02
---

# Phase 6 Plan 02: Agent Onboarding Documentation Summary

**Copy-pasteable MCP connection configs for Claude Code, Codex CLI, and Cursor over streamable HTTP with bearer token auth**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-04-02T06:37:58Z
- **Completed:** 2026-04-02T06:39:26Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created `docs/agent-onboarding.md` (327 lines) covering Claude Code, Codex CLI, and Cursor
- All HTTP examples use `http://127.0.0.1:8765/mcp` with `Authorization: Bearer ${MATLAB_MCP_AUTH_TOKEN}`
- Transport value in JSON configs uses `"streamable-http"` (MCP client format)
- Includes `--generate-token` workflow, troubleshooting section, and config reference
- No SSE transport configs recommended; SSE deprecation notice included

## Task Commits

Each task was committed atomically:

1. **Task 1: Write agent onboarding guide with connection examples** - `9ba0b3d` (feat)

**Plan metadata:** (pending final commit)

## Files Created/Modified

- `docs/agent-onboarding.md` - Agent connection guide for Claude Code, Codex CLI, and Cursor

## Decisions Made

- Document both stdio and streamable HTTP for each agent — stdio for local single-user, HTTP for team/production
- SSE transport gets deprecation notice and migration instruction; no working SSE configs provided (Codex CLI specifically notes SSE incompatibility as the root cause of original connectivity failures)
- Each agent section is self-contained to support direct navigation (readers skip to their agent)

## Deviations from Plan

None — plan executed exactly as written.

The worktree branch needed rebasing onto `master` before execution to pick up Phase 02-05 work (streamable HTTP, bearer token middleware). This was a setup step, not a deviation.

## Issues Encountered

The worktree branch `worktree-agent-acd511ff` was based on commit `29e30f7` (pre-Phase-02), which lacked the streamable HTTP transport and bearer token auth implemented in Phases 02-03. Rebased onto `master` before starting to ensure the documentation accurately reflects what the current codebase provides.

## User Setup Required

None — documentation only, no external service configuration required.

## Next Phase Readiness

- Phase 06 documentation complete: windows-deployment.md (plan 01) and agent-onboarding.md (plan 02)
- Phase 06 completes the v2.0 milestone documentation
- Agent onboarding guide ready for review and publishing to wiki/README
