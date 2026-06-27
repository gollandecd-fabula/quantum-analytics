# BUILD Acceptance Plan v1

Status: `ACTIVE_FOR_PLANNING`
Applies to: Macro-stage B — BUILD.
Stage contract: `STAGE-B-BUILD-v1`.
Tracking issue: `#5`.

| ID | Category | Acceptance test | Gate |
|---|---|---|---|
| BLD-001 | Governance | `CURRENT_STATE` references `STAGE-B-BUILD-v1` and the current executable unit | B0 |
| BLD-002 | Governance | Decision Ledger records explicit user approval to start Macro-stage B | B0 |
| BLD-003 | Governance | Every B unit has risk class, dependencies, outputs, tests, and approval gate | B0 |
| BLD-004 | Governance | R3/R4 work cannot start without explicit recorded approval | ALL |
| BLD-005 | Requirements | Every BUILD requirement traces to Issue, branch, PR, tests, and evidence | B8 |
| BLD-006 | Rules | No fixed cost, tax, tax-base, other-expense, allocation, or rounding constant exists in canonical logic | B1 |
| BLD-007 | Rules | Missing financial configuration blocks only dependent results and never substitutes zero | B1 |
| BLD-008 | Rules | Scope, validity, priority, exclusivity, version, and status resolve deterministically | B1 |
| BLD-009 | Rules | Overlapping or ambiguous active rules fail closed with typed diagnostics | B1 |
| BLD-010 | Rules | Safe expression contract rejects arbitrary code, unknown symbols, invalid types, cycles, and unsupported operators | B1 |
| BLD-011 | Finance | Monetary operations use decimal arithmetic only | B1 |
| BLD-012 | Finance | Intermediate and presentation rounding use an approved versioned policy | B1 |
| BLD-013 | Finance | Golden tests cover cost, tax, other expense, allocation, commission, logistics, storage, advertising, fines, and profit boundaries | B1 |
| BLD-014 | Finance | Property tests prove conservation, sign, monotonicity, and no-double-count invariants | B1 |
| BLD-015 | Finance | Differential tests match an independent oracle for approved fixtures | B1 |
| BLD-016 | Finance | Actual and Scenario rules/results remain isolated under read, write, export, and recalculation paths | B1/B6 |
| BLD-017 | Returns | Sale→return→restock→resale does not double charge or restore cost | B1/B2 |
| BLD-018 | Returns | Write-off, loss, rejection, and compensation lifecycles reconcile to approved semantics | B1/B2 |
| BLD-019 | Views | Operational, settlement, and tax-recognition views remain separate and explain timing differences | B2 |
| BLD-020 | Reconciliation | Row-wise reconciliation uses approved Source Authority and tolerance | B2 |
| BLD-021 | Reconciliation | Aggregate reconciliation equals the sum of accepted row results within explicit tolerance | B2 |
| BLD-022 | Reconciliation | Conflicts produce typed diagnostics and do not silently publish a valid result | B2 |
| BLD-023 | Periods | OPEN, PROVISIONAL, CLOSED, and RESTATED periods preserve immutable prior snapshots | B2 |
| BLD-024 | Evidence | Every metric snapshot links calculation profile, events, transformations, source records, source file, and SHA-256 | B3 |
| BLD-025 | Evidence | Recalculation records actor, timestamp, reason, rule versions, Product Master version, and rounding version | B3 |
| BLD-026 | Evidence | A verifier reproduces the metric from immutable evidence with no hidden inputs | B3 |
| BLD-027 | Reporting | Every report states accounting view, currency, unit, freshness, confidence, and confirmed expense boundary | B4 |
| BLD-028 | Reporting | Exports preserve typed states and Evidence Chain identifiers on round trip | B4 |
| BLD-029 | UI | Cost, tax rate, tax base, and other expense inputs have explicit scope and validity controls | B5 |
| BLD-030 | UI | EMPTY, BLOCKED, UNAVAILABLE, CONFLICT, VALID, and zero have distinct accessible rendering | B5 |
| BLD-031 | UI | Exception Inbox shows cause, affected metrics, evidence, and required resolution while independent metrics remain available | B5 |
| BLD-032 | UI | Critical-path E2E and accessibility checks pass for configuration, import status, report, and evidence drill-down | B5 |
| BLD-033 | Decision support | Recommendation cites evidence, assumptions, confidence, expected effect, limitations, and no-action alternative | B6 |
| BLD-034 | Decision support | Recommendation and scenario execution cannot mutate Actual results or marketplace state | B6 |
| BLD-035 | Security | Unauthenticated, unapproved, suspended, and revoked users are denied | B7 |
| BLD-036 | Security | Cross-tenant read/write attempts fail closed and are audit logged without leaking sensitive data | B7 |
| BLD-037 | Security | Session, CSRF, CSP, XSS, SQL-injection, file-abuse, secret, dependency, license, SBOM, and provenance checks pass | B7/B8 |
| BLD-038 | Deployment | Railway, Vercel, and Cloudflare comparison records free-tier limits, runtime fit, worker, database, storage, auth, backup, rollback, and observability | B7/B8 |
| BLD-039 | Operations | Technical health, data freshness, and calculation health are separate and retain last valid result when a new run is blocked | B8 |
| BLD-040 | Recovery | Backup, restore, retry, dead-letter, and rollback evidence passes for the selected BUILD architecture | B8 |
| BLD-041 | Review | Financial implementation actor does not approve its own golden baseline or R2+ change | ALL |
| BLD-042 | Release | BUILD Evidence Package lists immutable commit/artifact hashes, tests, approvals, limitations, and rollback evidence | B8 |
| BLD-043 | Release | BUILD completion does not start Macro-stage C or authorize production | B8 |

## Evidence rules

- A passing test without an immutable commit and artifact reference is insufficient.
- Mocks do not prove PostgreSQL transaction safety, durable object storage, tenant isolation, backup, restore, or platform limits.
- Golden baselines must be approved independently from calculation implementation.
- Financial results using synthetic data must be labeled synthetic and cannot activate Source Authority.
- Failing financial, security, reconciliation, or recovery tests block B8 closure.

## Test portfolio

### Fast pull-request checks

- schema and contract consistency;
- fixed-constant scan;
- deterministic decimal unit tests;
- typed-state serialization;
- rule resolution examples;
- Evidence Chain reference integrity.

### Targeted risk suites

- financial golden/property/differential tests;
- reconciliation and restatement tests;
- return lifecycle tests;
- tenant-isolation and authorization tests;
- file-abuse and injection tests;
- deployment limit and failure-mode tests.

### BUILD closure suite

- all fast and targeted tests;
- representative end-to-end flow;
- independent oracle comparison;
- security review;
- backup, restore, and rollback evidence;
- immutable BUILD Evidence Package verification.
