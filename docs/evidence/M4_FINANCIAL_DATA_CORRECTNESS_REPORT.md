# MILESTONE 4 — Financial & Data Correctness

**Baseline commit:** `2016929fa6ed58dcf6c950b33afdaf75d1468a60`  
**Branch:** `fix/quantum-one-click-stable-release`  
**Scope:** deterministic finance, required inputs, returns, tax, expense boundaries, reconciliation and evidence lineage  
**Marketplace writes:** disabled  
**Release state:** `RELEASE_BLOCKED`

## 1. Financial contract

The confirmed calculation remains deterministic and uses Decimal arithmetic with the versioned rounding policy.

### Units and returns

```text
net_sold_units = gross_sales_units - returned_units
```

Return constraints:

- all unit counts must be non-negative;
- `returned_units <= gross_sales_units`;
- `resalable_returned_units + compensated_returned_units <= returned_units`;
- a positive compensation amount requires at least one compensated return;
- compensation without compensated units is rejected;
- restored resalable units do not consume product cost again;
- non-resalable and compensated returns remain inside the cost exposure defined by the kernel.

### Product cost

```text
product_cost_amount =
    cost_per_unit × (gross_sales_units - resalable_returned_units)
```

`cost_per_unit` is mandatory and user-provided. It is not hard-coded by product category.

### Other expenses

Each component is explicit and versioned:

```text
MONEY_PER_ITEM component = value × net_sold_units
MONEY component          = value
other_expense_amount     = sum(all components)
```

The component list is mandatory. Negative values, malformed components, duplicates and excessive component counts are blocked.

### Marketplace income

```text
net_marketplace_income_amount =
    gross_sales_amount
    - discounts_amount
    + subsidies_excluding_return_compensation_amount
    + return_compensation_amount
    - marketplace_commission_amount
    - forward_logistics_amount
    - reverse_logistics_amount
    - storage_amount
    - advertising_amount
    - fines_withholdings_amount
```

### Tax

```text
tax_amount = selected_tax_base × tax_rate
```

Guardrails:

- `tax_rate` is mandatory and user-provided;
- accepted range is `0..1`;
- the selected base must be an approved money metric;
- a negative tax base does not create a negative tax automatically;
- without an explicit negative-base policy, the result is `BLOCKED` with `TAX_BASE_NEGATIVE_POLICY_REQUIRED`.

### Net profit

```text
net_profit_amount =
    net_marketplace_income_amount
    - product_cost_amount
    - other_expense_amount
    - tax_amount
```

```text
profit_per_sold_unit = net_profit_amount / net_sold_units
```

Profit per unit is blocked when `net_sold_units <= 0`. `profitability_of_costs` remains blocked until its denominator policy is explicitly approved.

## 2. Mandatory confirmed metrics

A local pilot may claim `PILOT_RUN_COMPLETE` only after all seven metrics are valid and reconciled:

1. `net_sold_units`;
2. `product_cost_amount`;
3. `other_expense_amount`;
4. `tax_amount`;
5. `net_marketplace_income_amount`;
6. `net_profit_amount`;
7. `profit_per_sold_unit`.

## 3. Red Team findings

### M4-D001 — partial reconciliation false positive — P1

Before the patch, reconciliation iterated only over values supplied by the caller. Therefore:

- an empty `expected_metrics` object could reconcile;
- a single matching `net_profit_amount` could reconcile;
- the pilot could report completion without checking cost, tax and other required metrics.

#### Correction

- the expected metric set must equal the complete mandatory set;
- values are serialized using canonical JSON (`sort_keys`, compact separators, UTF-8);
- the canonical bytes are bound to `control_totals_sha256`;
- absence of the hash yields `PENDING`;
- a hash mismatch or incomplete metric set yields `CONFLICT`;
- every actual metric must be `VALID` and equal to the bound expected value.

### M4-D002 — independent oracle tax divergence — P1

A deterministic 500-case audit initially found 41 disagreements. In every disagreement the selected tax base was negative:

- kernel: `BLOCKED / TAX_BASE_NEGATIVE_POLICY_REQUIRED`;
- oracle: generated a negative tax and continued profit calculation.

The kernel behavior matches the fail-closed policy. The oracle was corrected to block tax, profit and profit per unit on a negative tax base until a separate policy is approved.

Post-correction deterministic audit:

```text
seed=20260712
cases=500
mismatches=0
result=PASS
```

## 4. Verified reference case

The permanent M4 test covers:

- gross units: 10;
- returns: 2;
- resalable returns: 1;
- compensated returns: 1;
- cost per unit: 400 RUB;
- per-sold-unit expense: 40 RUB;
- fixed expense: 100 RUB;
- tax rate: 6% of gross sales;
- commissions, forward and reverse logistics, storage, advertising, fines, discounts, subsidies and return compensation.

Expected results:

| Metric | Expected |
|---|---:|
| Net sold units | 8 |
| Product cost | 3,600.00 RUB |
| Other expenses | 420.00 RUB |
| Tax | 600.00 RUB |
| Marketplace income | 7,750.00 RUB |
| Net profit | 3,130.00 RUB |
| Profit per sold unit | 391.25 RUB |

## 5. Evidence and lineage

Confirmed finance outputs preserve:

- deterministic `input_hash`;
- deterministic `result_hash`;
- source identifiers for every mandatory metric;
- accounting view and expense boundary;
- rounding policy reference and application point;
- tenant binding for the local pilot;
- independent verifier requirement;
- privacy-safe reconciliation differences without raw commercial rows.

## 6. Local validation

- pre-patch failing evidence preserved;
- final targeted tests: 10 tests × 3 repetitions = 30 PASS;
- compileall: PASS;
- deterministic oracle audit: 500/500 PASS;
- no marketplace write path enabled.

## 7. Remaining limitations

- no authorized real commercial dataset was reconciled in M4;
- `profitability_of_costs` is intentionally blocked pending denominator policy;
- no country-specific tax interpretation is inferred automatically;
- external competitor estimates cannot confirm finance metrics;
- browser-render and UI evidence belong to M5;
- clean-environment release verification belongs to M8;
- production release and final scoring remain blocked.

## 8. M4 candidate verdict

`PASS_WITH_LIMITATIONS` is permitted only after exact-head CI validates the runtime patch, updated local-pilot tests, finance oracle and immutable manifest R49. Until then the branch remains a release-blocked candidate.
