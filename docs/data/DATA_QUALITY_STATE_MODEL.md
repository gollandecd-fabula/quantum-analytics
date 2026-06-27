# Data Quality State Model v1.0

Status: `APPROVED_WITHIN_STAGE_A4`

## Record-level states

- `RECEIVED`
- `VALIDATED`
- `QUARANTINED`
- `NORMALIZED`
- `PUBLISHED`
- `SUPERSEDED`
- `REVERSED`
- `REJECTED`

## Batch-level states

- `RECEIVED`
- `FINGERPRINTED`
- `ADAPTER_SELECTED`
- `VALIDATING`
- `QUARANTINED`
- `NORMALIZING`
- `RECONCILING`
- `PUBLISHED`
- `PARTIALLY_PUBLISHED`
- `FAILED`
- `RESTATED`

## Period states

- `OPEN`
- `PROVISIONAL`
- `CLOSED`
- `RESTATED`

## Rules

- A quarantined record is never published.
- A partially published batch requires reconciliation before retry.
- A closed period is not overwritten; corrections create a restatement.
- Data freshness and calculation validity are independent.
- A last valid result may remain visible while a later batch is blocked, but it must be marked stale.
