# CURRENT STATE

Date: 2026-06-30
Status: `BUILD_B1B_REVIEW_PENDING_CI_AND_INDEPENDENT_REVIEW`
Active contract: `STAGE-B-BUILD-v1`
Live execution state: `docs/evidence/STAGE_B_EXECUTION_STATE.yaml`
Current unit: `B1b — CALCULATION_KERNEL_IMPLEMENTATION`
Risk: `R3`
Tracking issue: `#32`
Working branch: `build-b1b-financial-kernel-v1`

## Authorization

Explicit user R3 authorization was recorded on 2026-06-30.

- Business Golden Oracle Owner: project owner/user.
- Baseline source: synthetic test scenarios under the approved methodology.
- Exact Golden Baseline values were explicitly approved by the owner on 2026-06-30.
- Scenarios 1–3 were approved without changes.
- Scenario 4 preserves `net_profit_amount = -44.00` and blocks
  `profit_per_sold_unit` when `net_sold_units` is negative.
- External second-line financial review remains mandatory before admission of real
  or anonymized commercial data or production use.

## Implementation candidate

The B1b branch contains a dependency-free preview financial kernel with:

- decimal-only arithmetic and versioned rounding;
- typed `VALID`, `EMPTY`, `BLOCKED`, `UNAVAILABLE`, and `CONFLICT` results;
- deterministic B1a rule resolution and typed Safe Expression evaluation;
- explicit cost, tax rate, tax base, and named other-expense inputs;
- no hidden commercial defaults or fixed commercial constants;
- Actual/Scenario isolation;
- independent reference oracle that does not import the production runtime;
- four owner-approved synthetic Golden Baseline scenarios;
- 67 targeted test methods prepared for rerun after the owner-signoff patch;
- compile, AST security, fixed-commercial-constant, Foundation CI, and OSS Admission
  controls required on the new exact head.

## Pending controls

B1b is not complete until:

1. the full accumulated repository test suite and required GitHub CI pass on the
   owner-signoff patch exact head;
2. OSS Admission/registry/OSV checks pass on the same exact head;
3. independent code review has no unresolved findings;
4. exact reviewed-head and post-merge evidence are recorded.

## Critical path

B2 remains gated by B1b completion. B6 remains gated by B1b and B2. B7 external
access remains unauthorized. No subsequent R3 unit has been started.

## Exclusions

No ACTIVE financial rule or profile, Source Authority activation, real or
anonymized marketplace data, B2 reconciliation/restatement, external HTTP
service, browser deployment, external authentication, database persistence,
production release, or marketplace write is included.

`RELEASE_BLOCKED`
