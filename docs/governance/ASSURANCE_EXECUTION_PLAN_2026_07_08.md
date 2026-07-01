# Quantum Assurance Execution Plan — 8 July 2026

Status: `ACTIVE`
Authority: explicit project-owner decision dated 2026-07-01
Tracking issue: `#39`
Target date: `2026-07-08`
Target outcome: `PILOT_READY` or an evidence-based blocking verdict
Macro-stage boundary: remains inside `B — BUILD`
Production release: `RELEASE_BLOCKED`

## 1. Purpose

This plan adds independent error, vulnerability, financial-correctness, operational-defence,
and release-verification functions to the governed Quantum delivery process.

It does not amend Constitution v3.0, does not replace `STAGE-B-BUILD-v1`, and does not
authorize Macro-stage C, production deployment, real marketplace writes, or unrestricted
external access.

The July 8 target is a controlled, invite-only, pseudonymous pilot candidate with immutable
evidence. It is not an automatic production-release approval.

## 2. Mandatory execution and assurance roles

### 2.1 Development Team

Responsibilities:

- implement the approved Stage B scope;
- remediate verified findings;
- add regression tests for every accepted defect;
- preserve read-only, Actual/Scenario isolation, typed states, Evidence Chain, and recovery boundaries;
- produce exact-head evidence for review.

Restrictions:

- cannot approve its own R2-or-higher change;
- cannot close its own security or financial finding without independent verification;
- cannot modify release evidence after gatekeeper review begins.

### 2.2 Red Team

Mission: attack the pilot candidate as an adversary.

Required attack classes:

- cross-tenant and authorization bypass;
- forged, stale, replayed, or mutated financial rule-resolution traces;
- financial-rule, tax, cost, rounding, source-authority, and Evidence Chain tampering;
- Actual/Scenario contamination;
- malformed, oversized, adversarial, duplicate, and semantically drifting files;
- secret, token, log, dependency, workflow, and supply-chain exposure;
- session, invitation, account-recovery, and privilege-lifecycle abuse;
- attempts to activate marketplace writes or unapproved external actions.

Restrictions:

- does not implement the production fix it later verifies;
- does not close its own findings;
- does not lower severity to satisfy the deadline.

### 2.3 Blue Team

Mission: make attacks observable, containable, and recoverable.

Responsibilities:

- security and privacy-safe audit logging;
- detection for cross-tenant attempts, forged traces, rule tampering, repeated authentication failures,
  unexpected privilege changes, and blocked write-capability access;
- incident triage, account/session revocation, containment, and recovery runbooks;
- alert-to-evidence linkage;
- backup, restore, rollback, and recovery-drill support.

Restrictions:

- cannot suppress a confirmed finding without an approved risk record;
- logs must not contain secrets, direct identifiers, or unminimized personal data;
- detection success does not replace prevention.

### 2.4 Purple Team

Purple Team is a controlled collaboration loop, not an approval authority.

Loop:

1. Red Team demonstrates a reproducible attack.
2. Development Team implements a bounded remediation.
3. Blue Team adds or verifies detection and response.
4. Independent Assurance reruns the exploit, regression, and evidence checks.
5. Release Gatekeeper decides whether the finding is closed.

Restrictions:

- cannot merge findings into vague combined tickets;
- cannot mark a finding closed without reproduction evidence and exact-head retest;
- cannot override the independent gatekeeper.

### 2.5 Quantum Independent Assurance Team

The team is organizationally independent from the implementation actor and contains four
mandatory functions.

#### IV&V

- requirements-to-code-to-test traceability;
- acceptance-criteria verification;
- independent reproduction of claimed fixes;
- regression and boundary testing;
- verification that the reviewed head equals the candidate head.

#### AppSec

- architecture and threat-model review;
- SAST, secret scanning, dependency and workflow review;
- tenant-isolation, authentication, authorization, file-abuse, injection, XSS, CSRF, CSP,
  session, and privacy-control validation;
- SBOM, OSV, license, provenance, and pinned-action checks.

#### Financial QA

- independent golden oracle;
- Decimal and versioned-rounding verification;
- property-based, differential, mutation, replay, and reconciliation tests;
- returns, reversals, restatements, taxes, costs, logistics, other expenses, and no-double-count checks;
- confirmation that missing, blocked, unavailable, conflict, valid, and numeric zero remain distinct.

#### Release Audit

- exact commit and branch verification;
- CI, artifact-manifest, review-thread, evidence-package, recovery, and rollback verification;
- open-risk and deferred-scope consistency;
- confirmation that no production credential, marketplace write capability, or unapproved real data
  entered the candidate.

Restrictions:

- Assurance may create test and evidence artifacts but does not approve its own changes;
- Assurance cannot replace the formal release gatekeeper;
- financial oracle ownership must remain independent from financial-kernel implementation.

### 2.6 Formal Validator and Release Gatekeeper

The Formal Validator evaluates typed machine-readable outputs and invariant compliance.

The Release Gatekeeper:

- evaluates immutable evidence only;
- does not modify implementation code;
- is separate from proposer, implementation actor, Red Team finding author, and remediation author;
- issues exactly one final verdict:
  - `NOT_READY`;
  - `REMEDIATION_REQUIRED`;
  - `PILOT_READY_WITH_LIMITATIONS`;
  - `PILOT_READY`.

## 3. Agent and model assignment

