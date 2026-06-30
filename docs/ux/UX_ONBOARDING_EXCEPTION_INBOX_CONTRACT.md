# UX, Onboarding, and Exception Inbox Contract v1

Status: `IMPLEMENTED_FOR_P1_5_REVIEW`  
Risk class: `R2`  
Stage unit: `B5 — UX, onboarding, and Exception Inbox`  
Tracking issue: `#29`

## Purpose

P1.5 provides a dependency-free, headless presentation foundation over the
existing B1a, B3, B4, and ingestion contracts. It defines deterministic models
that a later approved browser surface may render. It does not activate a
financial rule, calculate a metric, admit real marketplace data, expose an HTTP
service, or authorize external access.

## Configuration onboarding

The configuration form exposes four explicit inputs:

- product cost;
- tax rate;
- tax base;
- other expense.

Every form carries organization, Actual/Scenario mode, optional scenario,
actor, explicit rule scope, validity interval, currency, creation timestamp, and
an immutable form hash. Optional scope dimensions use omission as the only
wildcard representation. Product and product-group scopes are mutually
exclusive.

No field contains a commercial default. A new field is `EMPTY` with `value:
null`. Numeric zero is accepted only when explicitly supplied as the normalized
string `"0"`. Missing validity start, missing monetary currency, malformed
decimal input, unknown tax base, scope conflict, and scenario mismatch fail
closed with machine-readable diagnostics.

Tax-base input follows the B1a `configuration-rule` vocabulary for `RATE`
rules. The accepted values are `UNIT`, `ORDER`, `EVENT`, `PERIOD`,
`GROSS_SALES`, `NET_SALES`, `PAYOUT`, `PRODUCT_COST`, and
`CUSTOM_VARIABLE`. `NONE` is rejected because B1a prohibits it for `RATE`.

A complete valid form reaches `READY_FOR_RULE_DRAFT`. This state means only
that a draft rule may be constructed by a later bounded workflow. It does not
create, approve, publish, or activate a B1 financial rule. The form publication
state is always `PREVIEW_ONLY`.

## Typed-state presentation

B4 report records are validated through the public reporting validator before
presentation. The UX view preserves the report state and provides a text-first
accessible status model:

- `VALID`;
- valid numeric zero;
- `EMPTY`;
- `BLOCKED`;
- `UNAVAILABLE`;
- `CONFLICT`;
- `INVALID`;
- `NOT_APPLICABLE`.

Status is never conveyed by color alone. Every result contains a status label,
stable status token, semantic role `status`, and accessible summary. A blocked
or missing value renders as an em dash and never as zero. Integer zero and every
canonical decimal-string representation whose numeric value is zero, including
`0.0`, `0.00`, `-0`, and `-0.00`, receive the distinct `valid-zero` token.

## Import status

Import presentation accepts only canonical `RawFileRecord` values. The public
UX boundary validates UUID, tenant, SHA-256, byte size, safe filename, canonical
storage key, state, schema/fingerprint payload, and diagnostics before rendering.

The states `RECEIVED`, `VALIDATING`, `VALID`, `QUARANTINED`, and `REJECTED`
have distinct text-first accessible views. Only `VALID` is marked admitted to
canonical processing. The raw storage key is never exposed by the UX view.
Quarantined and rejected files remain excluded.

Canonical diagnostic strings are preserved in their original order, including
empty or repeated values allowed by the P1.2 ingestion contract. When an import
exception needs one non-empty machine-readable cause, the Inbox uses the first
non-empty diagnostic; if none exists, it uses `IMPORT_<STATE>` without mutating
the source record.

Tenant scope is independent from organization scope. P1.5 does not infer or
invent a tenant-to-organization mapping.

## Evidence drill-down

The drill-down model preserves the Metric Snapshot identifier and hash,
Evidence Chain reference, optional verified Evidence Chain content hash,
limitations, mode, scenario, and organization.

A B4 `PREVIEW_ONLY` report produces `verification_status: PREVIEW_ONLY` and
`can_claim_verified_evidence: false`. Only an already validated B4
`EVIDENCE_VERIFIED` record may produce a verified claim. P1.5 does not verify
an Evidence Chain independently or upgrade publication state.

