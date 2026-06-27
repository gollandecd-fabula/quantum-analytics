# Legacy Reuse Matrix

Status: `A3_COMPLETE`
Rule: no legacy evidence transfers automatically to Quantum.

| Artifact | Classification | Reusable | Must change or defer |
|---|---|---|---|
| Quantum Analytics Core Metrics v1.1 | REVISE | Metric hierarchy, separation of orders/sales/returns, financial-result ladder, data-status disclosure | Replace legacy `C40` with configurable versioned `other_expense` rules; formalize source authority; preserve typed states |
| 06_THREAT_MODEL.md | REUSE_WITH_SCOPE_REVIEW | Untrusted-input boundary, sandboxing, token isolation, idempotency, ambiguous-result reconciliation, supply-chain controls | GitHub webhook/write threats move to LATER security project |
| Approval Execution Core v0.2.1 | SELECTIVE_REUSE_ONLY | Atomic claims, bounded retry, crash recovery, malformed-input tests, dedicated-database guard, evidence discipline | Do not reuse as Quantum architecture or claim its QA for new code |
| 04_TARGET_ARCHITECTURE.md | REVISE | PostgreSQL, worker leases, sandbox boundaries, exact evidence, API/Worker runtime split | Remove GitHub mutation pipeline; reinterpret as modular monolith; defer Agents SDK and GitHub App |
| 07_ACCEPTANCE_TEST_MATRIX.md | REVISE | Schema rejection, resource limits, secret scan, evidence bundle, idempotency and recovery patterns | Replace webhook/branch/PR tests with ingestion, ledger, reconciliation, calculation and Evidence Chain tests |
| 03_GAP_MATRIX.md | HISTORICAL_REFERENCE | Evidence that Development Agent was not implemented | Do not treat agent gaps as Quantum MVP blockers |
| Quantum Master Prompt v2.0 audits | SUPERSEDED_REFERENCE | Audit rationale and discovered failure modes | Constitution v3.0 is authoritative |
| Quantum Master Prompt v3.0 / Plan v152.0 | ACTIVE_AUTHORITY | Full Project Constitution and Runtime Protocol | Changes require audit, migration notes and explicit user decision |

## Prohibited evidence transfer

The following statements are invalid unless independently reproduced in the Quantum repository:

- test counts from the Approval Execution Core;
- coverage percentages;
- mutation-test results;
- concurrency guarantees;
- deployment readiness;
- GitHub integration readiness;
- Development Agent readiness.
