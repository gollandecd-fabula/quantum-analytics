# Quantum Project Rules Master

Status: `ACTIVE`

Authority: explicit project-owner directives and approved repository contracts. A later explicit project-owner decision supersedes an older rule.

## 1. Governance

1. GitHub is the durable source of truth; critical rules must not exist only in chat history.
2. Immutable stage contracts define stage boundaries; live execution-state files define current unit state.
3. Stable verified state and unverified work in progress must always be recorded separately.
4. Proposer, verifier, and gatekeeper roles remain separated for high-risk changes.
5. Unknown, contradictory, stale, or unverified evidence fails closed.
6. Exact-head evidence replaces older-head evidence; older evidence must be marked stale.

## 2. Product and architecture

1. Quantum is marketplace-neutral and product-category-neutral.
2. Wildberries is the first adapter, not the platform core.
3. MVP mode is read-only.
4. Architecture is a modular monolith with API Service and Worker Service boundaries.
5. Premature microservices and Kubernetes are excluded.
6. Legacy `Approval Execution Core v0.2.1` is untrusted and reusable only selectively after audit.
7. Marketplace writes, external action execution, and production deployment require separate explicit authorization.

## 3. Data admission and provenance

1. Every uploaded file is untrusted input.
2. Preserve every raw original immutably and record SHA-256.
3. Unknown, changed, or semantically ambiguous schemas go to quarantine.
4. Repeated import must be idempotent and must not duplicate financial events.
5. Canonical records retain source-file and source-record identifiers.
6. Evidence Chain must trace results deterministically to rules, inputs, records, and files.
7. Published snapshots are never silently rewritten; corrections use versioned revision, reversal, supersession, or restatement semantics.
8. Operational, settlement, and tax-recognition views remain separate.
9. Real or anonymized commercial data is not admitted until the relevant gates and external second-line review pass.
10. Secrets, credentials, marketplace tokens, production keys, personal data, and real commercial datasets are prohibited in GitHub.

## 4. Financial kernel

1. Monetary calculations use Decimal arithmetic, never binary floating point.
2. Cost, tax rate, tax base, other expenses, allocation, and rounding must not be hidden or hardcoded as universal commercial constants.
3. Product cost, tax rate, and other expenses are explicit configurable inputs.
4. Scenario results remain isolated from Actual results and may not mutate Actual state.
5. Results use typed states such as valid, blocked, unavailable, and conflict; missing values must not be coerced to zero.
6. Rule precedence, overlap, exclusivity, dependencies, and versioned rounding are deterministic.
7. Arbitrary user code execution is prohibited; SAFE_EXPRESSION is constrained by schema and runtime validation.
8. Unknown operations, double counting, unconfirmed formulas, untrusted traces, or missing authoritative dependencies block publication.
9. Financial changes require golden, property-based, differential, typed-state, replay, isolation, and reconciliation tests as applicable.
10. Golden Oracle inputs remain synthetic until real-data admission is explicitly approved.
11. Source Authority activation and ACTIVE financial rules require separate gates.

## 5. CI, review, and merge gates

1. Foundation CI and OSS Admission/official-registry/OSV checks must pass on the exact candidate head.
2. Artifact manifests must match tracked content hashes and sizes exactly.
3. Independent exact-head review must return no findings.
4. Unresolved review threads must equal zero.
5. QA, CI, or review failures trigger automatic diagnosis, remediation, rerun, and evidence synchronization.
6. Permission is required only for a genuinely new stage unless standing Quantum authorization already covers it.
7. Retrying, fixing within the same stage, or rollback after failure does not require new permission.
8. Implementation merge uses an expected-head SHA guard.
9. Post-merge completion evidence is recorded in a separate closure PR.
10. `RELEASE_BLOCKED` remains until all required closure evidence is merged.
11. Temporary diagnostics must be removed before final merge unless explicitly promoted to permanent regression tests.

## 6. Quantum autonomous execution protocol

1. For Quantum only, work continues automatically through implementation, QA, review remediation, evidence closure, and the next authorized roadmap task.
2. Pending review, CI queue, failed checks, or other recoverable states are not reasons to stop.
3. Work stops only at a critical blocker that requires a project-owner decision or unavailable authority.
4. After every tool action, record stage, status, completed work, outputs, verification, risks, and next action.

## 7. Security, privacy, pilot, and self-learning

1. Pilot access is invitation-only or approved-request-only.
2. Each tester has a personal account, while direct identifiers are minimized.
3. Pseudonymous accounts are preferred; unnecessary name, phone, and email collection is prohibited.
4. Personal-data processing must implement localization, transparent consent, minimization, consent logging, withdrawal, deletion, and secure authentication consistent with applicable Russian-law requirements.
5. Initial clients use the system free of charge in controlled testing mode unless a later explicit decision changes this.
6. Self-learning uses a controlled auditable loop: data -> hypothesis -> controlled experiment -> measured result -> approved rule/model update.
7. Learning must record data lineage, consent scope, experiment version, evaluation, rollback, and human approval.
8. Self-learning may not directly activate rules, execute marketplace writes, or perform autonomous commercial actions.

## 8. Technology direction

The admitted direction may include DuckDB, Polars, Pandera, Hypothesis, FastAPI/Pydantic, React-admin, and ECharts, subject to dependency admission, official-registry verification, OSV checks, licensing review, and demonstrated stage need. `wbsdk` requires a separate audit.

## 9. Release blockers

Release remains blocked when any of the following is true:

- real-data admission is not approved;
- marketplace write capability exists without authorization;
- a financial formula is unconfirmed;
- double counting is possible;
- source semantics are unknown;
- exact-head CI is not green;
- the artifact manifest differs from tracked content;
- independent review is incomplete;
- unresolved review threads are non-zero;
- closure evidence is missing or stale;
- security, privacy, tenant-isolation, or recovery gates are incomplete.
