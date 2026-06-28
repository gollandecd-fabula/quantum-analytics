# Metric Result Contract v1

Status: `DRAFT / B3 R2`

## Purpose

A Metric Result is an immutable, marketplace-neutral snapshot of one metric for one organization, accounting view, scope, period, mode, and exact set of versioned inputs. It is evidence metadata only: this contract does not implement the B1b calculation kernel and does not activate any financial rule.

## Identity and immutability

Every snapshot contains:

- `metric_result_id` — stable snapshot identifier;
- `result_version` — positive immutable version;
- `result_hash` — SHA-256 of the canonical snapshot payload;
- exact `metric_definition_ref` (`id`, `version`, `content_hash`);
- exact `calculation_profile_ref` (`id`, `version`, `content_hash`);
- exact `rounding_policy_ref` and `source_authority_ref`;
- `evidence_chain_ref` with ID, version, and content hash;
- deterministic `input_fingerprint`.

A published snapshot is never edited in place. Recalculation creates a new result and references its predecessor.

## Result semantics

`result` follows the typed-value state model. Numeric zero is a valid value and never represents missing data.

- `VALID` requires a non-null value and no reason code.
- `EMPTY`, `BLOCKED`, `UNAVAILABLE`, `CONFLICT`, `INVALID`, and `NOT_APPLICABLE` require `value: null` and a non-empty reason code.
- `validity.state` must equal `result.state`.
- Currency is present only when required by the referenced Metric Definition.
- Unit, value type, currency behavior, and accounting view must match the referenced Metric Definition exactly.

These cross-document checks are semantic validation requirements; JSON Schema validation alone is necessary but not sufficient.

## Scope, period, and mode

The result records organization, optional marketplace account, marketplace-neutral dimensions, period start/end/timezone/status, and accounting view.

- `ACTUAL` requires `scenario_id: null`.
- `SCENARIO` requires a non-empty `scenario_id`.
- Scenario results never replace or mutate Actual results.

## Freshness, confidence, and validity

Freshness records `as_of`, `evaluated_at`, status (`FRESH`, `STALE`, `UNKNOWN`), and age limits. `UNKNOWN` never silently becomes fresh.

Confidence records an explicit level, optional decimal score from 0 to 1, and non-empty evidence basis. Confidence is not validity and cannot make a blocked or unavailable result publishable.

Validity records typed state, diagnostic codes, and publishability. Only `VALID` may be publishable, and publication still requires the referenced Metric Definition and Calculation Profile to permit it.

## Recalculation audit

Every snapshot contains:

- kind: `INITIAL`, `RECALCULATION`, or `RESTATEMENT`;
- actor and reason;
- requested/completed timestamps;
- predecessor result ID/hash for non-initial runs;
- deterministic replay key;
- input fingerprint.

`INITIAL` requires null predecessor fields. `RECALCULATION` and `RESTATEMENT` require both predecessor fields.

## Evidence dependency

The referenced Evidence Chain must resolve without ambiguity:

`Metric Result → Metric Definition → Calculation Profile → Events → Transformations → Source Records → Source Files → SHA-256`.

Broken links, unknown versions, hash mismatches, duplicate identities, missing required evidence classes, or contradictory state/value metadata make the result non-publishable and fail closed.

## Security and scope boundary

The contract contains no secrets or real commercial data. It grants no marketplace write capability, deployment authorization, or production release. B1b, B2, B6, and B7 remain gated.