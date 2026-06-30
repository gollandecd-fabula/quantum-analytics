# CURRENT STATE

Date: 2026-06-30
Status: `BUILD_P1_5_FINDINGS_REMEDIATED_TESTS_PENDING`
Active contract: `STAGE-B-BUILD-v1`
Live execution state: `docs/evidence/STAGE_B_EXECUTION_STATE.yaml`
Current unit: `P15 — UX_ONBOARDING_EXCEPTION_INBOX_FOUNDATION`
Mapped unit: `B5 — UX, onboarding, and Exception Inbox`
Tracking issue: `#29`
Working branch: `p15-ux-onboarding-exception-inbox`

## Current result

P1.5 implements dependency-free, headless UX contracts over the completed B1a,
B3, B4, and ingestion foundations. The current branch provides:

- explicit preview-only inputs for cost, tax rate, tax base, and other expense;
- B1a-aligned RATE tax-base vocabulary with `NONE` rejected;
- explicit organization, Actual/Scenario, scope, validity, and currency controls;
- no-hidden-default behavior and distinct numeric-zero semantics;
- all canonical decimal-zero strings rendered as `valid-zero`;
- text-first accessible views for typed metric and import states;
- preview-safe Evidence Chain drill-down;
- deterministic Exception Inbox entries with cause, evidence, affected metrics,
  required resolution, and independent-result continuity;
- fail-closed organization, mode, tenant, duplicate, and forged-input controls;
- duplicate configuration form identifiers rejected;
- non-empty tenant identifiers enforced for every Inbox mode;
- machine-readable schemas and 61 declared targeted test methods.

The three Codex Review findings on commit `408ef82a…` have been remediated.
Exact-head tests, artifact-manifest synchronization, review recheck, thread
resolution, and closure remain pending. No current-head pass is claimed.

## Completed baseline

P1.4/B4 remains complete at merge commit
`f19bfb652fccca9f205e2c83d334bd157d3e257c` with 37 targeted tests, Foundation
CI, OSS Admission, OSV, artifact-manifest equality, and zero unresolved review
threads.

## Critical path

B1b remains blocked because an independent golden oracle owner and approved
golden baseline are not available. P1.5 does not activate the financial
calculation kernel and does not unblock B2 or B6.

## Exclusions

No financial calculation or rule activation, real marketplace data, external
HTTP service, browser deployment, external authentication, database
persistence, production release, or marketplace writes are included.

`RELEASE_BLOCKED`
