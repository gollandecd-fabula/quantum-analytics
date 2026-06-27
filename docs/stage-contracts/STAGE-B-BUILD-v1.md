# Stage Contract B — BUILD v1

Status: `ACTIVE_FOR_B0`; later units remain subject to their gates.
Authority: explicit user approval on 2026-06-27.
Tracking issue: `#5`.

## Goal

Build a marketplace-neutral, read-only analytics product on top of the verified
FOUNDATION baseline. The stage must deliver configurable financial rules,
reconciliation, reproducible Evidence Chain, reporting, user experience,
decision support, internal QA, and security review without hardcoded commercial
assumptions or unverified source semantics.

## Non-goals

- Marketplace write operations.
- Production release approval.
- Kubernetes or premature microservices.
- Arbitrary user code execution.
- Hidden defaults for cost, tax, tax base, other expenses, allocation, or rounding.
- Treating synthetic fixtures as verified Wildberries source contracts.

## Units

### B0 — Build readiness and Stage Contract

Risk: `R1`.

Outputs:

- Stage Contract B;
- BUILD requirements snapshot;
- BUILD acceptance plan;
- machine-readable readiness evidence;
- synchronized Current State, Decision Ledger, and Risk Register.

Gate: no financial implementation is permitted in B0.

### B1 — Configurable financial rules and calculation kernel

#### B1a — Financial contracts and rule resolution

Risk: `R2`.

Outputs:

- typed rule vocabulary and scope contract;
- method and safe-expression contract;
- rule precedence, overlap, exclusivity, and double-count controls;
- versioned rounding and calculation-profile snapshot contracts;
- metric catalogue with explicit expense boundaries;
- golden-calculation specification and independent oracle plan.

#### B1b — Calculation kernel implementation

Risk: `R3`.

Outputs:

- decimal calculation kernel;
- typed blocked/unavailable/conflict results;
- Actual and Scenario isolation;
- approved golden, property, and differential tests.

Gate: explicit user approval is required before B1b implementation or activation
of any cost, tax, allocation, other-expense, or rounding rule.

### B2 — Reconciliation, periods, and restatement

Risk: `R3`.

Outputs:

- row-wise and aggregate reconciliation;
- operational, settlement, and tax-recognition views;
- period states OPEN, PROVISIONAL, CLOSED, and RESTATED;
- source-authority conflict handling;
- impact reports for revisions, reversals, and late corrections.

Gate: explicit user approval and approved B1 contracts are required.

### B3 — Metric snapshots and Evidence Chain

Risk: `R2`.

Outputs:

- immutable metric-result contract;
- calculation-profile version linkage;
- source-record and source-file traceability;
- freshness, confidence, and validity metadata;
- reproducible recalculation reason and actor audit.

### B4 — Reporting, API, and exports

Risk: `R2`.

Outputs:

- explicit operational, settlement, tax, and profitability reports;
- metric API contracts;
- export contracts that preserve typed states and provenance;
- confirmed expense-boundary labels.

### B5 — UX, onboarding, and Exception Inbox

Risk: `R2`.

Outputs:

- configuration input flows for cost, tax, tax base, and other expenses;
- typed-state rendering without converting missing values to zero;
- exception and conflict resolution workflow;
- accessibility and critical-path tests.

### B6 — Decision support and scenarios

Risk: `R3`.

Outputs:

- explainable recommendations linked to evidence;
- scenario modelling isolated from Actual results;
- forecast assumptions and confidence ranges;
- no external action execution.

Gate: explicit user approval is required before recommendation ranking or
financial forecast implementation.

### B7 — Identity, tenant isolation, and security controls

Risk: `R3` for externally accessible authentication and tenant isolation.

Outputs:

- approved-user-only access;
- session and account lifecycle controls;
- tenant-isolation enforcement and tests;
- file-abuse controls, privacy-safe logs, secrets, SBOM, and threat model;
- deployment-specific security controls for Railway, Vercel, or Cloudflare.

Gate: explicit user approval is required before external-access implementation.
Production credentials remain unavailable to implementation agents.

### B8 — Internal QA, security review, and BUILD evidence package

Risk: `R2`.

Outputs:

- targeted and full BUILD test portfolio;
- independent financial oracle evidence;
- security review and unresolved-risk report;
- rollback and recovery evidence available at the BUILD level;
- immutable BUILD Evidence Package;
- recommendation for transition to Macro-stage C without starting it.

## Autonomous scope

Inside this contract, R0 and R1 work proceeds autonomously. R2 documentation,
contracts, tests, reversible implementation, and preview-only work may proceed
when Definition of Ready is satisfied, an independent reviewer verifies the
change, and the protected-branch workflow passes.

The implementation actor cannot approve its own R2-or-higher change or its own
financial golden baseline.

## Gates

Explicit user approval is required for:

- every R3 or R4 unit;
- activation of financial rules or Source Authority rows;
- admission of real or anonymized commercial marketplace data;
- external authentication or tenant-access implementation;
- final selection of Railway, Vercel, or Cloudflare;
- production deployment or marketplace write capability;
- scope changes outside this contract.

A blocked unit does not block independent units unless a documented dependency
requires it.

## Definition of Done

- Every BUILD requirement traces to an Issue, branch, Pull Request, tests, and evidence.
- Financial rules are configurable, versioned, scoped, and free of fixed commercial constants.
- Decimal arithmetic and an approved versioned rounding policy are enforced.
- Missing, blocked, unavailable, conflict, valid, and numeric zero remain distinct.
- Actual and Scenario results cannot contaminate each other.
- Returns, revisions, reversals, and restatements do not double count value or cost.
- Reconciliation passes row-wise and aggregate-wise against approved source authority.
- Every published metric has a reproducible Evidence Chain.
- Reports state their confirmed expense boundary and accounting view.
- UI critical paths preserve typed states and meet accessibility checks.
- Recommendations are explainable and cannot execute marketplace actions.
- Authentication, tenant isolation, and security controls pass their approved tests before external access.
- Required CI, financial, security, and recovery evidence is immutable and reviewable.
- BUILD Evidence Package lists remaining limitations and release blockers.
- Transition to Macro-stage C is not performed without explicit user approval.

## Machine-readable summary

```yaml
stage_contract_id: STAGE-B-BUILD-v1
macro_stage: B
status: ACTIVE_FOR_B0
tracking_issue: 5
units:
  B0: {risk: R1, state: IN_PROGRESS}
  B1a: {risk: R2, state: PLANNED}
  B1b: {risk: R3, state: GATED}
  B2: {risk: R3, state: GATED}
  B3: {risk: R2, state: PLANNED}
  B4: {risk: R2, state: PLANNED}
  B5: {risk: R2, state: PLANNED}
  B6: {risk: R3, state: GATED}
  B7: {risk: R3, state: GATED}
  B8: {risk: R2, state: PLANNED}
production_release: BLOCKED
marketplace_write_capability: DISABLED
real_commercial_data: NOT_ADMITTED
next_gate: B1_FINANCIAL_CONTRACTS_READINESS
```
