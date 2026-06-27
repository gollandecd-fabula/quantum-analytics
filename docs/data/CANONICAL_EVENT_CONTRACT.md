# Canonical Event Contract — Draft

Every canonical event must include:

- event_id
- organization_id
- marketplace_account_id
- event_type
- event_time
- recognition_time
- stable_business_key
- source_row_key
- revision
- idempotency_key
- supersedes_event_id
- reversal_of_event_id
- import_batch_id
- source_record_id
- schema_version
- payload
- provenance
- status

No field may silently substitute an absent value with zero.
