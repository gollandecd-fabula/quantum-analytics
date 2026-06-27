# BUILD Requirements Snapshot v1

Status: `ACTIVE_FOR_PLANNING`
Applies to: Macro-stage B — BUILD.
Stage contract: `STAGE-B-BUILD-v1`.
Tracking issue: `#5`.

## Authority and interpretation

This snapshot refines Constitution v3.0, active user decisions, Scope, and existing
requirements. It does not activate any financial rule or Source Authority row.
Where a requirement conflicts with a later explicit user decision, the later
user decision has priority and the conflict must be recorded.

## Requirements

| ID | Priority | Risk | Requirement | Primary acceptance |
|---|---|---:|---|---|
| Q-BLD-001 | MUST | R2 | The canonical core remains marketplace-neutral, category-neutral, brand-neutral, and currency-aware. | The calculation domain has no Wildberries-, apparel-, size-, or brand-specific constants. |
| Q-BLD-002 | MUST | R3 | Cost, tax rate, tax base, other expenses, allocation, and rounding are user-supplied or imported as versioned scoped rules. | No default commercial value is activated; missing required rules block only dependent results. |
| Q-BLD-003 | MUST | R3 | Rule resolution is deterministic across scope, validity period, priority, exclusivity group, version, and status. | Overlap, ambiguity, and double-count cases fail closed with typed diagnostics. |
| Q-BLD-004 | MUST | R3 | Complex expressions use a typed declarative DSL with an allowlisted operator set and no arbitrary code execution. | Invalid types, unknown variables, cycles, and unsafe operations are rejected before publication. |
| Q-BLD-005 | MUST | R3 | Monetary calculations use decimal arithmetic and an approved versioned rounding policy. | Golden and differential tests prove intermediate and presentation rounding are separate. |
| Q-BLD-006 | MUST | R2 | Metrics distinguish orders, sales, purchases, returns, charges, payouts, discounts, subsidies, commissions, logistics, storage, advertising, fines, cost, other expenses, taxes, profit, profit per unit, and profitability. | Every metric declares accounting view, expense boundary, source authority, freshness, confidence, and Evidence Chain. |
| Q-BLD-007 | MUST | R2 | `EMPTY`, `BLOCKED`, `UNAVAILABLE`, `CONFLICT`, `VALID`, and numeric `0` remain distinct throughout domain, API, reports, exports, and UI. | Serialization and UI snapshot tests prove that missing states never become zero. |
| Q-BLD-008 | MUST | R3 | Operational, settlement, and tax-recognition views are calculated and reported separately. | Cross-view reconciliation explains timing differences and prevents silent mixing. |
| Q-BLD-009 | MUST | R3 | Return, revision, reversal, restatement, restock, write-off, loss, and compensation flows prevent double counting of value and cost. | Lifecycle golden tests cover resale, write-off, loss, and compensation paths. |
| Q-BLD-010 | MUST | R3 | Reconciliation runs row-wise and aggregate-wise against approved Source Authority and tolerance rules. | Every mismatch produces a typed reconciliation result and traceable diagnostic. |
| Q-BLD-011 | MUST | R2 | Every published metric is an immutable snapshot linked to calculation profile, normalized events, transformations, source records, source file, and SHA-256. | A verifier can reproduce the result from recorded versions and inputs. |
| Q-BLD-012 | MUST | R3 | Actual and Scenario data, rules, results, and exports are isolated. | Scenario execution cannot mutate or replace Actual snapshots. |
| Q-BLD-013 | MUST | R2 | Reports and exports preserve typed states, accounting view, currency, units, rounding version, and confirmed expense boundary. | Export round-trip tests preserve semantics and provenance identifiers. |
| Q-BLD-014 | MUST | R2 | The user interface provides explicit inputs for cost, tax rate, tax base, and other expenses at supported scopes and validity periods. | No financial field is prefilled with an unstated business assumption. |
| Q-BLD-015 | SHOULD | R2 | Exception Inbox exposes blocked, unavailable, conflict, schema, reconciliation, and configuration problems without suppressing independent results. | A user can identify cause, affected metrics, evidence, and required resolution. |
| Q-BLD-016 | MUST | R3 | Decision support is explainable, evidence-linked, confidence-aware, and read-only. | Recommendations show assumptions, expected effect, limitations, and cannot execute marketplace actions. |
| Q-BLD-017 | MUST | R3 | External application access is limited to registered and explicitly approved users with tenant isolation and revocation. | Unauthorized and cross-tenant access tests fail closed. |
| Q-BLD-018 | MUST | R2 | Final hosting is restricted to Railway, Vercel, or Cloudflare and requires documented free-tier feasibility. | Comparative staging proof covers runtime, worker, database, storage, auth, limits, backup, rollback, and observability. |
| Q-BLD-019 | MUST | R2 | Financial changes require golden, property-based, differential, reconciliation, and independent-oracle evidence. | The calculation author cannot approve the corresponding golden baseline. |
| Q-BLD-020 | MUST | R4 | Production release and any marketplace write capability require separate explicit approval and release evidence. | BUILD merge cannot be interpreted as production authorization. |

## Rule lifecycle requirements

A rule progresses through:

```text
DRAFT → SHADOW → PILOT → ACTIVE → SUSPENDED → RETIRED
```

Before `ACTIVE`, the system must perform:

- schema and semantic validation;
- scope and validity checks;
- overlap and exclusivity checks;
- dependency-cycle checks;
- double-count checks;
- preview impact;
- golden calculation;
- immutable versioned snapshot;
- independent verification.

No automatic fallback may supply a missing cost, tax rate, tax base, other
expense, allocation rule, or rounding policy.

## Metric-result minimum contract

Every result must contain or reference:

- metric identifier and semantic version;
- organization and marketplace-account scope;
- period and accounting view;
- typed state and optional numeric value;
- currency and unit where applicable;
- calculation-profile version;
- rounding-policy version;
- source-authority version;
- freshness, confidence, and validity;
- normalized event identifiers;
- source-record and source-file identifiers;
- trace identifier, actor, timestamps, and recalculation reason;
- limitations and confirmed expense boundary.

## BUILD sequencing constraints

- B1a contracts precede B1b implementation.
- B1b precedes B2 reconciliation and B6 decision support.
- B3 Evidence Chain contract must be available before publishing any B1 result.
- B7 access controls must pass before any externally accessible deployment.
- B8 cannot close while any critical financial, security, or recovery test fails.

## Current implementation gates

- `Q-METRICS-001` remains `NOT_APPROVED_FOR_IMPLEMENTATION`.
- `ROUNDING_POLICY.md` remains `DRAFT`.
- Source Authority rows remain `DRAFT`.
- Real Wildberries schemas remain unverified.
- B1b, B2, B6, and B7 require explicit R3 approval.
- Production release remains `RELEASE_BLOCKED`.
