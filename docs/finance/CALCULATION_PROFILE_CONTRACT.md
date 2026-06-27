# Calculation Profile Contract v1

Status: `DRAFT_FOR_B1A_REVIEW`
Risk class: `R2`
Tracking issue: `#7`

## Purpose

A Calculation Profile is an immutable snapshot of every versioned contract and
configuration input needed to reproduce a metric result. A mutable user profile
may create a new Calculation Profile version, but an existing snapshot is never
edited in place.

## Required identity

- `profile_id` — stable logical profile identifier;
- `profile_version` — positive immutable version;
- `organization_id` — tenant boundary;
- `marketplace_account_id` — optional account restriction;
- `mode` — `ACTUAL` or `SCENARIO`;
- `scenario_id` — null for Actual and required for Scenario;
- `effective_at` — explicit calculation instant;
- `created_at`, `actor`, and `reason`;
- `profile_hash` — SHA-256 of canonical content excluding the hash field.

## Snapshot references

Every immutable artifact reference uses one canonical shape:

```json
{
  "id": "stable-domain-identifier",
  "version": 1,
  "content_hash": "64-lowercase-hex-characters"
}
```

The common key `id` stores the stable identifier appropriate to the referenced
domain. For example, it contains a rule's logical rule identifier inside
`rule_refs`, a metric definition identifier inside `metric_definition_refs`,
and a rounding-policy identifier inside `rounding_policy_ref`. Alternate keys
such as `rule_id`, `metric_id`, or `policy_id` are not valid inside Calculation
Profile references in contract v1.

The profile contains sorted immutable references to:

- configuration rules: `id`, `version`, `content_hash`;
- metric definitions: `id`, `version`, `content_hash`;
- rounding policy: `id`, `version`, `content_hash`;
- Source Authority Matrix version and hash;
- Product Master version and hash when product identity is relevant;
- resolver contract version;
- safe-expression contract version;
- accounting-view vocabulary version;
- optional approved tolerance-policy reference.

A reference without a stable `id`, positive integer `version`, or content hash is
invalid. Aliases such as `latest` are forbidden because they do not identify an
immutable version.

## Mode isolation

- Actual profiles have `scenario_id: null` and cannot reference Scenario rules.
- Scenario profiles require `scenario_id` and may reference explicit inherited
  Actual-rule versions plus Scenario overrides.
- Profile identifiers and hashes are namespaced by mode.
- A Scenario profile cannot replace, supersede, or publish an Actual snapshot.

## Completeness

Before publication, the profile validator confirms:

- every required metric input has an eligible rule or approved source;
- no rule-resolution conflict exists;
- no dependency cycle exists;
- units and currencies are compatible;
- all referenced versions exist and their hashes match;
- rounding policy is approved for the profile mode;
- Source Authority status is adequate for the requested publication class;
- no DRAFT, SUSPENDED, or RETIRED rule is selected for Actual publication.

A profile may exist in `DRAFT` or `SHADOW` with incomplete references, but it
cannot publish a VALID Actual metric.

## Lifecycle

```text
DRAFT → SHADOW → PILOT → ACTIVE → SUSPENDED → RETIRED
```

A lifecycle change creates an immutable status transition. A profile version is
never silently promoted by changing its content.

## Canonicalization

Canonical profile JSON uses:

- UTF-8 and sorted object keys;
- reference arrays sorted by `id`, then positive integer `version`;
- timestamps normalized to UTC ISO 8601;
- decimal values, when present in embedded approved metadata, represented as
  normalized strings;
- no insignificant whitespace.

`profile_hash` is computed with SHA-256 over the canonical object excluding
`profile_hash` itself.

## Evidence Chain

Every metric snapshot records the exact Calculation Profile reference and hash.
The profile links the result to rule versions, metric definitions, rounding,
Source Authority, Product Master, actor, effective time, and approval evidence.

## Change impact

Creating a new profile version requires an impact preview listing:

- metrics affected;
- periods and scopes affected;
- changed rule/metric/policy references;
- expected directional impact when safely computable;
- blocked calculations and conflicts;
- whether prior closed periods require restatement rather than overwrite.

## Diagnostics

- `PROFILE_REFERENCE_MISSING`;
- `PROFILE_HASH_MISMATCH`;
- `PROFILE_RULE_CONFLICT`;
- `PROFILE_DEPENDENCY_CYCLE`;
- `PROFILE_UNIT_MISMATCH`;
- `PROFILE_CURRENCY_MISMATCH`;
- `PROFILE_ROUNDING_UNAPPROVED`;
- `PROFILE_SOURCE_AUTHORITY_UNAPPROVED`;
- `PROFILE_MODE_CONTAMINATION`;
- `PROFILE_PUBLICATION_BLOCKED`.

## Gate

B1a defines schemas, canonicalization rules, and test fixtures. Creating an
ACTIVE profile that changes financial results or evaluating the profile in the
calculation kernel is B1b R3 work and is not authorized.
