# Quantum — Multi-User Runtime Foundation v1

**Unit:** `P2.1 AUTHENTICATION_AND_TENANCY_RUNTIME`  
**Date:** 2026-07-03  
**Risk class:** `R3`  
**State:** `IN_DEVELOPMENT`  
**Release:** `RELEASE_BLOCKED`

## 1. Scope

P2.1 converts the P2.0 identity and tenant contracts into an internal service runtime. The authoritative implementation after security remediation R4 is `src/quantum/pilot/runtime_v3.py`; `runtime.py` and `runtime_v2.py` are retained only as reviewed historical baselines. It does not expose authentication over HTTP and does not authorize real users.

The runtime implements the closed pilot sequence:

`operator bootstrap → owner invite → pseudonymous account → tenant membership → authentication → tenant-scoped authorization → session revocation or credential recovery`.

## 2. Credential boundary

The runtime accepts only a credential backend that identifies itself as `argon2id`. Encoded verifiers must begin with `$argon2id$`; malformed output, plaintext-like output, backend exceptions and non-boolean verification results fail closed.

The repository stores verifier records only. Passwords, invite secrets and recovery keys are accepted transiently by service methods and are never written to account, audit or session records.

No production Argon2id adapter is included in P2.1. Tests use an explicitly test-only adapter. Real-user onboarding remains blocked until a reviewed production adapter is integrated.

## 3. Invite and account lifecycle

Tenant bootstrap is an internal operator action and creates one owner invite. Additional invites require a live `TENANT_OWNER` session with `MANAGE_MEMBERS`.

Invites:

- cannot be accepted before their issue time;
- are one-time;
- expire after a configured interval between one minute and seven days;
- store only an Argon2id verifier;
- fail closed on replay, expiration, wrong secret or inactive tenant.

Invite acceptance creates a pseudonymous account and one tenant membership atomically. Pseudonyms are unique case-insensitively. Direct identifier fields are absent.

## 4. Session security

Authentication returns a 256-bit bearer token once. The process-local store retains only its SHA-256 digest mapped to an internal session record.

Each authorization checks current:

- session status;
- account status and authentication epoch;
- membership status and role;
- tenant status and tenant identifier;
- absolute issue and expiry times;
- requested permission.

Sessions have a one-hour default lifetime and a hard maximum of twelve hours. Authentication, revocation and recovery reject time regressions. Individual revocation takes effect immediately.

Credential recovery increments `authentication_epoch`, supersedes old password and recovery verifier records, and revokes all active sessions for the account. Neither previous password nor previous recovery material may be reused in either new credential purpose.

## 5. Tenant isolation

Authentication failures do not reveal whether a pseudonym, password, tenant or membership was incorrect. Authorization uses an explicit tenant identifier and fails closed on mismatch.

Member invites require an authorized owner session. Viewer and analyst sessions cannot create members.

## 6. Audit and resource boundary

The runtime records immutable in-process event objects containing identifiers and event codes only. Passwords, recovery keys, invite secrets and bearer tokens are excluded.

The in-process audit list is not a production audit log. Persistent append-only audit storage remains mandatory before real users. Runtime v3 applies validated hard limits to tenants, accounts, memberships, invites, sessions, verifier records and audit events. Credentials and session authority are validated under the same lock before capacity is disclosed. Capacity is then checked before mutation, and expired or revoked session records are pruned before new session issuance.

## 7. Current limitations

P2.1 intentionally does not provide:

- persistent identity or session storage;
- a production Argon2id implementation;
- authentication rate limiting;
- HTTP cookies, CSRF controls or browser endpoints;
- operator MFA;
- backup and restore;
- multi-instance session consistency;
- real-user activation;
- deploy or release.

These limitations are explicit release blockers rather than hidden assumptions.

## 8. Definition of Done

P2.1 is internally complete when:

1. 36 focused runtime_v3 regressions pass;
2. session tokens are not stored in plaintext;
3. invite replay and concurrent double acceptance fail closed;
4. tenant-owner authorization is required for member invites;
5. credential recovery invalidates previous credentials and sessions;
6. no direct identifier fields exist in the account contract;
7. Foundation CI and OSS Admission CI pass on the exact head;
8. immutable manifest overlay R26 validates;
9. no unresolved internal P0/P1 findings or review threads remain.

Protected-main merge, deployment and real-user activation remain separately gated.
