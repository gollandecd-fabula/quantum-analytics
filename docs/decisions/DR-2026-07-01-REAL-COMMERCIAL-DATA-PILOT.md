# Decision Record — Real Commercial Data in the Closed Pilot

Decision ID: `DR-2026-07-01-REAL-COMMERCIAL-DATA-PILOT`
Date: `2026-07-01`
Risk class: `R3`
Status: `APPROVED`
Owner decision: the Quantum pilot must operate on real commercial data.
Tracking issue: `#41`

## Decision

Real commercial marketplace data is mandatory for the July 8 closed pilot. Synthetic data remains
permitted for unit, fuzz, adversarial, and regression testing, but cannot by itself satisfy the pilot
acceptance gate.

At least one authorized organization dataset must complete the controlled path:

```text
DECLARED
→ QUARANTINED
→ VALIDATED
→ ADMITTED
→ INGESTED
→ CALCULATED
→ RECONCILED
→ PILOT_EVIDENCE_ACCEPTED
```

A dataset may instead transition to `REJECTED` or `REVOKED`. Failures are fail-closed.

## Boundaries

- Closed access only: invitation or approved request.
- Pseudonymous user accounts and minimized personal data.
- Marketplace interaction remains read-only.
- Marketplace write tokens, write methods, and execution buttons remain prohibited.
- Production release remains `RELEASE_BLOCKED`.
- Raw commercial data, credentials, secrets, and personal data are prohibited in GitHub, CI logs,
  model prompts, issue bodies, PR comments, test fixtures, screenshots, and evidence packages.
- External AI services may receive only sanitized, aggregated, or synthetic material unless a separate
  lawful data-processing decision explicitly authorizes otherwise.

## Required gate

Data is not admitted merely because the owner approved real-data use. Each dataset must pass the
Real Commercial Data Admission Contract, including authorization, classification, minimization,
encryption, tenant isolation, retention, deletion, recovery, and independent reconciliation controls.

## Consequences

- The pilot becomes an R3 financial and data-security exercise.
- Red, Blue, Purple, AppSec, IV&V, Financial QA, and Release Audit must test the real-data control path.
- `PILOT_READY` is impossible without end-to-end evidence from an admitted real dataset.
- A data leak, cross-tenant read, unencrypted storage, unapproved export, or unreconciled material
  financial difference is P0/P1 and blocks the pilot.
