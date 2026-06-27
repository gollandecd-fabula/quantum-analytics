# Rounding Policy v1

Status: `DRAFT_FOR_B1A_REVIEW`
Risk class: `R2`
Tracking issue: `#7`

## Principles

- All monetary and rate arithmetic uses decimal types; binary floating point is forbidden.
- Rounding is explicit, versioned, hashed, and included in the Evidence Chain.
- Intermediate rounding and presentation rounding are separate.
- No system-wide or commercial default policy is activated in B1a.
- A missing required policy blocks only dependent calculations; it does not choose a mode implicitly.

## Supported modes

Initial allowlist:

- `HALF_EVEN`;
- `HALF_UP`;
- `DOWN` — toward zero;
- `UP` — away from zero;
- `FLOOR`;
- `CEILING`.

Changing or extending the allowlist requires a new contract version and golden
impact analysis.

## Scales

A policy declares:

- `calculation_scale` — precision retained by approved intermediate application points;
- `money_scale` — final accounting scale for monetary amounts;
- `rate_scale` — final scale for rates and ratios;
- optional currency-specific presentation scale;
- maximum input precision and scale accepted before validation fails.

Scales are non-negative integers. Currency-specific presentation scale never
changes stored accounting value.

## Application points

Rounding may occur only at explicitly named points:

- `RULE_INPUT_NORMALIZATION`;
- `RULE_COMPONENT_RESULT`;
- `METRIC_FINAL_ACCOUNTING`;
- `REPORT_PRESENTATION`;
- `EXPORT_PRESENTATION`.

A metric definition lists its permitted points. Rounding after every arithmetic
operation is forbidden unless an approved metric contract explicitly requires
it and the golden baseline proves the behavior.

## Intermediate versus presentation rounding

- Intermediate/accounting rounding changes the stored result and therefore must
  be part of the calculation-profile hash.
- Presentation rounding changes display only and cannot be used as an input to
  another calculation.
- Reports and exports disclose the applied policy ID, version, mode, and scale.
- Recalculation under a new accounting policy creates a new metric snapshot and
  may require restatement; history is not overwritten.

## Currency behavior

- Monetary addition/subtraction requires identical currency.
- No implicit currency conversion is allowed.
- The policy may declare presentation scales by ISO 4217 currency code.
- Absence of a currency-specific presentation scale uses the explicit general
  presentation scale in that policy, not a hidden global constant.
- Currency behavior is validation metadata, not a source of exchange rates.

## Negative values and ties

The selected decimal mode applies symmetrically according to its mathematical
definition. Golden vectors must include positive and negative values, exact
ties, values immediately below/above ties, zero, and large magnitudes.

## Lifecycle

```text
DRAFT → SHADOW → PILOT → ACTIVE → SUSPENDED → RETIRED
```

Only an approved `ACTIVE` policy may be referenced by an Actual publication
profile. B1a creates no ACTIVE policy.

## Canonicalization and hash

The canonical policy document includes:

- stable `policy_id` and positive `version`;
- status;
- all modes, scales, application points, and currency presentation scales;
- actor, timestamps, source, reason, and approval reference;
- previous-policy reference where applicable.

The SHA-256 is calculated over canonical JSON excluding the hash field.

## Diagnostics

- `ROUNDING_POLICY_MISSING`;
- `ROUNDING_POLICY_NOT_APPROVED`;
- `ROUNDING_MODE_UNSUPPORTED`;
- `ROUNDING_SCALE_INVALID`;
- `ROUNDING_POINT_FORBIDDEN`;
- `ROUNDING_CURRENCY_INVALID`;
- `ROUNDING_HASH_MISMATCH`;
- `ROUNDING_PRESENTATION_USED_AS_INPUT`.

## Golden acceptance

Before activation, an independent golden baseline must cover:

- every mode used;
- every accounting application point;
- supported scales and currencies;
- positive, negative, zero, and tie cases;
- aggregation order and row-versus-aggregate behavior;
- comparison with an independent decimal oracle.

The calculation implementation actor cannot approve the corresponding golden
baseline.
