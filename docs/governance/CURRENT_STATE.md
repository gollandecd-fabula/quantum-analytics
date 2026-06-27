# CURRENT STATE

Date: 2026-06-27
Status: `BUILD_B1A_READY_FOR_MERGE`
Active contract: `STAGE-B-BUILD-v1`
Current unit: `B1a — FINANCIAL_RULE_CONTRACTS_AND_RESOLUTION`
Tracking issue: `#7`
Working branch: `build-b1a-financial-contracts`
Pull Request: `#8`

## Scope

B1a is R2 contract, schema, fixture, test, and evidence work. It does not implement the calculation kernel, activate financial rules, admit real commercial data, enable marketplace writes, or authorize production. Source Authority remains DRAFT and release remains blocked.

## Verification

- Foundation tests: 34.
- B1a tests: 26.
- Reproducible total: 60 passed tests.
- Latest technical CI: `28298953265`, success on Python 3.12.3.
- Codex review threads: 20 total, 0 unresolved.
- Current metadata-synchronized head requires final CI and Codex review before squash merge.

## Confirmed invariants

- no fixed cost, tax, tax base, other expense, allocation, or rounding default;
- one rule method payload only;
- `CUSTOM_VARIABLE` requires at least one declared dependency;
- rounding policy is owned by Calculation Profile `rounding_policy_ref`;
- scope wildcards use omission only and tenant boundaries are mandatory;
- rule resolution is deterministic and fail-closed;
- eligible candidates carry complete ordering tuples;
- zero remains a VALID value, not a state;
- Actual and Scenario remain isolated;
- safe expressions are typed, arity constrained, and currency aware;
- purchases use explicit quantity and amount metrics;
- Calculation Profile references use `{id, version, content_hash}`;
- golden values require an independent oracle.

## Remaining gate

- current-head CI success;
- current-head Codex review with no unresolved findings;
- protected squash merge of PR #8.

B1b remains R3 and is not approved. B2, B6, B7, production, real-data admission, and Macro-stage C remain unapproved.

`RELEASE_BLOCKED`
