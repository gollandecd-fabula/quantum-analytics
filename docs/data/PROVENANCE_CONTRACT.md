# Provenance Contract v1.0

Status: `APPROVED_WITHIN_STAGE_A4`
Risk class: `R3`

## Evidence Chain

```text
Metric Result
→ Calculation Profile Version
→ Canonical Events
→ Normalization Rule Versions
→ Source Records
→ Import Batch
→ Source File
→ SHA-256
```

## Required provenance fields

Every canonical event and derived result must reference:

- `import_batch_id`;
- `source_record_id`;
- `source_file_sha256`;
- `source_adapter`;
- `source_schema_id`;
- `normalization_rule_version`;
- `product_master_version`, when product identity is involved;
- `calculation_profile_version`, for derived financial outputs;
- `rounding_policy_version`, for monetary outputs;
- `actor`;
- `created_at`;
- `trace_id`;
- `reason_for_recalculation`, when replacing a previous result.

## Immutability rules

- Source file bytes are immutable.
- Source records are append-only.
- Canonical events are append-only.
- Published metric snapshots are immutable.
- Corrections create new versions and explicit links.
- Hash mismatches are release blockers.

## Minimum source record

A source record must preserve:

- stable row locator;
- raw row payload;
- normalized structural fingerprint;
- source file hash;
- adapter version;
- ingestion timestamp;
- validation status;
- quarantine reason, if any.

## Derived result requirements

A derived result must disclose:

- complete dependency set;
- included and excluded record counts;
- typed-state distribution;
- formula identifier and version;
- calculation profile and scope;
- freshness;
- confidence;
- limitations.
