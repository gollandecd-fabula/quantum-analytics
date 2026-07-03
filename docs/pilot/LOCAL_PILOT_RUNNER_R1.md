# LOCAL_PILOT_RUNNER_R1

## Status

Internal loopback-only pilot runner. It does not assert `PILOT_READY`, does not deploy, and does not enable marketplace writes.

## Pipeline

```text
LOCAL FILE
→ IMMUTABLE RECEIPT
→ TENANT-SCOPED RAW STORAGE
→ QUARANTINE ZONE
→ DECLARED
→ VALIDATED OR REJECTED
→ ADMITTED
→ ADMITTED ZONE
→ FINANCIAL CALCULATION
→ RECONCILED | CONFLICT | PENDING
→ LOCAL JSON REPORT
```

Only an `ADMITTED` dataset reaches the financial kernel. Unknown schemas, prohibited headers, malformed XLSX packages, incomplete attestations, tenant mismatches and reconciliation differences fail closed.

## Local boundaries

- Run only on a project-owner-controlled computer.
- Bind any supporting API only to `127.0.0.1`.
- Do not expose the storage root through LAN, cloud sync, shared folders, removable media or public backup.
- Do not put real reports, configuration with commercial values, output reports or storage directories in GitHub.
- Do not send raw report data to external AI services.
- Use pseudonymous tenant, account and verifier identifiers.
- The verifier identifier must differ from the operator identifier.
- Marketplace write credentials and write operations are prohibited.

## Required files

1. Authorized XLSX or ZIP-XLSX report.
2. Local JSON configuration containing:
   - tenant/account/verifier identifiers;
   - report period and authority reference;
   - retention deadline;
   - approved XLSX schema and limits;
   - malware-scan evidence hash;
   - explicit control attestations;
   - explicit financial request with cost, tax and other-expense values;
   - optional expected aggregate metrics for reconciliation.

## Command

The repository build backend is intentionally disabled. Run directly from the source tree:

```powershell
$env:PYTHONPATH = "src"
python -m quantum.pilot.local_runner `
  --file "C:\QuantumPilot\input\report.xlsx" `
  --config "C:\QuantumPilot\config\pilot.json" `
  --storage-root "C:\QuantumPilot\data" `
  --output "C:\QuantumPilot\output\pilot-report.json"
```

Do not bind the input, storage or output directories to Git synchronization.

## Result statuses

- `PILOT_RUN_COMPLETE`: admitted, calculated and all configured expected metrics matched.
- `CALCULATED_RECONCILIATION_PENDING`: admitted and calculated, but expected metrics were not supplied.
- `RECONCILIATION_CONFLICT`: at least one expected aggregate differs.
- `CALCULATION_BLOCKED`: a required finance metric is non-valid.
- `ADMISSION_REJECTED`: file or schema validation failed; calculation was not executed.
- `ERROR`: malformed configuration, missing authority/evidence, tenant mismatch or another fail-closed error.

## Configuration skeleton

All hashes below are placeholders and must be replaced with independently obtained values.

```json
{
  "tenant_id": "tenant-local-pilot",
  "account_id": "operator-local",
  "verifier_account_id": "verifier-local",
  "source_internal_id": "wb-report-2026-07",
  "marketplace": "WILDBERRIES",
  "report_type": "SALES_REPORT",
  "reporting_period_start": "2026-07-01",
  "reporting_period_end": "2026-07-31",
  "timezone": "Europe/Moscow",
  "expected_row_count": 1,
  "control_totals_sha256": null,
  "data_categories": ["FINANCIAL", "SALES"],
  "owner_authority_reference": "OWNER-LOCAL-PILOT-1",
  "lawful_authority_attested": true,
  "retention_deadline": "2026-08-31T00:00:00Z",
  "malware_scan_evidence_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
  "attestations": {
    "source_authority_verified": true,
    "report_period_verified": true,
    "control_totals_verified": true,
    "direct_identifiers_absent_or_approved": true,
    "malware_scan_clean": true
  },
  "inspection_policy": {
    "policy_id": "wb-sales-local-pilot",
    "version": 1,
    "limits": {
      "max_file_bytes": 104857600,
      "max_archive_entries": 10000,
      "max_total_uncompressed_bytes": 536870912,
      "max_entry_uncompressed_bytes": 134217728,
      "max_compression_ratio": 100,
      "max_xml_bytes": 134217728,
      "max_rows": 1000000,
      "max_columns": 500
    },
    "schemas": [
      {
        "schema_id": "WB_SALES",
        "schema_version": "1",
        "schema_authority_reference": "APPROVED-WB-SCHEMA-1",
        "direct_identifiers_expected": false,
        "package_kind": "XLSX",
        "sheet_name": "Sheet1",
        "sheet_count": 1,
        "header_row_index": 1,
        "header_sha256": "0000000000000000000000000000000000000000000000000000000000000000",
        "column_count": 1,
        "min_data_rows": 1,
        "max_data_rows": 1000000,
        "max_formula_count": 0
      }
    ],
    "prohibited_header_tokens": ["phone", "email", "address", "passport"]
  },
  "finance_request": {
    "replace_with_a_valid_versioned_finance_request": true
  },
  "reconciliation": {
    "expected_metrics": {
      "net_profit_amount": "0.00"
    }
  }
}
```

## Deliberate limitations

R1 does not provide durable authentication, database-backed session state, durable queueing, backup/restore verification, automated deletion rehearsal, report-row extraction into finance inputs, or independent release audit. Therefore even `PILOT_RUN_COMPLETE` is a successful local run, not a declaration of full `PILOT_READY`.
