# Reporting, API, and Export Contract v1

Status: `IMPLEMENTED_FOR_P1_4_REVIEW`
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
- confirmed expense boundary and rounding metadata;
- freshness, confidence, limitations, and Evidence Chain identity/version;
- generation timestamp and explicit publication state.

Numeric zero remains a `VALID` payload. `EMPTY`, `BLOCKED`, `UNAVAILABLE`,
`CONFLICT`, `INVALID`, and `NOT_APPLICABLE` use `value: null` and a
machine-readable reason code.

## Publication state

`PREVIEW_ONLY` is the default when no complete Evidence Chain is supplied.
The record adds `EVIDENCE_NOT_VERIFIED_FOR_PUBLICATION` to its limitations.

`EVIDENCE_VERIFIED` is allowed only when the existing B3 runtime verifier
accepts the supplied Evidence Chain and its tenant, mode, scenario, identifier,
and version match the Metric Snapshot.

This state does not authorize production release. `RELEASE_BLOCKED` remains in
force.

## API pagination

The runtime returns bounded pages with a maximum size of 100. A cursor contains
an offset and a digest of the ordered result identity. Reusing a cursor after
records or order change fails closed.

## Export formats

- canonical JSON export bundle with deterministic SHA-256;
- JSON Lines records;
- CSV with explicit reporting columns and a canonical JSON record payload.

CSV import verifies that projected columns match the canonical record. JSON,
JSONL, and CSV round trips preserve typed states, Evidence Chain identifiers,
currency, units, expense boundary, rounding, freshness, confidence, and
limitations.

## Isolation and limits

One export bundle may contain only one organization and one Actual/Scenario
namespace. Cross-tenant and Actual/Scenario mixtures fail closed.

Limits:

- maximum page size: 100 records;
- maximum export bundle: 10,000 records;
- maximum serialized export payload: 10,000,000 bytes.

## Diagnostics

- `REPORT_SNAPSHOT_INVALID`
- `REPORT_EVIDENCE_INVALID`
- `REPORT_EVIDENCE_BINDING_MISMATCH`
- `REPORT_MODE_CONTAMINATION`
- `REPORT_STATE_VALUE_MISMATCH`
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
