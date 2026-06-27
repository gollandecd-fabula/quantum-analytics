# Metric Catalogue v1

Status: `DRAFT_FOR_B1A_REVIEW`
Risk class: `R2`
Tracking issue: `#7`

This catalogue defines metric semantics only. It contains no approved formula,
commercial constant, Source Authority activation, or publishable financial
result. Every materialized metric definition must conform to
`schemas/metric-definition.schema.json`, receive an immutable content hash, and
be included in an approved Calculation Profile.

## Common contract

All metrics support the states `EMPTY`, `BLOCKED`, `UNAVAILABLE`, `CONFLICT`,
`VALID`, and valid numeric zero. Every published snapshot requires Calculation
Profile, normalized events, transformations, source records, source-file
SHA-256, rounding policy, Source Authority, actor, reason, and trace evidence.

| Metric ID | View | Type / unit | Kind | Required inputs or rule outputs | Confirmed expense boundary |
|---|---|---|---|---|---|
| `orders_count` | OPERATIONAL | INTEGER / ORDER | EVENT_AGGREGATE | accepted order events | none |
| `ordered_units` | OPERATIONAL | INTEGER / ITEM | EVENT_AGGREGATE | ordered quantity | none |
| `gross_sales_units` | OPERATIONAL | INTEGER / ITEM | EVENT_AGGREGATE | recognized sale quantity | none |
| `returned_units` | OPERATIONAL | INTEGER / ITEM | EVENT_AGGREGATE | accepted return quantity | none |
| `net_sold_units` | OPERATIONAL | INTEGER / ITEM | DERIVED | gross sales units, returned units | none |
| `gross_sales_amount` | OPERATIONAL | MONEY | EVENT_AGGREGATE | recognized gross sale amount | none |
| `discounts_amount` | SETTLEMENT | MONEY | EXTERNAL_SOURCE | admitted discount source | none |
| `subsidies_amount` | SETTLEMENT | MONEY | EXTERNAL_SOURCE | admitted subsidy/compensation source | none |
| `marketplace_commission_amount` | SETTLEMENT | MONEY | EXTERNAL_SOURCE | admitted commission source | marketplace commission |
| `forward_logistics_amount` | SETTLEMENT | MONEY | EXTERNAL_SOURCE | admitted forward-logistics source | forward logistics |
| `reverse_logistics_amount` | SETTLEMENT | MONEY | EXTERNAL_SOURCE | admitted reverse-logistics source | reverse logistics |
| `storage_amount` | SETTLEMENT | MONEY | EXTERNAL_SOURCE | admitted storage source | storage |
| `advertising_amount` | SETTLEMENT | MONEY | EXTERNAL_SOURCE | admitted advertising source | advertising |
| `fines_withholdings_amount` | SETTLEMENT | MONEY | EXTERNAL_SOURCE | admitted fines/withholdings source | fines and withholdings |
| `payout_amount` | SETTLEMENT | MONEY | EXTERNAL_SOURCE | admitted payout source | none; payout is a separate flow |
| `inventory_on_hand_units` | OPERATIONAL | INTEGER / ITEM | EXTERNAL_SOURCE | accepted inventory snapshot | none |
| `product_cost_amount` | OPERATIONAL | MONEY | RULE_COMPONENT | net sold units; eligible `COST` rule | product cost |
| `other_expense_amount` | OPERATIONAL | MONEY | RULE_COMPONENT | eligible scoped `OTHER_EXPENSE` rules explicitly declared additive | other expense |
| `tax_amount` | TAX_RECOGNITION | MONEY | RULE_COMPONENT | eligible `TAX` rate and explicit tax base | tax |
| `net_marketplace_income_amount` | SETTLEMENT | MONEY | DERIVED | gross sale, discount, subsidy, commission, logistics, storage, advertising, fines | marketplace commission; forward/reverse logistics; storage; advertising; fines/withholdings |
| `net_profit_amount` | SETTLEMENT | MONEY | DERIVED | net marketplace income, product cost, other expense, tax | all admitted marketplace deductions plus product cost, other expense, tax |
| `profit_per_sold_unit` | SETTLEMENT | MONEY / ITEM | DERIVED | net profit, valid non-zero net sold units | same as net profit |
| `profitability_of_costs` | SETTLEMENT | RATE / PERCENT | DERIVED | net profit and an explicitly approved cost denominator | exactly the components named by the approved denominator contract |

## Semantic constraints

- Orders, sales, purchases, returns, charges, payouts, and inventory are separate flows.
- A payout is not revenue and is not silently used as a sales metric.
- `net_sold_units` does not treat missing return data as zero.
- A zero denominator produces `BLOCKED`, not infinity, zero, or an empty value.
- `OTHER_EXPENSE` components are additive only when the metric definition names
  distinct rule outputs; rule type alone never implies addition.
- `net_marketplace_income_amount` explicitly excludes product cost, other
  expense, and tax.
- `net_profit_amount` includes only expense components present in its approved
  metric version and Calculation Profile.
- `profitability_of_costs` remains `DRAFT_ONLY` until the denominator boundary is
  independently approved.
- Cross-currency aggregation is `BLOCKED` without an approved conversion contract.
- Operational, settlement, and tax-recognition values are never silently mixed.

## Rounding points

Money and rate metrics may use:

- `METRIC_FINAL_ACCOUNTING` under an approved policy;
- `REPORT_PRESENTATION` for display only;
- `EXPORT_PRESENTATION` for formatting only.

A metric may additionally use `RULE_COMPONENT_RESULT` only when its approved
version explicitly declares the application point and golden tests cover it.

## Activation gate

Every row remains draft. Before any metric becomes publishable:

- formula and input contracts are approved;
- Source Authority is approved;
- expense boundary is independently reviewed;
- a Calculation Profile and Rounding Policy are active;
- golden, property, differential, and reconciliation tests pass;
- B1b R3 implementation is explicitly authorized.
