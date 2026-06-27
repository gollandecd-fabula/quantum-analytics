# CURRENT STATE

Date: 2026-06-27
Status: `BUILD_B1A_READY_FOR_MERGE`
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
- safe expression with typed literal and currency metadata rules;
- calculation profile with canonical immutable reference shape;
- versioned rounding policy;
- draft metric catalogue with separate purchase quantity and amount flows;
- independent golden-oracle plan.

Machine-readable schemas:

- configuration rule with omission-only wildcard scope encoding;
- safe expression with typed values and currency constraints on every node kind;
- rounding policy;
- calculation profile with `{id, version, content_hash}` references;
- metric definition;
- rule-resolution result with complete eligible-candidate trace requirements.

Tests and evidence:

- omission-only resolution and validation vectors;
- strict resolver matcher with explicit-null rejection;
- contract-alignment tests;
- MONEY currency-node test;
- rounding-policy ownership test;
- execution-state test;
- financial contract tests;
- review-regression tests;
- rounding-mapping test;
- `STAGE_B_B1A_CONTRACT_EVIDENCE.yaml`.

## Verification

- Foundation tests: 34.
- B1a tests: 25.
- Reproducible total: 59 passed tests.
- Latest technical CI: run `28298583275`, Python 3.12.3, success.
- Independent Codex review produced 19 P1/P2 threads across multiple reviewed heads.
- All 19 threads are resolved.
- Current metadata-synchronized head must pass CI and Codex review before squash merge.

## Confirmed invariants

- no fixed commercial cost, tax, tax-base, other-expense, allocation, or rounding default;
- exactly one rule method payload is present;
- rounding policy is not a Configuration Rule type and is referenced exclusively by Calculation Profile `rounding_policy_ref`;
- only `organization_id` is mandatory in rule scope; absent optional dimensions are the sole wildcard encoding and explicit nulls are forbidden;
- resolver fixtures and matcher use the same omission-only wildcard semantics;
- organization boundary and lexicographic scope specificity are deterministic;
- eligible candidates contain exactly four ordering components and no exclusion reasons;
- ineligible candidates contain at least one exclusion reason and a null ordering tuple;
- unresolved semantic ties fail closed as `CONFLICT`;
- missing required configuration becomes `BLOCKED`, not zero;
- numeric zero remains a `VALID` value, not a typed state;
- Actual and Scenario remain isolated;
- dependency cycles, unsafe expressions, invalid arity, overlap, and unit mismatch fail closed;
- decimal, integer, and boolean literal representations match their declared types;
- every MONEY literal, variable, and operation carries an explicit ISO currency; non-MONEY nodes use `currency: null`;
- purchases are represented by explicit quantity and amount metrics and are not inferred from sales, inventory, payout, or configured product cost;
- rounding-point mapping is unambiguous and versioned;
- Calculation Profile references use canonical `{id, version, content_hash}` objects with positive integer versions;
- golden values require an independent oracle and are not approved in B1a.

## Remaining B1a gate

- current metadata-synchronized head CI must pass;
- current metadata-synchronized head Codex review must complete with no unresolved findings;
- PR #8 must be squash-merged through protected `main`.

## Approval gates

- B1b calculation implementation is R3 and is not approved.
- No configuration rule or rounding policy may become ACTIVE in B1a.
- B2, B6, B7, production, real-data admission, and Macro-stage C remain unapproved.

## Release state

`RELEASE_BLOCKED`
