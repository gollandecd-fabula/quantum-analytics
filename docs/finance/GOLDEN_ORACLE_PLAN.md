# Financial Golden Calculation and Independent Oracle Plan v1

Status: `DRAFT_FOR_B1A_REVIEW`
Risk class: `R2`
Tracking issue: `#7`

## Purpose

This plan defines evidence required before B1b financial implementation may be
accepted. B1a does not implement formulas and does not approve any golden value.

## Separation of duties

- The calculation-kernel implementation actor cannot create or approve the final golden baseline.
- The oracle owner must independently derive expected values from approved contracts.
- A reviewer verifies expense boundaries, tax base, rounding, returns, and typed-state cases.
- Changes to either implementation or oracle invalidate the corresponding evidence until re-reviewed.

## Oracle form

The independent oracle may be:

- a small separately reviewed decimal reference implementation;
- a locked spreadsheet with disclosed formulas and checksums;
- a second implementation in a different execution path;
- manually derived fixtures with signed review evidence.

It cannot import or call the production calculation kernel.

## Required fixture dimensions

- Actual and Scenario modes;
- organization, marketplace account, product, product group, profile, and period scopes;
- fixed-value, rate, and safe-expression rules;
- priority, specificity, validity, version, tie, overlap, and missing-rule cases;
- zero, positive, negative, very small, and large decimal values;
- every approved rounding mode and application point;
- orders, sales, returns, payout, inventory, charges, product cost, other expense, and tax flows;
- operational, settlement, and tax-recognition views;
- return→restock→resale, write-off, loss, rejection, and compensation lifecycles;
- EMPTY, BLOCKED, UNAVAILABLE, CONFLICT, VALID, and valid zero;
- cross-currency blocked cases;
- late correction and restatement cases.

## Evidence per fixture

- fixture ID and semantic purpose;
- exact input events and source hashes;
- rule/profile/metric/rounding/source-authority versions and hashes;
- expected typed state and value;
- expected expense boundary and accounting view;
- expected intermediate values where contractually observable;
- independent derivation or oracle output;
- reviewer identity, timestamp, and approval reference;
- implementation comparison and tolerance, normally exact for decimal contract values.

## Required test classes

- golden examples;
- property-based invariants;
- differential comparison with the independent oracle;
- row-wise and aggregate reconciliation;
- mutation/replay determinism;
- no-double-count lifecycle tests;
- Actual/Scenario isolation;
- rule-resolution conflict and missing-data propagation;
- evidence reproduction.

## Approval gate

B1b cannot begin until:

- B1a schemas and contracts are merged;
- oracle owner and financial reviewer are identified;
- initial fixture matrix is independently approved;
- explicit user R3 approval is recorded.

No fixture in B1a is an approved financial golden baseline.
