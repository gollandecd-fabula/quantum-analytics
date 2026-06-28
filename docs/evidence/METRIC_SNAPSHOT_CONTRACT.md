# Metric Snapshot Contract v1

Status: `DRAFT_FOR_B3_REVIEW`
Risk class: `R2`
Tracking issue: `#9`

## Purpose

A Metric Snapshot is an immutable, reproducible statement of one metric result
for one explicit tenant, scope, accounting view, period, mode, Calculation
Profile, and evidence set. A snapshot is never edited in place. Recalculation
creates a new snapshot linked to the prior result.

## Identity

Every snapshot contains:

- `metric_snapshot_id`, positive `snapshot_revision`, and content SHA-256;
- `metric_definition_ref` with positive immutable version and hash;
- `calculation_profile_ref` with positive immutable version and hash;
- mandatory `organization_id` and optional marketplace-account scope;
- `mode` — `ACTUAL` or `SCENARIO`;
- `scenario_id` — null for Actual and required for Scenario;
- explicit period start/end and accounting view;
- calculation timestamp, actor, reason, and trace identifier;
- optional prior-snapshot and restatement references.

## Result state

The state vocabulary is exactly the canonical Stage A4 set:

- `VALID`;
- `EMPTY`;
- `BLOCKED`;
- `UNAVAILABLE`;
- `CONFLICT`;
- `INVALID`;
- `NOT_APPLICABLE`.

Numeric zero is a valid payload of `VALID`; it is not a separate state.

A `VALID` snapshot contains a typed value. Every non-VALID snapshot contains
`value: null`, a machine-readable reason code, limitations, and evidence needed
to explain the state.

## Value metadata

Where applicable, the snapshot declares:

- normalized decimal-string or integer value;
- value type and unit, including `MONEY_PER_ITEM` where defined by B1a;
- ISO 4217 currency;
- accounting view and confirmed expense boundary;
- rounding-policy reference, application point, mode, and resolved scale;
- approved Source Authority reference;
- Evidence Chain reference.

Cross-currency aggregation is `BLOCKED` unless a separately approved conversion
contract is referenced.

## Immutable references

Every reference uses a stable identifier, positive immutable version, and
SHA-256 content hash. Required evidence includes:

- Calculation Profile;
- Metric Definition;
- Rule Resolution results and selected Configuration Rules;
- normalized Canonical Events;
- Transformations;
- Source Records;
- source files and their SHA-256;
- Rounding Policy;
- Source Authority;
- Product Master version when relevant.

Aliases such as `latest`, mutable URLs, or unversioned names are forbidden.

## Freshness, confidence, and validity

A snapshot records:

- `data_freshness_state`: `CURRENT`, `STALE`, `UNKNOWN`, or `NOT_APPLICABLE`;
- freshness observation and optional deadline;
- `confidence_state`: `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`, or `NOT_APPLICABLE`;
- machine-readable confidence reasons;
- applicability interval;
- limitations and unresolved conflicts.

Freshness and confidence never change a numeric value silently. A changed
assessment creates a new snapshot or separately versioned assessment.

## Recalculation and restatement

Recalculation records:

- prior snapshot identifier;
- recalculation reason;
- initiating actor;
- trigger and completion timestamps;
- changed event, rule, metric, rounding, Source Authority, Product Master, or
  Transformation references;
- whether the prior period is OPEN, PROVISIONAL, CLOSED, or RESTATED.

Closed-period corrections create a restatement chain. History is never
rewritten.

## Actual and Scenario isolation

- Actual snapshots have `scenario_id: null` and cannot reference Scenario rules,
  profiles, or evidence nodes.
- Scenario snapshots require `scenario_id`; inherited Actual references are
  explicit and immutable.
- Scenario snapshots cannot supersede, restate, or publish as Actual snapshots.
- Identifiers and Evidence Chains are namespaced by mode.

## Publishability

A snapshot is publishable only when:

- its Metric Definition permits the requested publication class;
- Calculation Profile references are complete and hash-valid;
- required Source Authority is approved;
- no unresolved evidence-link, tenant, mode, version, or hash conflict exists;
- required inputs are not BLOCKED, UNAVAILABLE, CONFLICT, or INVALID;
- an approved Rounding Policy is referenced;
- the Evidence Chain is complete and reproducible.

B3 defines the contract only. No financial snapshot is calculated or published.

## Diagnostics

- `METRIC_DEFINITION_MISSING`;
- `METRIC_PROFILE_MISSING`;
- `METRIC_REQUIRED_INPUT_MISSING`;
- `METRIC_EVIDENCE_INCOMPLETE`;
- `METRIC_REFERENCE_HASH_MISMATCH`;
- `METRIC_REFERENCE_VERSION_INVALID`;
- `METRIC_TENANT_MISMATCH`;
- `METRIC_MODE_CONTAMINATION`;
- `METRIC_ROUNDING_UNAPPROVED`;
- `METRIC_SOURCE_AUTHORITY_UNAPPROVED`;
- `METRIC_CURRENCY_CONFLICT`;
- `METRIC_RESTATEMENT_CHAIN_INVALID`;
- `METRIC_PUBLICATION_BLOCKED`.
