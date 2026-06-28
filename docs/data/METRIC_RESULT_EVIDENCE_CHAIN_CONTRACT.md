# Metric Result Snapshot and Evidence Chain Contract v1

Status: `DRAFT_FOR_B3_REVIEW`
Risk class: `R2`
Tracking issue: `#16`
Pull Request: `#17`

## Purpose

Define an immutable, marketplace-neutral result snapshot and a reproducible Evidence
Chain without implementing the B1b financial calculation kernel. The contract records
what was calculated, which immutable versions and source facts were used, how evidence
integrity was evaluated, and why a recalculation created a new snapshot.

## Non-goals

- No calculation of commission, logistics, storage, advertising, cost, tax, allocation,
  other expense, margin, profit, or forecast.
- No activation of financial rules, rounding rules, Source Authority rows, or commercial defaults.
- No real or anonymized commercial marketplace data.
- No marketplace write operation, external authentication, hosting selection, or production release.
- No mutable replacement of an earlier published result.

## Result identity

Every snapshot records:

- `result_id`;
- result and Evidence Chain contract versions;
- organization and optional marketplace-account boundary;
- mode: `ACTUAL` or `SCENARIO`;
- explicit Scenario identifier only in Scenario mode;
- calculation instant and marketplace-neutral scope dimensions;
- immutable Calculation Profile and metric-definition references;
- canonical typed value;
- Evidence Chain;
- recalculation audit;
- `reproduction_hash` and `content_hash`.

`result_id` is `mr_` followed by the complete `content_hash`.

## Immutable version references

A version reference contains exactly:

- stable `id`;
- positive integer `version`;
- lowercase SHA-256 `content_hash`.

Metric results reference immutable Calculation Profile, metric definition, rounding
policy, normalization-rule, source-file, source-record, and canonical-event evidence.
A mutable latest-version pointer is not reproducible evidence.

## Two hashes

`reproduction_hash` covers semantic result material:

- tenant/account, mode and Scenario isolation;
- calculation instant and scope;
- immutable profile and metric-definition references;
- typed result value;
- complete Evidence Chain, including its input-set hash, freshness, confidence and validity metadata.

It excludes only recalculation actor/audit metadata.

`content_hash` covers the same semantic material plus the complete recalculation audit.
Changing actor, reason, calculated timestamp or predecessor therefore creates a new
immutable content identity without pretending that semantic calculation inputs changed.

Binary floating point, non-finite decimal values, ambient time, process-local state,
unordered sets and non-string JSON keys are forbidden hash inputs. Datetimes are
timezone-aware and normalized to UTC. Canonical JSON uses sorted keys, compact
separators, UTF-8 and a terminal line feed.

## Evidence Chain

For source-derived results the chain is:

```text
Metric Result
→ Calculation Profile Version
→ Metric Definition Version
→ Rounding Policy Version
→ Canonical Event Revisions
→ Normalization Rule Versions
→ Source Records
→ Import Batches / Source Files
→ Source File and Row SHA-256
```

Each source file, source record and canonical event repeats the organization and
marketplace-account boundary. Cross-tenant or cross-account references are rejected,
not retained as a readable fallback.

A source-derived result requires at least one source file, source record and canonical
event. A system-generated result contains no source references and must disclose an
explicit system-generated reason.

## Input-set integrity

`input_set_hash` is the canonical SHA-256 of sorted immutable references to:

- Calculation Profile;
- metric definition;
- rounding policy;
- source files/import batches;
- source records;
- canonical event revisions and normalization rules.

Duplicate file, record or event-revision references are invalid. A VERIFIED chain
requires every source record to resolve to a listed import batch and every event to
resolve to a listed source record.

## Typed value and state distribution

The result value follows the canonical typed-state contract:

- numeric zero is only a `VALID` value;
- every non-VALID state has `value = null` and a reason code;
- `VALID` requires non-null value and no reason code;
- a VALID result requires Evidence Chain validity `VERIFIED`.

The chain records included and excluded record counts plus all seven canonical
typed-state counts. Counts must be non-negative and reconcile to the complete referenced
source-record set.

## Freshness

Freshness is explicit:

- `CURRENT`: recorded age is not greater than the recorded threshold;
- `STALE`: recorded age exceeds the threshold;
- `UNKNOWN`: no data-through timestamp or threshold is invented.

Freshness evaluation uses recorded timestamps. Wall-clock time is not an implicit input.

## Confidence

Known confidence uses a decimal score from zero through one and at least one explicit
basis statement. `UNKNOWN` confidence has no fabricated score.

## Evidence validity

Validity metadata is separate from the business typed state:

- `VERIFIED`;
- `BROKEN_LINK`;
- `MISSING_VERSION`;
- `HASH_MISMATCH`;
- `CROSS_TENANT`;
- `UNVERIFIED`.

VERIFIED evidence has no diagnostics. Every non-verified status has explicit diagnostics.
A business result cannot be VALID when evidence validity is not VERIFIED.

Missing versions, cross-tenant references and hash mismatches fail closed. Broken-link
evidence may be preserved only with a non-VALID business result and explicit diagnostics.

## Recalculation audit

Every snapshot records actor, reason, timezone-aware calculation timestamp and trace ID.

`INITIAL` has no predecessor. Every other reason requires an immutable predecessor
result ID. Recalculation creates a new snapshot; it never mutates or deletes the previous
result.

Supported reasons are:

- source revision;
- profile change;
- metric-definition change;
- rounding-policy change;
- manual correction;
- restatement.

## Actual and Scenario isolation

Actual results require `scenario_id = null`. Scenario results require an explicit
Scenario identifier. Result identity, Evidence Chain and hashes include mode and
Scenario identifier, so Scenario evidence cannot overwrite or masquerade as Actual.

## Fail-closed rules

The following conditions block a VALID snapshot:

- missing required version or content hash;
- input-set hash mismatch;
- source record without its import batch;
- event without its source record;
- cross-tenant or cross-account reference;
- invalid record-count or typed-state reconciliation;
- non-verified evidence;
- non-timezone-aware audit or calculation timestamps;
- binary floating-point hash input;
- Actual/Scenario mismatch.

Independent results remain unaffected unless they depend on the invalid chain.

## Gate

B3 provides contracts, schemas, deterministic evidence utilities, fixtures, tests and
reviewable evidence only. B1b calculation implementation, rule activation, Source
Authority activation, real data admission, external access, deployment, marketplace
writes and production release remain blocked.
