# B1b Calculation Kernel Contract v1

Status: `REVIEW_PENDING_OWNER_SIGNOFF`
Risk class: `R3`
Tracking issue: `#32`
Implementation branch: `build-b1b-financial-kernel-v1`

## Purpose

This contract defines the synthetic-only, dependency-free financial calculation
kernel implemented in B1b. It evaluates explicit financial inputs under B1a
configuration, typed-state, calculation-profile, rule-resolution, safe-expression,
and rounding contracts. It does not activate financial rules, admit marketplace
data, publish verified metric snapshots, reconcile periods, or authorize release.

## Authorization and separation of duties

- Explicit user R3 authorization was recorded on 2026-06-30.
- Business Golden Oracle Owner: `PROJECT_OWNER_USER`.
- Baseline source: synthetic scenarios independently derived from approved contracts.
- Public production facade: `src/quantum/finance/runtime.py`.
- Internal production modules: `_common.py`, `_rounding.py`, `_expression.py`,
  `_rules.py`, `_metrics.py`, `_calculation_core.py`, `_calculation_expenses.py`,
  and `_calculation_profit.py`; these are package-private and CI-scanned.
- Independent reference path: `src/quantum/finance/oracle.py`.
- The reference path must not import or call the production runtime.
- Exact candidate fixture values require explicit owner signoff before the baseline
  may change from `CANDIDATE_VALUES_PENDING_EXPLICIT_OWNER_SIGNOFF` to `APPROVED`.
- External second-line financial review remains mandatory before real or anonymized
  commercial data or production use.

## Public runtime boundary

The runtime exposes:

- `validate_rounding_policy(policy, preview=True)`;
- `evaluate_expression(expression, variables, declared_dependencies, policy)`;
- `resolve_rule(rules, context)`;
- `evaluate_resolved_rule(resolution, rules, variables, policy)`;
- `calculate(request)`.

All arithmetic uses `decimal.Decimal`. Binary floating point is rejected. Inputs
and results are canonical JSON-compatible mappings and are never mutated.

## Typed values

Every value has exactly these fields:

- `state`: `VALID`, `EMPTY`, `BLOCKED`, `UNAVAILABLE`, or `CONFLICT`;
- `value`: normalized string/integer/boolean for `VALID`, otherwise `null`;
- `value_type`: `MONEY`, `DECIMAL`, `RATE`, `INTEGER`, or `BOOLEAN`;
- `unit` and explicit `currency` where applicable;
- `reason_code`: null for `VALID`, non-empty for a non-valid state;
- sorted unique `source_ids`.

Numeric zero is a valid value. Missing configuration, unavailable evidence,
conflict, and zero remain distinct. Non-valid state precedence for a dependent
calculation is `CONFLICT > BLOCKED > UNAVAILABLE > EMPTY`.

## Rounding

The kernel implements the B1a allowlist:

- `HALF_EVEN`;
- `HALF_UP`;
- `DOWN`;
- `UP`;
- `FLOOR`;
- `CEILING`.

Only named application points are accepted. Input normalization uses
`RULE_INPUT_NORMALIZATION`; component results may use `RULE_COMPONENT_RESULT`;
final money and rate metrics use `METRIC_FINAL_ACCOUNTING`. Presentation and
export rounding are not reused as calculation inputs. No rounding policy is
selected implicitly.

## Rule resolution and evaluation

Resolution is deterministic over the complete ordering tuple:

```text
(specificity_vector, priority, valid_from, version)
```

A complete tie returns `CONFLICT/RULE_RESOLUTION_TIE`. A forbidden exclusivity
collision returns `CONFLICT/RULE_EXCLUSIVITY_OVERLAP`. Missing required rules or
publication approval return `BLOCKED`. Candidate trace is the only selection
authority; a duplicate top-level selected-rule field is rejected.

Supported rule methods are `FIXED_VALUE`, `RATE`, and `SAFE_EXPRESSION`.
`ALLOCATION` is not implemented because allocation recognition and reconciliation
belong to a later approved contract/B2 boundary.

Safe expressions are typed JSON AST data. The evaluator is limited to the
contracted arithmetic, comparison, and conditional operators over declared typed
variables. Every capability outside that explicit allowlist is denied, including
executable text, external-resource access, dynamic lookup, and implicit fallback.

## Preview calculation request

A request explicitly supplies:

- calculation, organization, mode, Scenario, and timestamp identity;
- immutable Calculation Profile reference;
- a `SHADOW` or isolated `PILOT` profile status;
- one explicit rounding policy;
- ISO 4217 currency;
- typed source values for every requested source metric;
- explicit cost per unit;
- an explicit list of other-expense components, including an explicit zero when
  the intended expense is zero;
- explicit tax rate and tax-base metric identifier.

`ACTIVE` profiles are rejected. An empty other-expense component list is not zero;
it blocks the dependent metrics with `OTHER_EXPENSE_RULE_REQUIRED_MISSING`.

## Implemented preview metrics

- `net_sold_units = gross_sales_units - returned_units`;
- `product_cost_amount = net_sold_units × explicit cost_per_unit`;
- `other_expense_amount = sum(explicit named components after unit expansion)`;
- `net_marketplace_income_amount = gross_sales_amount - discounts_amount + subsidies_amount - marketplace_commission_amount - forward_logistics_amount - reverse_logistics_amount - storage_amount - advertising_amount - fines_withholdings_amount`;
- `tax_amount = explicit tax rate × explicit selected money base`;
- `net_profit_amount = net_marketplace_income_amount - product_cost_amount - other_expense_amount - tax_amount`;
- `profit_per_sold_unit = net_profit_amount / net_sold_units`, with a zero denominator returning `BLOCKED/ZERO_DENOMINATOR`;
- `profitability_of_costs = BLOCKED/COST_DENOMINATOR_NOT_APPROVED` until an independent denominator boundary is approved.

No formula contains a product, brand, marketplace, cost, tax, tax-base, currency,
or other-expense commercial constant.

## Result boundary

`calculate` returns `quantum-financial-kernel-result-v1` with:

- organization, mode, Scenario, profile, and rounding identity;
- `publication_state: PREVIEW_ONLY`;
- the eight typed metric results and confirmed expense boundaries;
- deterministic `input_hash` and `result_hash`;
- explicit limitations.

The result is not a B3 published metric snapshot and cannot bypass B3 Evidence
Chain validation. B4 may render it only after the approved snapshot-building
boundary is satisfied.

## Golden baseline and tests

Candidate fixture: `tests/contracts/fixtures/b1b-golden-baseline.json`.

Required and implemented test classes:

- golden calculations;
- independent differential oracle comparison;
- conservation, sign, monotonicity, and no-double-count invariants;
- all supported decimal rounding modes and tie behavior;
- typed-state propagation and valid-zero separation;
- Actual/Scenario isolation;
- rule precedence, tie, exclusivity, and deterministic candidate order;
- Safe Expression type, unit, currency, arity, limit, and capability rejection;
- request mutation and replay determinism;
- fixed-commercial-constant and forbidden-capability scans.

## Deferred boundaries

- Source Authority activation;
- real or anonymized marketplace data;
- B2 reconciliation, periods, reversals, restatements, and lifecycle accounting;
- approved allocation rules;
- approved profitability denominator;
- verified metric publication;
- external access, deployment, marketplace writes, or production release.

`RELEASE_BLOCKED` remains mandatory.
