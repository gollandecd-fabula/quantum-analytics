# Reporting, API, and Export Contract v1

Status: `REMEDIATED_FOR_P1_4_REVIEW`
Risk class: `R2`
Stage unit: `B4 — Reporting, API, and exports`

## Purpose

P1.4 exposes immutable B3 Metric Snapshots as read-only report records and
portable export bundles. It does not calculate a metric, approve a financial
rule, activate Source Authority, or authorize production publication.

## Report record

Every report record preserves:

- tenant, marketplace-account, Actual/Scenario namespace, and accounting view;
- Metric Snapshot identity, revision, and content SHA-256;
- typed state, value, value type, unit, currency, and reason code;
- confirmed expense boundary and exact rounding-policy resolution;
- freshness, confidence, limitations, and Evidence Chain identity/version;
- Evidence Chain content SHA-256 for evidence-verified records;
- generation timestamp, publication state, and deterministic record SHA-256.

The record hash covers every report field except the hash field itself. JSONL
and CSV import reject altered report metadata even when the referenced Metric
Snapshot hash remains unchanged.

Numeric zero remains a `VALID` payload. `EMPTY`, `BLOCKED`, `UNAVAILABLE`,
`CONFLICT`, `INVALID`, and `NOT_APPLICABLE` use `value: null` and a
machine-readable reason code.

Value validation is fail-closed:

- `MONEY` uses a normalized decimal string, money unit, and three-letter currency;
- `INTEGER` uses a JSON integer and cannot use money units or currency;
- `DECIMAL` and `RATE` use normalized decimal strings without money units;
- expense boundaries, rounding, freshness, and confidence use closed vocabularies
  and exact nested shapes.

## Publication state

`PREVIEW_ONLY` is the default when no complete Evidence Chain is supplied.
The record has no Evidence Chain content hash and includes
`EVIDENCE_NOT_VERIFIED_FOR_PUBLICATION` in its limitations.

`EVIDENCE_VERIFIED` is allowed only when the existing B3 runtime verifier
accepts the supplied Evidence Chain and all of the following match the Metric
Snapshot:

- Evidence Chain identifier and version;
- tenant, mode, and scenario namespace;
- root Metric Snapshot identifier, revision, and content SHA-256.

The exact Evidence Chain content SHA-256 is stored in the report record. This
state does not authorize production release. `RELEASE_BLOCKED` remains in force.

## API pagination

The runtime returns bounded pages with a maximum size of 100. A cursor contains
an offset and a digest of the complete ordered report records. Reusing a cursor
after any record content or order change fails closed. Duplicate report-record
identifiers are forbidden.

## Export formats

- canonical JSON export bundle with deterministic SHA-256;
- JSON Lines records with per-record SHA-256 validation;
- CSV with explicit reporting columns and a canonical JSON record payload.

CSV projected cells that could be interpreted as spreadsheet formulas are
neutralized with a leading apostrophe. Import recomputes the safe projection and
rejects any mismatch. The canonical JSON record remains the round-trip source of
truth.

JSON, JSONL, and CSV round trips preserve typed states, record hashes, Evidence
Chain identifiers and content hashes, currency, units, expense boundary,
rounding, freshness, confidence, and limitations.

## Isolation and limits

One export bundle may contain only one organization and one Actual/Scenario
namespace. Cross-tenant, Actual/Scenario, and duplicate-record mixtures fail
closed.

Limits:

- maximum page size: 100 records;
- maximum export bundle: 10,000 records;
- maximum serialized export payload: 10,000,000 bytes.

## Diagnostics

- `REPORT_SNAPSHOT_INVALID`
- `REPORT_EVIDENCE_INVALID`
- `REPORT_EVIDENCE_BINDING_MISMATCH`
- `REPORT_PUBLICATION_STATE_INVALID`
- `REPORT_RECORD_HASH_MISMATCH`
- `REPORT_VALUE_INVALID`
- `REPORT_ROUNDING_INVALID`
- `REPORT_FRESHNESS_INVALID`
- `REPORT_CONFIDENCE_INVALID`
- `REPORT_EXPENSE_BOUNDARY_INVALID`
- `EXPORT_RECORD_DUPLICATE`
- `EXPORT_TENANT_MIXED`
- `EXPORT_MODE_MIXED`
- `EXPORT_HASH_MISMATCH`
- `EXPORT_CSV_PROJECTION_MISMATCH`
- `REPORT_CURSOR_INVALID`
- `EXPORT_RECORD_LIMIT_EXCEEDED`
- `EXPORT_BYTE_LIMIT_EXCEEDED`

## Exclusions

- financial formula implementation;
- real marketplace data admission;
- Source Authority activation;
- external HTTP service or authentication;
- UI;
- database persistence;
- production deployment;
- marketplace write operations.
