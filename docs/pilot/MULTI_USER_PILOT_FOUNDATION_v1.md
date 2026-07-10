# Quantum — Multi-User Pilot Foundation v1

**Unit:** `P2.0 MULTI_USER_PILOT_FOUNDATION`  
**Date:** 2026-07-03  
**Risk class:** `R3`  
**State:** `IN_DEVELOPMENT`  
**Release:** `RELEASE_BLOCKED`

## 1. Decision

Quantum moves from the Windows loopback single-user pilot to a separate hosted multi-user pilot track. The local package remains a separate deployment profile and is not converted into a shared server.

The multi-user pilot is a closed, free testing program for the first clients. Access is only by invitation or an approved request. Each tester receives a personal cabinet backed by a pseudonymous account.

## 2. Trust boundaries

The modular monolith is divided into independent bounded contexts:

1. **Identity** — pseudonymous account, credential reference, recovery reference, invite lifecycle and session principal.
2. **Tenancy** — tenant lifecycle, membership, role and fail-closed tenant scope.
3. **Consent and privacy** — versioned consent evidence, withdrawal, deletion request and retention enforcement.
4. **Ingestion** — quarantine, validation, admission, immutable original and Evidence Chain.
5. **Analytics** — tenant-scoped calculations only.
6. **Learning** — private per-tenant outcome loop by default.
7. **Operations** — service health and audit metadata without access to tenant raw data by default.

Identity and tenancy must not be implemented inside ingestion. Every business record and every business query carries an explicit `tenant_id`. Missing or mismatched tenant scope is a hard denial.

## 3. Registration and recovery

The pilot registration surface accepts only:

- pseudonym;
- password;
- recovery key.

The core flow does not request or store full name, phone, email, postal address or social-network identity. The password and recovery key are never stored in plaintext. The approved password-hashing algorithm is Argon2id. The recovery key is displayed once and only a hardened verifier is stored.

There is no email password reset. Account recovery uses the recovery key and produces a fully audited credential rotation. Every credential rotation increments the account `authentication_epoch`; all sessions issued under an earlier epoch become invalid immediately.

## 4. Roles and sessions

Initial tenant roles are deliberately minimal:

- `TENANT_OWNER` — manage tenant membership and tenant data lifecycle;
- `TENANT_ANALYST` — upload admitted data and run analytics;
- `TENANT_VIEWER` — read approved analytics.

A session is bound to one active tenant. A role in tenant A never grants access to tenant B. The pilot operator is not a cross-tenant data superuser and cannot read raw tenant data by default.

Authorization is evaluated against the current session, account, membership and tenant records on every request. A revoked session, revoked account, suspended membership or suspended tenant is denied immediately; cached session claims are not sufficient. Sessions are invalid before their issue time, expire absolutely, and may not exceed 12 hours.

## 5. Data protection

Before any real tester is admitted:

- the personal-data operator must be formally defined;
- the required Roskomnadzor notification must be completed;
- production data residency in the Russian Federation must be confirmed;
- TLS and encryption at rest must be enabled;
- consent, withdrawal and deletion flows must pass end-to-end tests;
- backup and restore rehearsal must pass.

Third-party telemetry is disabled. Raw IP addresses are not persisted. Raw commercial data is not sent to external AI or analytics services.

## 6. Learning boundary

Learning is private per tenant by default. Cross-tenant raw training is forbidden. Global learning is disabled in this unit.

A future global model may consume only aggregated, depersonalized business events under a separately approved contract. Financial formulas, data contracts and safety policies cannot be changed by self-learning. Governed changes require versioned review and explicit approval.

## 7. Explicit exclusions

This unit does not authorize:

- public self-registration;
- billing;
- mobile applications;
- marketplace writes;
- email authentication;
- cross-tenant raw-data analytics;
- global online learning;
- protected-main merge;
- deployment or production release.

## 8. Definition of Done

`P2.0` is complete only when:

1. the machine-readable contract validates;
2. identity and tenancy domain invariants have regression tests;
3. cross-tenant authorization attempts fail closed;
4. no direct identifier is required by the account model;
5. Argon2id is the only admitted credential algorithm;
6. credential rotation invalidates all prior sessions;
7. individual session revocation denies immediately;
8. marketplace writes remain disabled;
9. the integrated artifact manifest matches the exact branch head;
10. Foundation CI and security tests pass;
11. an independent exact-head review reports zero open P0/P1 findings.

Real-user onboarding remains separately gated and requires explicit approval.
