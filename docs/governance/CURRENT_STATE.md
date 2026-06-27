# CURRENT STATE

Date: 2026-06-27
Status: `BUILD_B1A_READY_FOR_MERGE`
Active contract: `STAGE-B-BUILD-v1`
Live execution state: `docs/evidence/STAGE_B_EXECUTION_STATE.yaml`
Current unit: `B1a — FINANCIAL_RULE_CONTRACTS_AND_RESOLUTION`
Tracking issue: `#7`
Working branch: `build-b1a-financial-contracts`
Pull Request: `#8`

## Scope

B1a is R2 contract/schema/fixture/test/evidence work only. No calculation kernel, active rules, real commercial data, marketplace writes, or production authorization. Source Authority remains DRAFT.

## Verification

- 34 Foundation tests.
- 34 B1a tests.
- 68 total tests passed.
- Technical CI `28304873043`: success.
- 28 Codex threads; 0 unresolved.
- Manifest v6 verifies 158 tracked artifacts.

## Invariants

- deterministic tenant-safe and mode-isolated resolution;
- complete ordering evidence for eligible candidates;
- VALID traces contain an eligible candidate;
- typed unit/currency-safe expressions and rules;
- immutable Calculation Profiles;
- explicit purchase and per-item money metrics;
- reproducible tracked-tree evidence.

## Gate

Current head requires CI success, clean Codex review, and protected squash merge of PR #8. B1b remains R3 and is not approved.

`RELEASE_BLOCKED`
