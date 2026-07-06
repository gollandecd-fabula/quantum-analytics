# Bug Audit — One-Click Stable Release

Date: 2026-07-06
Branch: `fix/quantum-one-click-stable-release`

## Status

`BLOCKED`

## Findings

| ID | Severity | Finding | Evidence | Release impact |
|---|---:|---|---|---|
| QA-001 | P0 | Current execution environment cannot clone repository by HTTPS. | `git clone` failed with DNS resolution error and exit code `128`. | Blocks local tests, local smoke-test, and package execution. |
| QA-002 | P0 | No verified one-click package was executed. | No local package execution possible after checkout failure. | Blocks `READY`. |
| QA-003 | P0 | Existing application entry point is foundation-only health runtime. | `src/quantum/api/main.py` exposes `GET /health/technical` only. | Does not satisfy UI upload/calculation scenario. |
| QA-004 | P0 | Existing worker is idle foundation runtime. | `src/quantum/worker/main.py` returns `NO_DURABLE_QUEUE_CONFIGURED`. | Does not satisfy production-like import/calculation workflow. |
| QA-005 | P0 | Current repository documentation states `RELEASE_BLOCKED`. | `README.md` and `docs/governance/CURRENT_STATE.md`. | Blocks release claims. |
| QA-006 | P1 | Current documented runbook uses manual Python commands. | `docs/operations/LOCAL_RUNBOOK.md`. | Not one-click. |
| QA-007 | P1 | No current test run was performed in this audit. | Local checkout failed. | Cannot claim tests passed. |

## Non-findings

- No evidence was found that marketplace write mode is enabled.
- No financial hardcoded LarannA values were introduced by this audit.
- No user data directories were modified by this audit.

## Required next actions

1. Run in an environment with GitHub checkout access.
2. Execute `git status`, test discovery, and current CI.
3. Locate or create a verified one-click installer only after the current runtime can be tested.
4. Do not mark `READY` until installer and smoke-test succeed.