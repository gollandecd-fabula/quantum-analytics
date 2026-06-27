# Metric Snapshot Contract v1

Status: `DRAFT_FOR_B3_REVIEW`
Risk class: `R2`
Tracking: `[BUILD][B3] Define metric snapshots and Evidence Chain contracts`

## Purpose

A Metric Snapshot is an immutable, reproducible statement of one metric result
for one explicit tenant, scope, accounting view, period, mode, calculation
profile, and evidence set. A snapshot is never edited in place. Recalculation
creates a new snapshot linked to the prior result.

## Identity

Every snapshot contains:

- `metric_snapshot_id` — globally unique immutable identifier;
- `metric_id`, positive `metric_version`, and metric-definition content hash;
- `organization_id` — mandatory tenant boundary;
- optional `marketplace_account_id`, product, group, and profile scopes;
- `mode` — `ACTUAL` or `SCENARIO`;
- `scenario_id` — null for Actual and required for Scenario;
- explicit period start/end and accounting view;
- `calculated_at`, actor, reason, and trace identifier;
- positive snapshot revision;
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
`value: null`, a machine-readable reason code, limitations, and the evidence
needed to explain the state.

## Value metadata

Where applicable, the snapshot declares:

- decimal-string value or integer value;
- value type and unit;
- ISO 4217 currency;
- accounting view;
- confirmed expense boundary;
- rounding-policy ID, positive version, content hash, application point, mode,
  and resolved scale;
- source-authority ID, positive version, content hash, and approval status.

Cross-currency aggregation is `BLOCKED` unless a separately approved conversion
contract is referenced.

## Immutable references

Every reference uses a stable identifier, positive immutable version, and
SHA-256 content hash. Required references include:

- Calculation Profile;
- metric definition;
- rule-resolution results used by the metric;
- normalized canonical events;
- transformations;
- source records;
- source files and their SHA-256;
- rounding policy;
- Source Authority;
- Product Master version when relevant.

Aliases such as `latest`, mutable URLs, or unversioned names are forbidden.

## Freshness, confidence, and validity

A snapshot records:

- `data_freshness_state`: `CURRENT`, `STALE`, `UNKNOWN`, or `NOT_APPLICABLE`;
- `freshness_observed_at` and optional `freshness_deadline`;
- `confidence_state`: `HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`, or `NOT_APPLICABLE`;
- machine-readable confidence reasons;
- `valid_from` and optional `valid_to` for result applicability;
- limitations and unresolved conflicts.

Freshness and confidence never change the numeric value silently. A new
assessment produces a new snapshot or a separately versioned assessment record.

## Recalculation and restatement

Recalculation records:

- prior snapshot identifier;
- recalculation reason code;
- initiating actor;
- trigger timestamp and completion timestamp;
- changed event, rule, metric, rounding, Source Authority, Product Master, or
  transformation references;
- whether the prior period is OPEN, PROVISIONAL, CLOSED, or RESTATED.

Closed-period corrections create a restatement chain. History is never
rewritten.

## Actual and Scenario isolation

- Actual snapshots have `scenario_id: null` and cannot reference Scenario rules,
  profiles, or evidence nodes.
- Scenario snapshots require `scenario_id`; inherited Actual references are
  explicit and immutable.
- Scenario snapshots cannot supersede, restate, or publish as Actual snapshots.
- Identifiers and evidence graphs are namespaced by mode.

## Publishability

A snapshot is publishable only when:

- its metric definition permits the requested publication class;
- Calculation Profile references are complete and hash-valid;
- required Source Authority is approved;
- no unresolved evidence-link, tenant, mode, version, or hash conflict exists;
- required inputs are not BLOCKED, UNAVAILABLE, CONFLICT, or INVALID;
- an approved rounding policy is referenced;
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
