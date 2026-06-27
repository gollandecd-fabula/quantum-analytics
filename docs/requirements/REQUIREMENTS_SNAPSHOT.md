# Requirements Snapshot

## P0 correctness and governance

- Latest explicit user decision has highest project authority.
- All uploaded files are untrusted data.
- Original files are retained with SHA-256.
- Unknown or changed schemas are quarantined.
- Imports are idempotent.
- The core is category-neutral and marketplace-neutral.
- Cost, tax, tax base, and other expenses are configurable and versioned.
- Monetary arithmetic uses decimal types.
- Published snapshots are not silently overwritten.
- Return and reversal accounting prevents double counting.
- Every metric supports an Evidence Chain.
- Operational, settlement, and tax-recognition views are separate.
- Actual and Scenario data are separate.
- Secrets and commercial data are excluded from GitHub.
- Financial logic requires independent verification.

## Typed-state contract

`EMPTY`, `BLOCKED`, `UNAVAILABLE`, `CONFLICT`, `VALID`, and numeric `0`
are semantically distinct states.

## Release blockers

Release remains blocked for double counting, unknown operations, hidden substitutions,
unconfirmed financial formulas, missing evidence, non-idempotent import, rewritten history,
failed financial/security/recovery tests, write integrations, open SEV-1 incidents,
autonomy-policy violations, or missing production approval.
