# Rule Resolution Contract v1

Status: `DRAFT_FOR_B1A_REVIEW`
Risk class: `R2`
Tracking issue: `#7`

## Purpose

The resolver chooses configuration deterministically for one calculation
context and returns either exactly one selected candidate or a typed non-value
state. It never guesses, silently chooses between equal candidates, or converts
missing configuration to zero.

## Context

The resolver receives an explicit context containing:

- `organization_id`;
- calculation mode: `ACTUAL` or `SCENARIO`;
- calculation instant;
- optional marketplace account;
- optional marketplace;
- optional product;
- optional product group;
- Calculation Profile identifier;
- Scenario identifier when mode is Scenario.

Wall-clock time and ambient tenant state are forbidden inputs.

## Candidate filtering

A rule is eligible only when all conditions hold:

1. organization matches exactly;
2. lifecycle status is allowed by the profile and publication class;
3. calculation instant is inside `[valid_from, valid_to)`;
4. every scoped dimension matches the context;
5. Actual/Scenario isolation holds;
6. dependencies are available and valid;
7. no exclusion, suspension, or approval gate blocks the rule.

For scope matching, `organization_id` is always present and must match exactly.
For every other supported scope dimension, an omitted property is the only
wildcard encoding. A present property, including an explicit null, is not a
wildcard and fails validation before resolution. Unknown scope properties are
invalid.

An Actual context ignores Scenario-scoped rules. A Scenario context may use the
explicit inherited Actual versions contained in its Calculation Profile and
matching Scenario overrides.

## Specificity

Organization equality is a mandatory precondition and does not contribute to
specificity. Specificity is the lexicographic vector:

```text
(product_id,
 product_group_id,
 marketplace_account_id,
 marketplace,
 calculation_profile_id,
 scenario_id)
```

Each component is `1` when constrained by the rule and `0` when wildcard. The
vector is compared left to right. It is not replaced by a count of constrained
dimensions.

## Deterministic ordering

Eligible candidates are ordered by:

1. specificity vector, descending;
2. explicit priority, descending;
3. `valid_from`, descending;
4. immutable rule version, descending.

The complete ordering tuple is:

```text
(specificity_vector, priority, valid_from, version)
```

Every eligible candidate records this complete tuple. A truncated tuple is
invalid because it cannot reproduce the winner. An ineligible candidate records
`ordering_tuple: null` and at least one exclusion reason.

Rule identifiers are not a financial tie-breaker. If two candidates remain
equal across the full ordering tuple, resolution returns `CONFLICT` with
`RULE_RESOLUTION_TIE`.

## Selection authority

Candidate trace is the sole machine-readable authority for the selected rule.
Every candidate records `selected: true` or `selected: false`.

- A `VALID` result contains exactly one candidate with both `eligible: true` and
  `selected: true`.
- The selected rule is the immutable `rule` reference inside that candidate.
- Other eligible candidates use `selected: false`.
- Ineligible candidates always use `selected: false`.
- `BLOCKED`, `CONFLICT`, and `UNAVAILABLE` results contain no selected candidate.

Contract v1 deliberately has no separate top-level `selected_rule` field. A
duplicated rule reference cannot be proven equal to an array element by standard
JSON Schema and would create two competing selection authorities.

## Output states

- `VALID` — exactly one selected eligible candidate is returned.
- `BLOCKED` — a required rule is absent or approval blocks calculation.
- `CONFLICT` — equal eligible rules or a forbidden overlap prevent selection.
- `UNAVAILABLE` — a required external dependency is unavailable.

Numeric zero belongs only inside a `VALID` typed value after rule evaluation. It
is not a resolution state.

## Trace

Each result records:

- resolver contract version;
- normalized context hash;
- result state;
- diagnostic code where applicable;
- every considered candidate;
- candidate eligibility;
- candidate selection marker;
- exclusion reasons;
- complete ordering tuple for eligible candidates;
- actor, resolution time, and trace identifier.

## Fail-closed behavior

The resolver does not select a rule when:

- required configuration is missing;
- an unresolved complete tie exists;
- an exclusivity overlap exists;
- a dependency is unknown, invalid, or cyclic;
- units or currencies are incompatible;
- the selected rule is not approved for the requested publication class.

Only calculations depending on the blocked rule are blocked. Unrelated metrics
remain independently evaluable.

## Preview

A proposed rule version can be evaluated in preview without activation. Preview
uses the same resolver contract and returns:

- current selected candidate;
- proposed selected candidate;
- affected scopes and periods;
- conflicts and blocked dependencies;
- metrics potentially affected;
- direction or amount of change only when safely computable.

Preview cannot mutate Actual profiles or activate a rule.

## Golden vectors

Machine-readable vectors cover:

- product scope beating account scope;
- priority breaking equal specificity;
- later validity breaking equal priority;
- version breaking equal validity;
- complete tie returning `CONFLICT`;
- missing required rule returning `BLOCKED`;
- Actual ignoring Scenario rules;
- Scenario override beating inherited Actual rule;
- cross-organization exclusion;
- overlap, cycle, and unit-mismatch diagnostics.

Each resolution context declares `ACTUAL` or `SCENARIO` explicitly. Omitting mode
is invalid rather than defaulting to Actual.

## Gate

B1a defines the contract, schema, vectors, and tests. Production resolver code,
active-rule evaluation, and financial-result changes are B1b R3 work and are not
authorized here.
