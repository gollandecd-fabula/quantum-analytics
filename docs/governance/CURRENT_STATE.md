# CURRENT STATE

Date: 2026-06-27
Status: `BUILD_B1A_READY_FOR_MERGE`
Active contract: `STAGE-B-BUILD-v1`
Live execution state: `docs/evidence/STAGE_B_EXECUTION_STATE.yaml`
Current unit: `B1a — FINANCIAL_RULE_CONTRACTS_AND_RESOLUTION`
Tracking issue: `#7`
Working branch: `build-b1a-financial-contracts`
Pull Request: `#8`

## Scope

B1a is R2 contract, schema, fixture, test, and evidence work. It does not implement the calculation kernel, activate financial rules, admit real commercial data, enable marketplace writes, or authorize production. Source Authority remains DRAFT and release remains blocked.

## Verification

- Foundation tests: 34.
- B1a tests: 33.
- Reproducible total: 67 passed tests.
- Latest technical CI: `28303919943`, success on Python 3.12.3.
- Codex review threads: 26 total, 0 unresolved.
- Artifact manifest v6 verifies 157 tracked artifacts by SHA-256 and byte size.
- Current metadata-synchronized head requires final CI and Codex review before squash merge.

## Confirmed invariants

- no fixed cost, tax, tax base, other expense, allocation, or rounding default;
- one rule method payload only;
- RATE rules require `unit: RATE` and `currency: null`;
- `CUSTOM_VARIABLE` requires at least one declared dependency;
- rounding policy is owned by Calculation Profile `rounding_policy_ref`;
- every Calculation Profile version is a complete immutable reference snapshot;
- scope wildcards use omission only and tenant boundaries are mandatory;
- rule resolution is deterministic and fail-closed;
- ACTUAL rejects Scenario rules; SCENARIO requires `scenario_id` and supports matching overrides;
- eligible candidates carry complete ordering tuples;
- zero remains a VALID value, not a state;
- safe expressions are typed, arity constrained, currency aware, and comparisons return BOOLEAN;
- metric units represent `MONEY_PER_ITEM` explicitly;
- purchases use explicit quantity and amount metrics;
- Calculation Profile references use `{id, version, content_hash}`;
- artifact evidence is reproducible against the tracked tree;
- golden values require an independent oracle.

## Remaining gate

- current-head CI success;
- current-head Codex review with no unresolved findings;
- protected squash merge of PR #8.

B1b remains R3 and is not approved. B2, B6, B7, production, real-data admission, and Macro-stage C remain unapproved.

`RELEASE_BLOCKED`