- OpenAI: `PRIMARY_EXECUTOR`.
- DeepSeek: `INDEPENDENT_AUDITOR`.
- Separate component or actor: `FORMAL_VALIDATOR`.
- Release Gatekeeper remains independent from all three execution outputs.

Inter-stage exchange must use strict typed JSON or YAML, immutable version identifiers,
content hashes, actor identity, timestamp, inputs, outputs, findings, limitations, and evidence references.

No model name, endpoint, commercial value, tax rate, cost, or other business parameter may be
hardcoded into the product runtime.

## 4. Severity and closure policy

| Severity | Meaning | Deadline rule |
|---|---|---|
| `P0` | active compromise, destructive corruption, direct cross-tenant or financial-integrity failure | immediate block |
| `P1` | exploitable critical/high defect or correctness failure that invalidates the pilot | must be fixed and independently retested |
| `P2` | material weakness with bounded compensating control | may remain only with explicit limitation and owner |
| `P3` | hardening or quality improvement | may be deferred with traceable issue |

Rules:

- open `P0` or `P1` means `NOT_READY`;
- CRITICAL and HIGH security findings must be closed;
- accepted P2/P3 items require owner, compensating control, expiry or review date, and evidence;
- every fix requires a regression test and exact-head retest;
- no severity reduction is permitted solely to meet 2026-07-08.

## 5. July 1–8 execution calendar

| Date | Primary output | Required independent checks |
|---|---|---|
| 2026-07-01 | recover and synchronize B1b; repair CI, manifest, and open review findings | Financial QA and AppSec review of changed head |
| 2026-07-02 | B1b merge candidate and closure evidence; minimum B2 implementation | golden, differential, property, and reconciliation checks |
| 2026-07-03 | bounded B2 closure; preview-only B6 scenarios | Actual/Scenario isolation and no-double-count verification |
| 2026-07-04 | B7-like internal security controls without external-access activation | tenant, session, file-abuse, secret, log, and dependency checks |
| 2026-07-05 | Red Team wave 1 | attack evidence, Blue detections, prioritized findings |
| 2026-07-06 | P0/P1 remediation and full regression | Purple replay and independent closure review |
| 2026-07-07 | Red Team wave 2; recovery and rollback drills; assurance evidence package | exact-head review, manifest, SBOM, OSV, restore proof |
| 2026-07-08 | reserve, final immutable audit, and pilot verdict | Formal Validator plus independent Release Gatekeeper |

This schedule does not authorize Macro-stage C. B8-like closure activities are performed as
Stage B internal QA/security evidence only.

## 6. Mandatory test portfolio

- Foundation CI and accumulated regression suite;
- OSS Admission, official registries, OSV, license, SBOM, and provenance;
- SAST, secret scan, workflow-permission and pinned-action checks;
- financial golden, property-based, differential, mutation, replay, and reconciliation tests;
- fuzzing for files, schemas, timestamps, Decimal limits, expression limits, and typed states;
- tenant-isolation and authorization tests;
- invitation, session expiry, revocation, suspension, and recovery tests;
- Actual/Scenario non-mutation tests;
- Evidence Chain integrity and forged-proof rejection;
- backup, restore, retry, dead-letter, and rollback drills;
- marketplace-write capability absence tests.

## 7. Pilot boundaries

The July 8 candidate must remain:

- invite-only or approved-request only;
- pseudonymous;
- free for initial testers;
- minimized with respect to personal data;
- transparent about consent, withdrawal, deletion, and processing;
- read-only toward marketplaces;
- synthetic-only unless a separate real-data gate is explicitly approved;
- without production credentials;
- without public registration;
- without activated marketplace write methods.

## 8. Evidence package

The final package must include:

- exact candidate commit and reviewed head;
- test commands, run IDs, results, and immutable hashes;
- Red Team attack catalogue and findings;
- Blue Team detection and response evidence;
- Purple Team replay records;
- IV&V traceability matrix;
- AppSec report and threat-model delta;
- independent Financial QA oracle report;
- SBOM, OSV, license, provenance, and secret-scan evidence;
- open-risk register with P2/P3 ownership;
- recovery and rollback proof;
- unresolved review-thread count;
- Formal Validator result;
- Release Gatekeeper verdict.

## 9. Exit criteria for 2026-07-08

All of the following are mandatory for `PILOT_READY`:

1. zero open P0 and P1 findings;
2. all CRITICAL and HIGH security findings independently closed;
3. QA score at least `98/100`;
4. Foundation and OSS Admission checks green on the exact reviewed head;
5. artifact-manifest equality passes;
6. approved financial golden oracle and differential suite pass;
7. row and aggregate reconciliation checks pass for admitted synthetic fixtures;
8. Actual and Scenario isolation passes;
9. tenant-isolation and authorization tests pass for implemented internal surfaces;
10. no marketplace write capability or production credential exists;
11. recovery bundle, restore test, and rollback evidence pass;
12. unresolved review threads equal zero;
13. all P2/P3 limitations are explicit and owned;
14. Formal Validator passes;
15. independent Release Gatekeeper issues `PILOT_READY`.

Failure of any mandatory criterion produces `REMEDIATION_REQUIRED` or `NOT_READY`.
Production remains `RELEASE_BLOCKED` until a separately approved Macro-stage C production gate.

## 10. Scope-freeze rule

Through 2026-07-08, new functionality is admitted only when it:

- closes a P0/P1 finding;
- is required for correctness, security, recovery, or the core pilot flow; or
- replaces work of equal or greater scope.

All other features are deferred.
