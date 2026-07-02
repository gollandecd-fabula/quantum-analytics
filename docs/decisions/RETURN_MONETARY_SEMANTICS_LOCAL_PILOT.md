# Return Monetary Semantics — Local Pilot

Status: APPROVED FOR LOCAL PILOT

## Scope

This decision applies to the read-only local Quantum pilot. It does not authorize production release, marketplace writes, deployment, or processing outside the approved local admission boundary.

## Required inputs

- `gross_sales_units`: units initially recognized as sold/fulfilled.
- `returned_units`: all buyer-returned units.
- `resalable_returned_units`: returned units physically restored to saleable inventory and not compensated by the marketplace.
- `compensated_returned_units`: returned units not restored to inventory for which marketplace compensation was received.
- `return_compensation_amount`: settlement income received for `compensated_returned_units`.
- `subsidies_excluding_return_compensation_amount`: subsidy income after explicitly excluding every amount represented by `return_compensation_amount`.

The remaining quantity

`returned_units - resalable_returned_units - compensated_returned_units`

is treated as non-resalable and uncompensated.

## Invariants

1. All unit counts and compensation amounts must be non-negative.
2. `returned_units <= gross_sales_units`.
3. `resalable_returned_units + compensated_returned_units <= returned_units`.
4. A positive `return_compensation_amount` requires at least one `compensated_returned_unit`.
5. A positive `compensated_returned_units` value requires a positive `return_compensation_amount`.
6. Missing or contradictory return disposition data fails closed.
7. `subsidies_excluding_return_compensation_amount` and `return_compensation_amount` are disjoint accounting sources by contract.
8. The ambiguous legacy input `subsidies_amount` is not admitted by the local-pilot kernel.
9. Return compensation invariants are evaluated on the exact parsed decimal before policy rounding or quantization.

## Calculation rules

### Net sold units

`net_sold_units = gross_sales_units - returned_units`

### Recognized product cost

`product_cost_amount = cost_per_unit × (gross_sales_units - resalable_returned_units)`

Only saleable, uncompensated returns restore product cost to inventory. Non-resalable and compensated returns keep product cost recognized as an expense.

### Marketplace income

`return_compensation_amount` and `subsidies_excluding_return_compensation_amount` are added as separate positive components. A source amount must belong to exactly one of these inputs.

### Per-unit operating expense

A `MONEY_PER_ITEM` other-expense component continues to use `net_sold_units` as its denominator boundary.

## Fail-closed behavior

Invalid unit relations produce `RETURN_UNIT_SEMANTICS_INVALID`. Invalid compensation relations, including negative sub-rounding amounts, produce `RETURN_COMPENSATION_SEMANTICS_INVALID`. Missing required return fields propagate typed `BLOCKED` states into product cost and profit instead of silently assuming a disposition. Requests containing the legacy `subsidies_amount` key fail input admission with `KERNEL_INPUTS_INVALID`.
