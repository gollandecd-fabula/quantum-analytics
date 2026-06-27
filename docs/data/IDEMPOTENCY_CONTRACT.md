# Idempotency Contract v1.0

Status: `APPROVED_WITHIN_STAGE_A4`
Risk class: `R3`

## Goal

Reprocessing the same logical source data must not create duplicate source records,
canonical events, charges, returns, sales, payouts, or derived results.

## Keys

### File idempotency key

```text
organization_id
+ marketplace_account_id
+ source_file_sha256
+ adapter_id
+ adapter_version
```

### Source record idempotency key

```text
import_batch_id
+ source_row_key
+ raw_row_hash
```

### Canonical event idempotency key

```text
organization_id
+ marketplace_account_id
+ event_type
+ stable_business_key
+ revision
+ semantic_payload_hash
```

## Behaviour

- Exact replay returns the existing publication outcome.
- Same business key with a different semantic payload creates a new revision.
- Same file hash under another filename is still the same source file.
- Retry after worker crash resumes from durable checkpoints.
- Partial publication must be reconciled before retry.
- Ambiguous external outcomes are resolved by reading durable state, not by blind repeat.
- Duplicate detection must work under concurrent workers.

## Required database controls

- unique constraint for file idempotency key;
- unique constraint for source record idempotency key;
- unique constraint for canonical event idempotency key;
- transactional publication of event and provenance links;
- worker lease with expiry;
- atomic claim of pending work;
- immutable retry history.

## Forbidden implementation

- process-local deduplication only;
- time-window deduplication without stable keys;
- filename-based uniqueness;
- deleting the earlier event and replacing it in place;
- treating a timeout as proof that no write occurred.
