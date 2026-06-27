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

Dependencies:

- FOUNDATION bootstrap merged into protected `main`;
- Issues #1 and #3 closed as completed;
- explicit user approval to start Macro-stage B;
- Constitution, Scope, decisions, requirements, risks, acceptance, and security baseline available.

Outputs:

- Stage Contract B;
- BUILD requirements snapshot;
- BUILD acceptance plan;
- machine-readable readiness evidence;
- synchronized Current State, Decision Ledger, and Risk Register.

Tests:

- documentation and traceability consistency;
- declared readiness-status vocabulary check;
- unit risk/dependency/output/test/gate completeness check;
- documentation-only diff check;
- existing Foundation CI remains green;
- separate Codex governance review has no unresolved findings.

Gate: no financial implementation is permitted in B0.

### B1 — Configurable financial rules and calculation kernel

#### B1a — Financial contracts and rule resolution

Risk: `R2`.

Dependencies:

- B0 merged and `STAGE-B-BUILD-v1` active;
- configuration-rule schema available as a draft input;
- Q-METRICS-001, rounding policy, typed states, Source Authority Matrix, and Scope available;
- protected Pull Request workflow and independent verifier available.

Outputs:

- typed rule vocabulary and scope contract;
- method and safe-expression contract;
- rule precedence, overlap, exclusivity, and double-count controls;
- versioned rounding and calculation-profile snapshot contracts;
- metric catalogue with explicit expense boundaries;
- golden-calculation specification and independent oracle plan.

Tests:

- valid and invalid rule-schema examples;
- deterministic precedence vectors;
- overlap, exclusivity, and ambiguity fixtures;
- dependency-cycle and unknown-symbol rejection;
- fixed-commercial-constant scan;
- safe-expression type/operator rejection;
- independent contract review.

#### B1b — Calculation kernel implementation

Risk: `R3`.

Dependencies:

- B1a contracts approved by an independent verifier;
- explicit user R3 approval;
- B3 metric-result and Evidence Chain contract available before publication;
- approved golden baseline and independent oracle owner assigned.

Outputs:

- decimal calculation kernel;
- typed blocked/unavailable/conflict results;
- Actual and Scenario isolation;
- approved golden, property, and differential tests.

Tests:

- golden calculations for approved metric catalogue;
- property tests for conservation, signs, monotonicity, and no-double-count invariants;
- differential tests against the independent oracle;
- decimal and versioned-rounding tests;
- typed-state propagation tests;
- Actual/Scenario isolation tests;
- mutation and replay determinism tests.

Gate: explicit user approval is required before B1b implementation or activation
of any cost, tax, allocation, other-expense, or rounding rule.

### B2 — Reconciliation, periods, and restatement

Risk: `R3`.

Dependencies:

- approved B1 contracts and calculation kernel;
- explicit user R3 approval;
- approved Source Authority rows and tolerance rules;
- canonical revision, reversal, supersession, and period contracts.

Outputs:

- row-wise and aggregate reconciliation;
- operational, settlement, and tax-recognition views;
- period states OPEN, PROVISIONAL, CLOSED, and RESTATED;
- source-authority conflict handling;
- impact reports for revisions, reversals, and late corrections.

Tests:

- row-wise and aggregate reconciliation fixtures;
- tolerance-boundary tests;
- operational/settlement/tax-view separation tests;
- late-correction and restatement golden paths;
- return, restock, resale, write-off, loss, and compensation lifecycle tests;
- conflict and unavailable-source fail-closed tests.

Gate: explicit user approval and approved B1 contracts are required.

### B3 — Metric snapshots and Evidence Chain

Risk: `R2`.

Dependencies:

- canonical event, provenance, typed-state, and idempotency contracts;
- B1a calculation-profile and rounding-version contracts;
- immutable source-file and source-record identifiers.

Outputs:

- immutable metric-result contract;
- calculation-profile version linkage;
- source-record and source-file traceability;
- freshness, confidence, and validity metadata;
- reproducible recalculation reason and actor audit.

Tests:

