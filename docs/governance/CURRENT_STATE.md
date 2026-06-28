# CURRENT STATE

Date: 2026-06-28
Status: `BUILD_B1A_READY_FOR_MERGE`
Active contract: `STAGE-B-BUILD-v1`
Live execution state: `docs/evidence/STAGE_B_EXECUTION_STATE.yaml`
Current unit: `B1a — FINANCIAL_RULE_CONTRACTS_AND_RESOLUTION`
Tracking issue: `#7`
Working branch: `b1a-cleanup`
Pull Request: pending

## Scope

B1a is R2 contract/schema/fixture/test/evidence work only. No calculation kernel, active rules, real commercial data, marketplace writes, or production authorization. Source Authority remains DRAFT.

## Verification

- 34 Foundation tests.
- 34 B1a tests.
- 68 total tests passed.
- Technical CI `28307956212`: success.
- 31 Codex threads; 0 unresolved.
- Effective Manifest v6 verifies 159 permanent tracked artifacts.
- Temporary manifest diagnostics removed.

## Invariants

- deterministic tenant-safe and mode-isolated resolution;
- explicit `calculation_instant` with `[valid_from, valid_to)` filtering;
- complete ordering evidence and exactly one selected eligible candidate;
- typed unit/currency-safe expressions and rules;
- `NEGATE` and `ABS` require numeric results and operands;
- immutable Calculation Profiles;
- explicit purchase and per-item money metrics;
- reproducible tracked-tree evidence.

## Gate

Current cleanup head requires CI success, clean Codex review, and protected squash merge. B1b remains R3 and is not approved.

`RELEASE_BLOCKED`
