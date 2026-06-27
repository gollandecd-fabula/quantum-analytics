# CURRENT STATE — B3 SNAPSHOT

Date: 2026-06-27
Status: `BUILD_B3_DEPENDENCY_CI_PENDING`
Active contract: `STAGE-B-BUILD-v1`
Current unit: `B3 — METRIC_SNAPSHOTS_AND_EVIDENCE_CHAIN`
Tracking issue: `#9`
Working branch: `build-b3-metric-evidence-contracts`
Execution snapshot: `docs/evidence/STAGE_B_B3_EXECUTION_STATE.yaml`

## Authority and dependency gate

- Macro-stage B remains explicitly approved.
- B3 is R2 contracts, schemas, fixtures, and tests only.
- B3 requires B1a artifacts in protected `main`.
- `tests/test_b3_evidence_contracts.py` fails closed if the required B1a baseline is absent.
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
- every reference has a positive version and SHA-256;
- evidence paths reach immutable source-file bytes and SHA-256;
- tenant and Actual/Scenario boundaries are enforced;
- calculation evidence is acyclic;
- missing links, version/hash mismatches, cross-tenant references, mode contamination, and cycles fail closed;
- freshness, confidence, limitations, accounting view, expense boundary, rounding, actor, reason, and trace are explicit;
- recalculation and restatement create history links rather than overwriting results.

## Pending verification

- execute Foundation, B1a, and nine B3 tests;
- confirm B1a dependency files exist in the branch baseline;
- inspect and repair any CI failures;
- open a protected Pull Request;
- obtain independent Codex review;
- resolve all findings and re-run CI;
- merge only after required checks pass.

## Connector limitation

The existing canonical `docs/governance/CURRENT_STATE.md` is not modified in
this commit because the current Connector session is not exposing the blob SHA
required by the contents API. This versioned snapshot preserves the exact B3
state without an unsafe blind overwrite. The canonical pointer must be updated
before B3 closure when a verified SHA becomes available.

## Approval gates

- B1b, B2, B6, and B7 remain R3 and are not approved.
- No metric is calculated or published in B3.
- No financial rule, Rounding Policy, or Source Authority row becomes ACTIVE.
- Real or anonymized commercial data is not admitted.
- Final hosting platform and production remain unapproved.

## Release state

`RELEASE_BLOCKED`
