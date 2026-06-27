# Q-METRICS-001 — Core Metric Set Normalization

Status: `DRAFT`
Risk class: `R2`
Approval state: `NOT_APPROVED_FOR_IMPLEMENTATION`

## Goal

Adapt the recovered 19-metric specification to Constitution v3.0 without category,
brand, marketplace, cost, tax, or expense constants.

## Required correction

The legacy symbol `C40` must not exist in the canonical financial formula.
Replace it with a versioned, scoped configuration rule representing other expenses.

## Constraints

- no hidden assumptions;
- no default cost;
- no default tax rate;
- no default tax base;
- no default other expense;
- missing required values block only dependent calculations;
- every metric has source authority, freshness, confidence, and Evidence Chain;
- common expenses are not allocated to products without an approved allocation rule.

## Acceptance criteria

- metric formulas contain no fixed monetary constants;
- orders, gross sales units, returns, charges, payouts, and inventory are separate;
- financial result terminology states its confirmed expense boundary;
- search position, CTR and conversion return UNAVAILABLE when source data is absent;
- calculations reconcile row-wise and aggregate-wise;
- Actual and Scenario results are isolated.

## Gate

Independent product, data, financial, and QA review is required before ACTIVE status.
