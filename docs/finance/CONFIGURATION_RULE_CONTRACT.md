# Configuration Rule Contract v1

Status: `DRAFT_FOR_B1A_REVIEW`
Risk class: `R2`
Tracking issue: `#7`

## Purpose

A Configuration Rule represents one explicit, versioned financial input or
calculation instruction. Rules replace all hardcoded assumptions for product
cost, tax rate, tax base, other expenses, and allocation.

A rule is configuration, not a marketplace event. A rule never rewrites the
canonical event ledger and never becomes active merely because it exists.

## Rule types

- `COST` — product or service cost.
- `TAX` — tax rate and tax base selection.
- `OTHER_EXPENSE` — any user-defined expense not represented by a dedicated source event.
- `ALLOCATION` — explicit allocation of a common amount to a supported target scope.

No product category, marketplace, brand, currency, cost, tax rate, tax base, or
other-expense value is a system constant.

## Rounding policy ownership

Rounding policy is not a Configuration Rule type in contract v1. A Calculation
Profile references one immutable approved rounding policy through
`rounding_policy_ref` using the canonical `{id, version, content_hash}` shape.

A `FIXED_VALUE`, `RATE`, or `SAFE_EXPRESSION` rule cannot substitute for a
rounding-policy reference. This keeps financial input resolution separate from
rounding-policy selection and prevents two competing rounding authorities inside
one Calculation Profile.

## Typed scope

Every rule has a scope containing:

- `organization_id` — required tenant boundary;
- `marketplace_account_id` — optional account restriction;
- `marketplace` — optional adapter-neutral marketplace code;
- `product_id` — optional canonical product restriction;
- `product_group_id` — optional user-managed group restriction;
- `calculation_profile_id` — optional profile restriction;
- `scenario_id` — required only for Scenario rules and forbidden for Actual rules.

Unsupported dimensions are rejected. Empty wildcard strings are forbidden;
absence means wildcard. A rule that names both `product_id` and
`product_group_id` is invalid unless a later approved contract explicitly
allows intersection semantics.

## Scope specificity

Organization equality is a mandatory tenant-boundary filter and is evaluated
before specificity. It is never a wildcard and never contributes to ordering.

For deterministic resolution, specificity is the versioned lexicographic vector:

```text
(product_id,
 product_group_id,
 marketplace_account_id,
 marketplace,
 calculation_profile_id,
 scenario_id)
```

Each component is `1` when the rule constrains that dimension and `0` when the
dimension is wildcard. Vectors are compared left to right. Therefore a
product-specific rule outranks account- or marketplace-only rules regardless of
the number of lower-order dimensions they constrain. Priority is considered
only after the complete specificity vector is equal.

Specificity is derived, never supplied by the user. Changing the vector order
requires a new contract version, impact preview, updated machine-readable test
vectors, and independent review.

## Methods

Exactly one method is selected:

- `FIXED_VALUE` — decimal monetary or scalar value;
- `RATE` — decimal rate applied to an explicit base;
- `SAFE_EXPRESSION` — typed declarative expression defined by the Safe Expression Contract.

Exactly one of `value`, `rate`, or `expression` is present. The two unused
payload properties are omitted, not present as `null`. A fixed value does not
silently acquire a rate base. A rate always names its base. An expression lists
all variable dependencies explicitly.

## Bases

Initial base vocabulary:

- `NONE`;
- `UNIT`;
- `ORDER`;
- `EVENT`;
- `PERIOD`;
- `GROSS_SALES`;
- `NET_SALES`;
- `PAYOUT`;
- `PRODUCT_COST`;
- `CUSTOM_VARIABLE`.

`CUSTOM_VARIABLE` requires a declared variable dependency. Unknown bases are
rejected rather than interpreted heuristically.

## Units

Initial unit vocabulary:

- `MONEY`;
- `MONEY_PER_ITEM`;
- `MONEY_PER_ORDER`;
- `MONEY_PER_EVENT`;
- `MONEY_PER_PERIOD`;
- `RATE`;
- `DIMENSIONLESS`.

A monetary rule requires an ISO 4217 uppercase currency code. A rate or
dimensionless rule has `currency: null`.

## Lifecycle

```text
DRAFT → SHADOW → PILOT → ACTIVE → SUSPENDED → RETIRED
```

- `DRAFT` cannot affect any result.
- `SHADOW` may be evaluated for comparison but cannot replace Actual results.
- `PILOT` may affect an explicitly isolated pilot profile only.
- `ACTIVE` may affect results inside its approved scope and validity period.
- `SUSPENDED` and `RETIRED` cannot be newly selected.

A lifecycle transition creates a new immutable rule version or an immutable
status-transition record. Historical calculation profiles retain the exact
version they used.

## Validity

- `valid_from` is inclusive.
- `valid_to` is exclusive or null for an open interval.
- `valid_to` must be later than `valid_from`.
- Calculation time is explicit and cannot default to wall-clock time inside the resolver.

## Priority and exclusivity

Priority is an integer used only after scope matching and equality of the full
specificity vector. Higher values win. Priority cannot resolve a forbidden
overlap inside the same `exclusivity_group`; such overlap is a validation error
before activation.

Rules without an exclusivity group may coexist only when the metric contract
explicitly declares their expense components additive. Addition is never
inferred from rule type alone.

## Dependencies

Every rule declares zero or more dependencies:

- metric input identifiers;
- canonical event fields;
- configuration variable identifiers;
- other rule outputs allowed by an approved dependency graph.

Dependency cycles are invalid. Unknown dependencies are invalid. A dependency
that is `EMPTY`, `BLOCKED`, `UNAVAILABLE`, or `CONFLICT` propagates according to
the metric contract; it is never converted to numeric zero.

## Provenance and audit

Every rule records:

- stable `rule_id` and immutable `version`;
- actor and creation timestamp;
- source or user-input origin;
- content SHA-256;
- approval reference where required;
- status and validity interval;
- optional superseded rule reference;
- change reason.

## Fail-closed diagnostics

Contract validation produces typed codes, including:

- `RULE_METHOD_PAYLOAD_MISMATCH`;
- `RULE_SCOPE_INVALID`;
- `RULE_CURRENCY_UNIT_MISMATCH`;
- `RULE_VALIDITY_INVALID`;
- `RULE_DEPENDENCY_UNKNOWN`;
- `RULE_DEPENDENCY_CYCLE`;
- `RULE_EXCLUSIVITY_OVERLAP`;
- `RULE_RESOLUTION_TIE`;
- `RULE_UNSAFE_EXPRESSION`;
- `RULE_NOT_APPROVED`.

These diagnostics block only dependent calculations. They do not suppress
unrelated metrics.

## Activation gate

No rule becomes `ACTIVE` in B1a. Activation requires:

- schema and semantic validation;
- overlap and cycle checks;
- preview impact;
- approved golden calculation;
- immutable calculation-profile snapshot;
- independent verification;
- explicit R3 approval where financial behavior changes.
