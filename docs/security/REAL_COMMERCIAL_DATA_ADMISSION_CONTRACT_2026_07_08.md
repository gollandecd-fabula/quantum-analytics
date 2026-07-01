# Real Commercial Data Admission Contract — July 8 Closed Pilot

Contract ID: `REAL-DATA-ADMISSION-2026-07-08-v1`
Authority: `DR-2026-07-01-REAL-COMMERCIAL-DATA-PILOT`
Risk class: `R3`
Applies to: every real commercial dataset entering the Quantum closed pilot
Production status: `RELEASE_BLOCKED`

## 1. Admission state machine

```text
DECLARED → QUARANTINED → VALIDATED → ADMITTED
     └──────────────→ REJECTED
ADMITTED → REVOKED
```

Only `ADMITTED` data may be used for pilot calculations. `QUARANTINED`, `REJECTED`, and `REVOKED`
data must be excluded from calculations and user-visible recommendations.

## 2. Required declaration

Each dataset receives an immutable admission record containing:

- organization and tenant identifier;
- dataset owner or authorized uploader;
- source marketplace and report type;
- reporting period and timezone;
- file name represented only by a safe internal identifier where possible;
- SHA-256 of the original file;
- data categories and sensitivity classification;
- expected row count and control totals when available;
- lawful or contractual authority attestation;
- retention and deletion deadline;
- admission actor, timestamp, decision, and reason.

## 3. Prohibited material

Unless strictly required and separately approved, ingestion must reject or strip:

- customer names, phone numbers, email addresses, delivery addresses, and government identifiers;
- payment-card data and authentication secrets;
- marketplace API write tokens;
- session cookies and access tokens;
- unrelated employee or counterparty personal data;
- executable files, macros, embedded scripts, and active content.

## 4. Storage and transport controls

- TLS for transport.
- Encryption at rest for raw, normalized, backup, and evidence storage.
- Tenant-scoped object paths and database ownership fields.
- No public buckets or unauthenticated object URLs.
- Short-lived credentials and least privilege.
- Separate raw, quarantine, admitted, derived, and backup zones.
- Original file preserved immutably with SHA-256; derived records link to source without exposing raw values.
- Production credentials remain unavailable to implementation agents.

## 5. Validation gate

Before `ADMITTED`, the system must verify:

1. file type, encoding, delimiter, dates, timezone, and structural fingerprint;
2. schema and semantic fingerprint;
3. required fields and typed-state semantics;
4. row limits, file-size limits, decompression limits, and parser timeouts;
5. duplicate, replay, idempotency, revision, reversal, and supersession behavior;
6. organization and tenant ownership;
7. absence or approved handling of direct identifiers;
8. source authority and report-period compatibility;
9. control totals where available;
10. malware/active-content rejection appropriate to the file type.

Any unknown schema or semantic drift remains in `QUARANTINED` and creates a diagnostic issue without
copying commercial values into GitHub.

## 6. Calculation and reconciliation gate

For each admitted real dataset:

- row-level lineage must reach the original SHA-256;
- aggregate control totals must be compared with the source report;
- financial calculations must use versioned Decimal and rounding rules;
- missing, blocked, unavailable, conflict, valid, and numeric zero remain distinct;
- Actual and Scenario remain physically and logically separated;
- returns, reversals, corrections, taxes, costs, logistics, storage, advertising, fines, and other expenses
  must be checked for double counting;
- material differences produce `CONFLICT` or `BLOCKED`, never silent acceptance.

Tolerance values are versioned configuration, not hardcoded constants.

## 7. Access and tenant isolation

- Every raw and derived read requires authenticated tenant context.
- Object identifiers alone never grant access.
- Cross-tenant access attempts fail closed and create privacy-safe security events.
- Administrative access is time-limited, attributable, and logged.
- Export and download are disabled unless separately required and approved for the pilot.
- Testers see only their organization data and explicitly shared aggregate diagnostics.

## 8. Logging and AI-processing restrictions

Logs and evidence may contain hashes, safe identifiers, counts, typed states, rule versions, and error
codes. They must not contain raw rows, direct identifiers, secrets, full commercial reports, or unrestricted
financial payloads.

Raw real commercial data must not be sent to OpenAI, DeepSeek, or another external model. Model-assisted
analysis uses synthetic fixtures, redacted samples, schemas, aggregates, or locally generated evidence.

## 9. Retention, deletion, and revocation

- Each dataset has an explicit retention deadline.
- The organization may withdraw permission or request deletion.
- Revocation immediately blocks new processing and user access.
- Deletion covers raw, normalized, derived, cached, and queued copies.
- Backups use documented expiry or cryptographic erasure consistent with the deletion policy.
- A deletion verification record contains identifiers and hashes, not deleted commercial values.

## 10. Backup, recovery, and incidents

- Restore tests must preserve tenant boundaries and admission status.
- A restored `REVOKED` dataset must remain revoked.
- Security incidents trigger containment, credential/session revocation, evidence preservation, and owner notification workflow.
- Suspected cross-tenant exposure is P0 until disproved.

## 11. Independent assurance evidence

`PILOT_READY` requires evidence that at least one authorized real dataset completed:

- declaration and classification;
- quarantine and validation;
- admission;
- secure ingestion;
- financial calculation;
- row-level and aggregate reconciliation;
- tenant-isolation testing;
- retention/deletion or a verified deletion rehearsal;
- backup/restore boundary testing;
- independent Financial QA and Release Audit review.

No raw data is included in the evidence package.

## 12. Immediate blockers

The dataset or pilot is blocked by:

- absent owner authorization;
- direct identifiers without approved necessity and controls;
- unencrypted storage or transport;
- cross-tenant access;
- raw data in logs, GitHub, CI, prompts, or evidence;
- failed source reconciliation beyond approved tolerance;
- unknown financial operations silently mapped to zero;
- missing retention/deletion policy;
- marketplace write credentials or methods;
- open P0/P1 or CRITICAL/HIGH findings.
