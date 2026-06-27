# Rule Resolution Contract v1

Status: `DRAFT_FOR_B1A_REVIEW`
Risk class: `R2`
Tracking issue: `#7`

## Purpose

This contract defines deterministic selection of configuration-rule versions
for one calculation context. It does not evaluate financial formulas.

## Inputs

Resolution requires an explicit context:

- organization identifier;
- marketplace account and marketplace where known;
- canonical product and optional product group;
- calculation profile;
- mode: `ACTUAL` or `SCENARIO`;
- scenario identifier for Scenario mode;
- calculation instant;
- requested rule type or output identifier.

No context field is inferred from ambient process state.

## Candidate filtering

Candidates are filtered in this order:

1. stable rule/output identifier or requested rule type;
2. lifecycle eligibility;
3. calculation mode and scenario isolation;
4. validity interval;
5. organization boundary;
6. optional scope dimensions;
7. currency and unit compatibility;
8. dependency availability;
9. approval state required by the target profile.

A candidate failing any filter is excluded with a diagnostic reason.

## Lifecycle eligibility

- Actual publication accepts `ACTIVE` only.
- Shadow comparison accepts `ACTIVE` and `SHADOW` but labels results separately.
- Pilot calculation accepts `ACTIVE` and the explicitly named `PILOT` set.
- Scenario calculation uses Scenario-scoped rules plus explicitly inherited Actual rules.
- `DRAFT`, `SUSPENDED`, and `RETIRED` are never newly selected.

## Deterministic ordering

After filtering, candidates are ordered lexicographically by:

1. scope specificity, descending;
2. priority, descending;
3. `valid_from`, descending;
4. version, descending.

`rule_id` is not a semantic tie-breaker. It may be used only for stable display
of an already-conflicting set.

## Specificity vector

Specificity is represented as a fixed vector, not only a sum:

```text
(product_id,
 product_group_id,
 marketplace_account_id,
 marketplace,
 calculation_profile_id,
 scenario_id)
```

Each component is `1` when constrained by the rule and `0` when wildcard. The
vector is compared left to right. This prevents two materially different
scopes from becoming indistinguishable merely because they have the same count
of constrained dimensions.

The order above is part of the versioned contract. Changing it requires a new
contract version, impact preview, golden vectors, and approval.

## Winner and conflict

- Zero candidates: result `BLOCKED` with `RULE_REQUIRED_MISSING` when the metric requires the rule; otherwise the optional component is absent, not zero.
- One candidate: selected.
- Multiple candidates with a unique highest ordering tuple: highest candidate selected.
- Multiple candidates sharing the complete highest ordering tuple: result `CONFLICT` with `RULE_RESOLUTION_TIE`.

A lexical identifier or creation timestamp must not silently choose among a
semantic tie.

## Exclusivity and additive components

Before resolution, activation validation checks intervals for rules sharing an
`exclusivity_group`. Any overlapping eligible intervals in intersecting scopes
produce `RULE_EXCLUSIVITY_OVERLAP` and prevent activation.

Rules are additive only when a metric definition lists their output identifiers
as distinct additive components. Two rules of type `OTHER_EXPENSE` are not
implicitly additive.

## Scope intersection

Two scopes intersect when there exists at least one calculation context matching
both. A wildcard intersects every value. Different explicit values in the same
dimension do not intersect.

A rule containing both product and product-group restrictions is invalid in
contract v1. Therefore membership resolution cannot create an undocumented
intersection.

## Scenario isolation

- Actual resolution ignores every rule with `scenario_id`.
- Scenario resolution requires a scenario identifier.
- Scenario rules may override inherited Actual rules using the same ordering
  only inside that scenario.
- Scenario selections and profile hashes are stored separately from Actual.
- No Scenario status transition can activate an Actual rule.

## Dependency graph

Rules and metric definitions form a directed graph. Validation requires:

- every referenced node exists in the selected contract set;
- graph is acyclic;
- output types and units are compatible at every edge;
- Actual nodes cannot depend on Scenario nodes;
- unpublished or blocked nodes cannot be hidden by zero substitution.

Cycle diagnostics include the complete ordered cycle path.

## Resolution trace

Every resolution attempt records:

- context hash;
- candidate rule IDs and versions;
- eligibility state for every candidate;
- exclusion reasons;
- ordering tuple for eligible candidates;
- selected rule or typed conflict/missing state;
- resolver contract version;
- actor, timestamp, and trace ID.

An eligible candidate always records its complete ordering tuple and has no
exclusion reasons. An ineligible candidate records at least one exclusion reason
and has `ordering_tuple: null`. These representations are mutually exclusive;
an eligible candidate without its tuple is an invalid trace.

The trace is part of the Evidence Chain and must be reproducible.

## Test vectors

B1a maintains machine-readable vectors covering:

- more-specific scope wins;
- priority wins within identical scope specificity;
- later validity start wins after equal priority;
- later version wins after equal validity start;
- complete tie produces `CONFLICT`;
- missing required rule produces `BLOCKED`;
- Actual ignores Scenario rules;
- exclusivity overlap blocks activation;
- cycle and unit mismatch fail closed.
