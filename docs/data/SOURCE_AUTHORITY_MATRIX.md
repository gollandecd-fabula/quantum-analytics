# Source Authority Matrix v1.0

Status: `APPROVED_AS_CONTRACT_TEMPLATE`
Risk class: `R3`

No source is authoritative merely because it contains a field. Authority is assigned
per metric, field, event type, marketplace, account, period, and schema version.

## Required columns

| Column | Meaning |
|---|---|
| `authority_rule_id` | Stable versioned identifier |
| `scope` | Organization, account, marketplace, event or metric scope |
| `subject` | Field, event type, or metric governed |
| `primary_source` | Preferred source |
| `fallback_sources` | Ordered alternatives |
| `reconciliation_sources` | Independent comparison sources |
| `tolerance` | Numeric, temporal, or categorical tolerance |
| `conflict_action` | BLOCK, QUARANTINE, PREFER_PRIMARY, MANUAL_DECISION |
| `valid_from` / `valid_to` | Effective period |
| `priority` | Rule precedence |
| `version` | Immutable rule version |
| `status` | DRAFT, SHADOW, PILOT, ACTIVE, SUSPENDED, RETIRED |
| `owner` | Accountable role |
| `evidence_required` | Minimum evidence for activation |

## Initial matrix

All entries remain `DRAFT` until a real Wildberries source contract is inspected.

| Rule ID | Subject | Primary | Fallback | Reconciliation | Tolerance | Conflict action | Status |
|---|---|---|---|---|---|---|---|
| SAM-ORDER-001 | Order event | UNAVAILABLE | none | UNAVAILABLE | exact business key | BLOCK | DRAFT |
| SAM-SALE-001 | Sale event | UNAVAILABLE | none | UNAVAILABLE | exact business key and amount | BLOCK | DRAFT |
| SAM-RETURN-001 | Return event | UNAVAILABLE | none | UNAVAILABLE | exact business key, units, amount | BLOCK | DRAFT |
| SAM-CHARGE-001 | Charge event | UNAVAILABLE | none | UNAVAILABLE | amount and charge type | BLOCK | DRAFT |
| SAM-PAYOUT-001 | Payout event | UNAVAILABLE | none | UNAVAILABLE | payout identifier and amount | BLOCK | DRAFT |
| SAM-INVENTORY-001 | Inventory snapshot | UNAVAILABLE | none | UNAVAILABLE | timestamp and quantity | BLOCK | DRAFT |
| SAM-PRODUCT-001 | Product identity | UNAVAILABLE | none | Product Master | exact external identifiers | QUARANTINE | DRAFT |
| SAM-TAX-001 | Tax rule | User configuration | none | Calculation preview | exact scope and period | BLOCK | DRAFT |
| SAM-COST-001 | Cost rule | User configuration/import | none | Calculation preview | exact scope and period | BLOCK | DRAFT |
| SAM-OTHER-EXPENSE-001 | Other expense rule | User configuration/import | none | Calculation preview | exact scope and period | BLOCK | DRAFT |

## Activation rule

A row cannot become `ACTIVE` until:

- the source schema and semantics are documented;
- at least one representative fixture is validated;
- reconciliation behaviour is tested;
- conflict action is approved;
- effective dates and owner are set;
- evidence exists in the repository.