## Exception Inbox

The Exception Inbox accepts validated report records, validated configuration
forms, and optionally tenant-scoped import records. It produces deterministic,
hashed exception entries with:

- category and typed state;
- machine-readable cause;
- affected metric identifiers;
- Evidence Chain or raw-file SHA-256 references;
- required resolution;
- severity and open status;
- accessible summary.

Independent `VALID` metrics remain listed once in `available_metric_ids` when
another metric is blocked. Exceptions are sorted by content-derived identifiers,
so input order does not change the Inbox or its hash.

Mixed organizations, Actual/Scenario namespaces, tenants, duplicate report
records, duplicate import records, and duplicate configuration `form_id` values
fail closed. A supplied tenant identifier must be a non-empty string even when
no import records are present. Import exceptions require an explicit tenant
identifier. No exception resolution mutates source records, metric snapshots,
configuration rules, or marketplace state.

## Machine-readable artifacts

- `schemas/ux-configuration-form.schema.json`;
- `schemas/ux-view.schema.json`;
- `schemas/exception-inbox.schema.json`;
- `src/quantum/ux/runtime.py`;
- `src/quantum/ux/validation.py`;
- `src/quantum/ux/__init__.py`.

## Diagnostics

- `UX_FORM_MALFORMED`
- `UX_FORM_ID_INVALID`
- `UX_ORGANIZATION_ID_INVALID`
- `UX_ACTOR_INVALID`
- `UX_MODE_INVALID`
- `UX_SCENARIO_INVALID`
- `UX_SCOPE_INVALID`
- `UX_SCOPE_ORGANIZATION_MISMATCH`
- `UX_SCOPE_PRODUCT_AMBIGUOUS`
- `UX_SCOPE_SCENARIO_MISMATCH`
- `UX_CURRENCY_INVALID`
- `UX_CREATED_AT_INVALID`
- `UX_VALID_FROM_INVALID`
- `UX_VALID_TO_INVALID`
- `UX_VALIDITY_INTERVAL_INVALID`
- `UX_FORM_STATUS_INVALID`
- `UX_FORM_FIELDS_INVALID`
- `UX_FORM_PROBLEMS_INVALID`
- `UX_FORM_HASH_MISMATCH`
- `UX_CONFIGURATION_VALUES_INVALID`
- `UX_REPORT_INVALID`
- `UX_IMPORT_RECORD_INVALID`
- `UX_IMPORT_STATE_INVALID`
- `UX_IMPORT_STATE_PAYLOAD_INVALID`
- `UX_INBOX_CONTEXT_EMPTY`
- `UX_INBOX_ORGANIZATION_MIXED`
- `UX_INBOX_MODE_MIXED`
- `UX_INBOX_TENANT_REQUIRED`
- `UX_INBOX_TENANT_MIXED`
- `UX_INBOX_RECORD_DUPLICATE`
- `UX_INBOX_IMPORT_DUPLICATE`
- `UX_INBOX_FORM_DUPLICATE`
- `UX_INBOX_TIMESTAMP_INVALID`
- `UX_HASH_INVALID`
- `UX_HASH_MISMATCH`

## Acceptance mapping

- `Q-BLD-007` → typed-state and numeric-zero presentation tests;
- `Q-BLD-014` → explicit input, scope, validity, currency, and no-default tests;
- `Q-BLD-015` → Exception Inbox cause/evidence/resolution and continuity tests;
- `BLD-029` → configuration runtime and schema alignment;
- `BLD-030` → text-first accessible state views;
- `BLD-031` → deterministic Exception Inbox with independent metrics retained;
- `BLD-032` → configuration, import status, report, and evidence drill-down critical paths.

## Exclusions

- financial calculation kernel;
- rule publication or activation;
- Source Authority activation;
- real or anonymized commercial marketplace data;
- browser application or external HTTP API;
- authentication, external tenant provisioning, or production sessions;
- database persistence;
- production deployment;
- marketplace write operations.

`RELEASE_BLOCKED`