- end-to-end metric-to-file traceability;
- hash and version integrity tests;
- deterministic reproduction from recorded inputs;
- recalculation actor/reason/timestamp tests;
- stale, blocked, unavailable, and conflict evidence paths;
- broken-link and missing-version fail-closed tests.

### B4 — Reporting, API, and exports

Risk: `R2`.

Dependencies:

- stable metric catalogue and metric-result contract;
- B3 Evidence Chain identifiers;
- approved typed-state serialization;
- accounting-view and expense-boundary vocabulary.

Outputs:

- explicit operational, settlement, tax, and profitability reports;
- metric API contracts;
- export contracts that preserve typed states and provenance;
- confirmed expense-boundary labels.

Tests:

- API schema and backward-compatibility tests;
- report accounting-view and expense-boundary assertions;
- export/import round-trip preservation of typed states and evidence IDs;
- currency, unit, freshness, confidence, and rounding-version tests;
- pagination, empty-result, blocked-result, and large-export tests.

### B5 — UX, onboarding, and Exception Inbox

Risk: `R2`.

Dependencies:

- B1a rule-input and validation contracts;
- B3 evidence drill-down contract;
- B4 API/report contracts;
- security and accessibility baseline.

Outputs:

- configuration input flows for cost, tax, tax base, and other expenses;
- typed-state rendering without converting missing values to zero;
- exception and conflict resolution workflow;
- accessibility and critical-path tests.

Tests:

- critical-path end-to-end configuration and report flows;
- accessibility checks;
- typed-state visual and semantic snapshots;
- no-hidden-default input tests;
- Exception Inbox cause/evidence/resolution tests;
- independent-metric continuity when one calculation is blocked.

### B6 — Decision support and scenarios

Risk: `R3`.

Dependencies:

- approved B1 calculation kernel;
- approved B2 reconciliation results;
- B3 Evidence Chain and B4 report contracts;
- explicit user R3 approval;
- scenario/Actual isolation contract.

Outputs:

- explainable recommendations linked to evidence;
- scenario modelling isolated from Actual results;
- forecast assumptions and confidence ranges;
- no external action execution.

Tests:

- recommendation-to-evidence traceability;
- scenario isolation and non-mutation tests;
- confidence/limitation/no-action-alternative assertions;
- deterministic ranking under fixed inputs;
- unsupported-data and low-confidence suppression;
- marketplace-write capability absence tests.

Gate: explicit user approval is required before recommendation ranking or
financial forecast implementation.

### B7 — Identity, tenant isolation, and security controls

Risk: `R3` for externally accessible authentication and tenant isolation.

Dependencies:

- explicit user R3 approval for external access;
- threat model and data classification;
- B4/B5 externally exposed API and UX surfaces;
- deployment candidate architecture under Q-DEPLOY-001;
- secret-management and session design.

Outputs:

- approved-user-only access;
- session and account lifecycle controls;
- tenant-isolation enforcement and tests;
- file-abuse controls, privacy-safe logs, secrets, SBOM, and threat model;
- deployment-specific security controls for Railway, Vercel, or Cloudflare.

Tests:

- unauthenticated, unapproved, suspended, revoked, and expired-session denial;
- cross-tenant read/write isolation;
- CSRF, CSP, XSS, SQL-injection, and file-abuse tests;
- secret exposure and privacy-safe logging tests;
- dependency vulnerability, license, SBOM, and provenance checks;
- platform-specific quota and failure-mode security tests.

Gate: explicit user approval is required before external-access implementation.
Production credentials remain unavailable to implementation agents.

### B8 — Internal QA, security review, and BUILD evidence package

Risk: `R2`.

Dependencies:

- all required B1–B7 units completed or explicitly deferred with approved limitations;
- immutable evidence from financial, reconciliation, Evidence Chain, UI, security, and recovery suites;
- unresolved critical risks and conflicts enumerated;
- selected BUILD architecture and rollback boundary documented.

Outputs:

- targeted and full BUILD test portfolio;
- independent financial oracle evidence;
- security review and unresolved-risk report;
- rollback and recovery evidence available at the BUILD level;
- immutable BUILD Evidence Package;
- recommendation for transition to Macro-stage C without starting it.

