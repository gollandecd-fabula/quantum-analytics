# CURRENT STATE

Date: 2026-06-27
Status: `BUILD_B1A_REVIEW_PENDING`
Active contract: `STAGE-B-BUILD-v1`
Live execution state: `docs/evidence/STAGE_B_EXECUTION_STATE.yaml`
Completed macro-stage: `A — FOUNDATION`
Completed unit: `B0 — BUILD_READINESS_AND_STAGE_CONTRACT`
Current unit: `B1a — FINANCIAL_RULE_CONTRACTS_AND_RESOLUTION`
Tracking issue: `#7`
Working branch: `build-b1a-financial-contracts`
Pull Request: `#8`

## Authority

- Constitution v3.0 / Plan v152.0 remains authoritative.
- Macro-stage B was explicitly approved and recorded in `DEC-024`.
- B1a is R2 contracts/schemas/tests work allowed by Stage Contract B after B0 merge.
- The Stage Contract file is an immutable normative and initial-plan snapshot.
- `STAGE_B_EXECUTION_STATE.yaml` and this document are the live unit-state sources.
- B1b, B2, B6, B7, all R4 work, real-data admission, rule activation, and production remain separately gated.

## Completed B0 baseline

- PR #6 was merged into protected `main` as commit `d34394c56037132e4d9de95283beb9ca3871fb0e`.
- Issue #5 is closed as completed.
- Stage Contract B, BUILD requirements, acceptance plan, readiness evidence, decisions, risks, and repository controls are present in `main`.
- B0 Foundation CI passed and all Codex review findings were resolved.

## B1a scope

B1a defines financial contracts and executable contract tests only. It does not:

- implement the calculation kernel;
- create or activate commercial cost, tax, tax-base, other-expense, allocation, or rounding defaults;
- activate Source Authority;
- admit real commercial data;
- change marketplace write capability;
- deploy externally.

## B1a artifacts

Contracts:

- `docs/finance/CONFIGURATION_RULE_CONTRACT.md`;
- `docs/finance/RULE_RESOLUTION_CONTRACT.md`;
- `docs/finance/SAFE_EXPRESSION_CONTRACT.md`;
- `docs/finance/CALCULATION_PROFILE_CONTRACT.md`;
- expanded `docs/finance/ROUNDING_POLICY.md`;
- `docs/finance/METRIC_CATALOGUE.md`;
- `docs/finance/GOLDEN_ORACLE_PLAN.md`.

Schemas:

- strengthened `schemas/configuration-rule.schema.json`;
- `schemas/safe-expression.schema.json`;
- `schemas/rounding-policy.schema.json`;
- `schemas/calculation-profile.schema.json`;
- `schemas/metric-definition.schema.json`;
- `schemas/rule-resolution-result.schema.json`.

Tests and evidence:

- `tests/contracts/fixtures/b1a-rule-resolution-vectors.json`;
- `tests/test_b1a_financial_contracts.py` with 9 financial contract tests;
- `tests/test_b1a_execution_state.py` with 1 live-state test;
- `docs/evidence/STAGE_B_B1A_CONTRACT_EVIDENCE.yaml`;
- `docs/evidence/STAGE_B_EXECUTION_STATE.yaml`.

## B1a verification

- Initial PR #8 CI run `28292470434` passed before evidence synchronization.
- One transient-state assertion failed after CURRENT_STATE advanced to review-pending.
- The focused test was corrected without weakening B0/B1a/R3 semantic assertions.
- Corrected-head CI run `28292518502` completed successfully on Python 3.12.3.
- Existing Foundation suite: 34 tests.
- New B1a suite: 10 tests.
- Reproducible total: 44 passed tests.
- A final documentation-only CI is required for the current head after this synchronization.
- Independent Codex review is pending.

## Contract invariants

- financial values and assumptions are versioned configuration, never system constants;
- exactly one of fixed value, rate, or safe expression is selected;
- typed scope and deterministic ordering control rule selection;
- semantic ties fail closed as `CONFLICT`;
- missing required configuration becomes `BLOCKED`, not zero;
- Actual ignores Scenario-scoped rules;
- dependency cycles and unknown dependencies fail closed;
- arbitrary code and implicit currency conversion are forbidden;
- decimal strings and versioned rounding replace binary floating-point assumptions;
- metrics declare accounting view, required inputs, and expense boundary;
- calculation profiles snapshot immutable versions and content hashes;
- golden values require an independent oracle and are not approved in B1a.

## Remaining B1a gate

- final documentation-only Foundation CI must pass;
- PR #8 must be Ready for review;
- independent Codex review must inspect the latest head;
- all findings must be fixed and conversations resolved;
- protected squash merge must succeed.

## Approval gates

- B1b financial calculation implementation is R3 and is not approved.
- No configuration rule or rounding policy may become ACTIVE in B1a.
- Source Authority rows remain DRAFT.
- Real or anonymized commercial data has not been admitted.
- Final hosting platform has not been selected.
- Production release and Macro-stage C are not approved.

## Release state

`RELEASE_BLOCKED`
