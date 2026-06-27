# Foundation Acceptance Plan v1

Status: `DRAFT`
Applies to: Macro-stage A only.

| ID | Category | Acceptance test | Gate |
|---|---|---|---|
| FND-001 | Governance | Constitution version and source hash are recorded | FOUNDATION |
| FND-002 | Governance | CURRENT_STATE references the active Stage Contract | FOUNDATION |
| FND-003 | Governance | No lower-level artifact overrides Constitution silently | FOUNDATION |
| FND-004 | Repository | Dedicated repository is connected and private | FOUNDATION |
| FND-005 | Repository | `main` is protected and direct force-push is disabled | FOUNDATION |
| FND-006 | Repository | Required governance files exist | FOUNDATION |
| FND-007 | Security | Secret scan reports zero confirmed secrets | FOUNDATION |
| FND-008 | Security | Third-party CI actions are absent or pinned by immutable SHA | FOUNDATION |
| FND-009 | Intake | Unsupported file type is rejected safely | FOUNDATION |
| FND-010 | Intake | Oversized and malformed files fail closed | FOUNDATION |
| FND-011 | Intake | Original file bytes are preserved with SHA-256 | FOUNDATION |
| FND-012 | Intake | Re-import of the same file is idempotent | FOUNDATION |
| FND-013 | Schema | Unknown schema enters quarantine and is not published | FOUNDATION |
| FND-014 | Schema | Semantic drift without column rename is detected by fixture | FOUNDATION |
| FND-015 | Typed state | EMPTY is not converted to numeric zero | FOUNDATION |
| FND-016 | Typed state | BLOCKED, UNAVAILABLE and CONFLICT remain distinguishable | FOUNDATION |
| FND-017 | Ledger | Stable business key and source row key are stored | FOUNDATION |
| FND-018 | Ledger | Revision, reversal and supersession links are validated | FOUNDATION |
| FND-019 | Ledger | Duplicate canonical event publication is prevented | FOUNDATION |
| FND-020 | Evidence | Metric or proof object traces to source record and file hash | FOUNDATION |
| FND-021 | Recovery | Worker crash does not publish duplicate events | FOUNDATION |
| FND-022 | Recovery | Expired job lease can be recovered safely | FOUNDATION |
| FND-023 | Operations | Technical health, data freshness and calculation health are distinct | FOUNDATION |
| FND-024 | Operations | Last valid result is retained when a later run is blocked | FOUNDATION |
| FND-025 | Release | Foundation Evidence Package matches actual artifact hashes | FOUNDATION |

## Release rule

All FND tests must have immutable evidence in the dedicated Quantum repository.
Mocks alone cannot prove object-storage durability, database migration safety, restore,
or repository protection.