Tests:

- complete fast, targeted-risk, and BUILD closure suites;
- independent oracle verification;
- full reconciliation and Evidence Chain integrity suite;
- security and tenant-isolation review;
- backup, restore, retry, dead-letter, and rollback evidence checks;
- immutable artifact/hash and approval verification;
- release-blocker and unresolved-risk consistency check.

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
  B0:
    risk: R1
    state: IN_PROGRESS
    dependencies: [FOUNDATION_MERGED, USER_APPROVAL]
    tests: [DOC_CONSISTENCY, STATUS_VOCABULARY, UNIT_COMPLETENESS, FOUNDATION_CI, CODEX_REVIEW]
  B1a:
    risk: R2
    state: PLANNED
    dependencies: [B0, CONFIG_RULE_SCHEMA, METRIC_REQUIREMENT, ROUNDING_DRAFT]
    tests: [RULE_SCHEMA, PRECEDENCE, OVERLAP, CYCLE_REJECTION, CONSTANT_SCAN, SAFE_EXPRESSION]
  B1b:
    risk: R3
    state: GATED
    dependencies: [B1A_APPROVED, USER_R3_APPROVAL, B3_CONTRACT, GOLDEN_ORACLE]
    tests: [GOLDEN, PROPERTY, DIFFERENTIAL, DECIMAL_ROUNDING, TYPED_STATE, SCENARIO_ISOLATION]
  B2:
    risk: R3
    state: GATED
    dependencies: [B1B, USER_R3_APPROVAL, SOURCE_AUTHORITY_APPROVED]
    tests: [ROW_RECONCILIATION, AGGREGATE_RECONCILIATION, VIEW_SEPARATION, RESTATEMENT, RETURN_LIFECYCLE]
  B3:
    risk: R2
    state: PLANNED
    dependencies: [CANONICAL_EVENTS, PROVENANCE, B1A_PROFILE_CONTRACT]
    tests: [TRACEABILITY, HASH_VERSION_INTEGRITY, REPRODUCTION, RECALCULATION_AUDIT, FAIL_CLOSED_LINKS]
  B4:
    risk: R2
    state: PLANNED
    dependencies: [METRIC_CATALOGUE, B3, TYPED_SERIALIZATION]
    tests: [API_CONTRACT, REPORT_BOUNDARY, EXPORT_ROUND_TRIP, METADATA, LARGE_EXPORT]
  B5:
    risk: R2
    state: PLANNED
    dependencies: [B1A_INPUTS, B3, B4, ACCESSIBILITY_BASELINE]
    tests: [CRITICAL_E2E, ACCESSIBILITY, TYPED_STATE_SNAPSHOTS, NO_HIDDEN_DEFAULTS, EXCEPTION_INBOX]
  B6:
    risk: R3
    state: GATED
    dependencies: [B1B, B2, B3, B4, USER_R3_APPROVAL]
    tests: [RECOMMENDATION_EVIDENCE, SCENARIO_ISOLATION, CONFIDENCE, DETERMINISM, NO_EXTERNAL_ACTION]
  B7:
    risk: R3
    state: GATED
    dependencies: [USER_R3_APPROVAL, THREAT_MODEL, B4, B5, DEPLOYMENT_CANDIDATE]
    tests: [AUTHORIZATION, TENANT_ISOLATION, WEB_CONTROLS, FILE_ABUSE, SECRET_LOGGING, SBOM]
  B8:
    risk: R2
    state: PLANNED
    dependencies: [B1_TO_B7_EVIDENCE, RISK_REPORT, ROLLBACK_BOUNDARY]
    tests: [FULL_BUILD_SUITE, ORACLE, SECURITY_REVIEW, RECOVERY, ARTIFACT_HASH, BLOCKER_CONSISTENCY]
production_release: BLOCKED
marketplace_write_capability: DISABLED
real_commercial_data: NOT_ADMITTED
next_gate: B1_FINANCIAL_CONTRACTS_READINESS
```
