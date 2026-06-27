# Wildberries Synthetic Operations Schema v1

Status: `TEST_ONLY`
Purpose: A6 Data Proof
Authority for real Wildberries data: `NONE`

## Columns

| Column | Type | Required | Meaning |
|---|---|---:|---|
| row_id | string | yes | Stable source-row locator |
| operation_id | string | yes | Stable business key |
| operation_type | enum | yes | SALE or RETURN |
| event_time | datetime | yes | Business event time |
| recognition_time | datetime | yes | Recognition time |
| product_external_id | string | yes | Synthetic external product identifier |
| quantity | positive integer | yes | Units |
| gross_amount | non-negative decimal | yes | Synthetic gross amount |
| currency | string | yes | Currency code |
| revision | integer >= 1 | yes | Event revision |
| supersedes_event_id | string | conditional | Required for revision > 1 |
| reversal_of_event_id | string | conditional | Required for RETURN |

## Restrictions

- This is not a real Wildberries export contract.
- It cannot activate Source Authority Matrix rules.
- It contains no cost, tax, commission, logistics, storage, advertising,
  or other-expense assumptions.
