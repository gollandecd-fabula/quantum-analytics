# CURRENT STATE

Date: 2026-06-27
Status: `BUILD_B1A_FINAL_REVIEW_PENDING`
Active contract: `STAGE-B-BUILD-v1`
Live execution state: `docs/evidence/STAGE_B_EXECUTION_STATE.yaml`
Completed macro-stage: `A — FOUNDATION`
Completed unit: `B0 — BUILD_READINESS_AND_STAGE_CONTRACT`
Current unit: `B1a — FINANCIAL_RULE_CONTRACTS_AND_RESOLUTION`
Tracking issue: `#7`
Working branch: `build-b1a-financial-contracts`
Pull Request: `#8`

## Authority and scope

- Constitution v3.0 / Plan v152.0 remains authoritative.
- Macro-stage B was explicitly approved in `DEC-024`.
- B1a is R2 contract, schema, fixture, and test work.
- B1a does not implement the calculation kernel or activate financial rules.
- Source Authority remains DRAFT; real commercial data is not admitted.
- Marketplace write capability and production release remain blocked.

## B0 baseline

- PR #6 merged into protected `main` as `d34394c56037132e4d9de95283beb9ca3871fb0e`.
- Issue #5 closed completed.
- Stage Contract B, requirements, acceptance plan, risks, and governance controls are present in `main`.

## B1a deliverables

Contracts:

- configuration rule and deterministic resolution;
- safe expression with typed literal representations;
- calculation profile;
- versioned rounding policy;
- draft metric catalogue with separate purchase quantity and amount flows;
- independent golden-oracle plan.

Machine-readable schemas:

- configuration rule;
- safe expression;
- rounding policy;
- calculation profile;
- metric definition;
- rule-resolution result.

Tests and evidence:

- resolution and validation vectors;
- contract-alignment tests;
- execution-state test;
- financial contract tests;
- review-regression tests;
- rounding-mapping test;
- `STAGE_B_B1A_CONTRACT_EVIDENCE.yaml`.

## Verification

- Foundation tests: 34.
- B1a tests: 19.
- Reproducible total: 53 passed tests.
- Latest successful CI before final metadata synchronization: run `28295167667`, Python 3.12.3.
- Independent Codex review produced 12 P1/P2 threads across multiple reviewed heads.
- All 12 threads are resolved after contract, schema, catalogue, fixture, and test corrections.
- Fresh CI and Codex review are required for this final metadata-synchronized head.

## Confirmed invariants

- no fixed commercial cost, tax, tax-base, other-expense, allocation, or rounding default;
- exactly one rule method payload is present;
- organization boundary and lexicographic scope specificity are deterministic;
- unresolved semantic ties fail closed as `CONFLICT`;
- missing required configuration becomes `BLOCKED`, not zero;
- numeric zero remains a `VALID` value, not a typed state;
- Actual and Scenario remain isolated;
- dependency cycles, unsafe expressions, invalid arity, overlap, and unit mismatch fail closed;
- decimal, integer, and boolean literal representations match their declared types;
- purchases are represented by explicit quantity and amount metrics and are not inferred from sales, inventory, payout, or configured product cost;
- rounding-point mapping is unambiguous and versioned;
- calculation profiles reference immutable positive integer versions and content hashes;
- golden values require an independent oracle and are not approved in B1a.

## Remaining B1a gate

- final-head CI must pass;
- final-head Codex review must complete;
- any new findings must be fixed and resolved;
- PR #8 must be squash-merged through protected `main`.

## Approval gates

- B1b calculation implementation is R3 and is not approved.
- No configuration rule or rounding policy may become ACTIVE in B1a.
- B2, B6, B7, production, real-data admission, and Macro-stage C remain unapproved.

## Release state

`RELEASE_BLOCKED`
