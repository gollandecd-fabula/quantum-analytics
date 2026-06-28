# CURRENT STATE

Date: 2026-06-28
Status: `BUILD_B3_RECOVERY_CI_AND_REVIEW_PENDING`
Active contract: `STAGE-B-BUILD-v1`
Live execution state: `docs/evidence/STAGE_B_EXECUTION_STATE.yaml`
Current unit: `B3 — METRIC_SNAPSHOTS_AND_EVIDENCE_CHAIN`
Tracking issue: `#9`
Working branch: `build-b3-metric-evidence-contracts-v3`

## Predecessor closure

- B1a merged into protected `main` as `ff6bc6e23d3df7d877230578c4de0f02f20fce0d`.
- Permanent B1a manifest cleanup is included from `40c8ef94b4826257c2935d3ac499009734be758f`.
- B1a exact-head GitHub Actions run `28317157742` succeeded.
- All 31 B1a review threads were resolved.
- B1b remains R3 and is not approved.

## Active B3 scope

B3 is R2 contract/schema/fixture/test/evidence work only. It defines immutable
Metric Snapshot and Evidence Chain contracts. It does not calculate or publish a
metric, activate financial rules, admit real commercial data, write to a
marketplace, deploy production services, or authorize release.

## B3 verification

- 16 B3 contract tests pass locally.
- Evidence Chain graph SHA-256 is recalculated from canonical bytes.
- Transformation replay sequence is zero-based, unique, and contiguous.
- VALID MONEY payloads require a money unit and ISO currency.
- INTEGER, DECIMAL, and RATE payload representations are type-bound and cannot
  carry money units or currency.
- Snapshot-to-Evidence reference uses an unhashed stable locator; the Evidence
  Chain retains the hashed root snapshot reference, breaking the hash cycle.
- The valid Evidence Chain fixture uses the published schema field names.
- Required evidence is checked as exact typed paths, not generic node reachability.
- Rule evidence uses `RULE_RESOLUTION -> RESOLUTION_SELECTS_RULE -> CONFIGURATION_RULE`.
- Source evidence uses `CANONICAL_EVENT -> SOURCE_RECORD -> SOURCE_FILE`.
- Six review findings are remediated in the branch and await exact-head
  CI plus independent re-review.
- GitHub CI and independent review are pending for the recovery head.

## Gate

Merge B3 only after exact-head GitHub CI succeeds and all independent review
findings are resolved. B1b, B2, B6, and B7 remain gated R3 units without
approval.

`RELEASE_BLOCKED`
