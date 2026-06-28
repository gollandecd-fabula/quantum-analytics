# CURRENT STATE — B3 SNAPSHOT

Date: 2026-06-28
Status: `BUILD_B3_RECOVERY_CI_AND_REVIEW_PENDING`
Active contract: `STAGE-B-BUILD-v1`
Current unit: `B3 — METRIC_SNAPSHOTS_AND_EVIDENCE_CHAIN`
Tracking issue: `#9`
Working branch: `build-b3-metric-evidence-contracts-v3`
Execution snapshot: `docs/evidence/STAGE_B_B3_EXECUTION_STATE.yaml`
Predecessor merge: `ff6bc6e23d3df7d877230578c4de0f02f20fce0d`
Permanent B1a cleanup baseline: `40c8ef94b4826257c2935d3ac499009734be758f`

## Authority and dependency gate

- Macro-stage B remains explicitly approved.
- B3 is R2 contracts, schemas, fixtures, and tests only.
- B1a artifacts are inherited from protected `main`.
- `tests/test_b3_evidence_contracts.py` fails closed if the B1a baseline is absent.
- B1b financial calculation implementation remains R3 and is not approved.

## B3 artifacts

- `docs/evidence/METRIC_SNAPSHOT_CONTRACT.md`;
- `docs/evidence/EVIDENCE_CHAIN_CONTRACT.md`;
- `schemas/metric-result.schema.json`;
- `schemas/evidence-chain.schema.json`;
- `tests/contracts/fixtures/b3-evidence-chain-vectors.json`;
- `tests/test_b3_evidence_contracts.py`;
- `docs/evidence/STAGE_B_B3_CONTRACT_EVIDENCE.yaml`;
- `docs/evidence/STAGE_B_B3_EXECUTION_STATE.yaml`.

## B3 invariants

- metric snapshots are immutable and versioned;
- typed states exactly match Stage A4;
- numeric zero is a VALID value;
- B1a metric units, including `MONEY_PER_ITEM`, remain representable;
- MONEY payloads require decimal strings, money units, and ISO currency;
- INTEGER payloads are JSON integers;
- DECIMAL and RATE payloads are decimal strings;
- non-money payloads cannot carry money units or currency;
- every reference has a positive version and SHA-256;
- graph SHA-256 is recalculated from canonical UTF-8 JSON bytes;
- snapshot Evidence Chain locator contains only stable id/version, while the
  Evidence Chain retains the hashed root snapshot reference;
- transformation sequence is zero-based, unique, and contiguous;
- evidence uses exact typed paths to retained source-file bytes;
- selected rules are linked through Rule Resolution nodes;
- tenant and Actual/Scenario boundaries are enforced;
- calculation evidence is acyclic;
- missing links, wrong edge types, version/hash mismatches, cross-tenant
  references, mode contamination, and cycles fail closed;
- freshness, confidence, limitations, accounting view, expense boundary,
  rounding, actor, reason, and trace are explicit;
- recalculation and restatement create history links rather than overwriting results.

## Verification state

- local B3 contract tests: 16 passed;
- six review findings: remediated pending re-review;
- GitHub Actions exact-head CI: pending after recovery;
- independent review: pending after recovery;
- merge: blocked until all gates pass.

## Approval gates

- B1b, B2, B6, and B7 remain R3 and are not approved.
- No metric is calculated or published in B3.
- No financial rule, Rounding Policy, or Source Authority row becomes ACTIVE.
- Real or anonymized commercial data is not admitted.
- Final hosting platform and production remain unapproved.

## Release state

`RELEASE_BLOCKED`
