# Recommendation engine R1

Status: `INTEGRATION_BUILD_R1 / UNIT_2_2`

## Input boundary

The engine consumes only completed source-bridge results with typed observed metrics. It does not read raw marketplace rows and does not replace missing or blocked values with zero.

Supported R1 sources:

- `WB_SUPPLIER_GOODS`;
- `WB_DETAILED_FINANCIAL`.

## Policy boundary

Thresholds and forecast coefficients are not hidden constants. A complete versioned policy is required and must contain:

- warning and critical buyout rates;
- warning and critical return rates;
- commission, logistics and storage ratio warnings;
- stock-to-buyout warning;
- settlement-gap warning amount;
- maximum policy rates for commission, logistics, storage and return-related cost reduction.

Without a policy the recommendation bundle is `BLOCKED` with `RECOMMENDATION_POLICY_REQUIRED`.

## Recommendation classes

R1 can produce:

- completion of required financial inputs;
- low-buyout investigation;
- stockout and high-stock review;
- high-return investigation;
- commission and price-structure review;
- forward and reverse logistics review;
- storage-cost review;
- settlement-gap reconciliation.

## Financial effect

The engine separates current observed cost from forecast effect. Cost forecasts use only an explicit policy maximum reduction rate. Every resulting upper bound is marked `upper_bound_not_expected_savings = true`.

Where no approved causal or financial model exists, forecast state is `BLOCKED` instead of an invented value.

## Runtime isolation

HOME_LOCAL attaches the recommendation bundle after source dispatch. A missing policy yields a blocked bundle; a malformed policy yields an isolated recommendation error. Neither outcome changes source admission or source-bridge status.
