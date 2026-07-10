# Quantum — Persistent Identity Repository Foundation v1

**Unit:** `P2.2 PERSISTENT_IDENTITY_REPOSITORY_FOUNDATION`  
**Date:** 2026-07-03  
**Risk class:** `R3`  
**State:** `IN_DEVELOPMENT`  
**Release:** `RELEASE_BLOCKED`

## 1. Scope

P2.2 adds a durable, normalized SQLite reference repository for synthetic identity and tenancy checkpoints. It is stacked on P2.1 and does not replace the process-local runtime store during live operations.

The repository proves persistence semantics, integrity checking, immutable checkpoint storage and backup/restore mechanics without authorizing real users or production credentials.

## 2. Persistence model

A checkpoint contains canonical tuples of:

- tenants;
- pseudonymous accounts;
- tenant memberships;
- invites;
- sessions;
- Argon2id verifier records;
- SHA-256 session-token digests;
- metadata-only audit events.

Every row is scoped by an immutable `checkpoint_id`. Cross-record references are validated in Python before persistence and reinforced by SQLite foreign keys and uniqueness constraints.

## 3. Integrity boundary

Each state is canonicalized and hashed with SHA-256. `save_checkpoint` returns a `CheckpointReceipt`. The digest from that receipt must be stored outside the database and supplied to every trusted load.

The digest stored inside SQLite is diagnostic only. It is not treated as a trust anchor because an attacker with database-admin access could rewrite both data and local metadata after removing triggers.

Checkpoint rows, schema metadata and audit rows are protected by update/delete rejection triggers. Record count and canonical digest are verified on load. Corrupt enum, timestamp, JSON and domain relations fail closed with typed errors.

## 4. Secret handling

The schema contains no password, recovery-key, invite-secret or bearer-token plaintext columns. Only Argon2id encoded verifiers and SHA-256 bearer-token digests are admitted.

The SQLite file is not encrypted. Therefore P2.2 is restricted to synthetic/local testing and cannot process real identity or commercial data.

## 5. Resource and file controls

Repository limits bound checkpoints and every collection per checkpoint. Audit codes are bounded. Distinct concurrent checkpoint writes use `BEGIN IMMEDIATE` and SQLite busy handling.

Database and backup files are hardened to POSIX mode `0600`. A file-backed database is mandatory; `:memory:` is rejected because the stage tests durability and backup semantics.

## 6. Backup boundary

The repository supports SQLite online backup to a separate file and requires an initialized source schema. The external checkpoint receipt is not embedded into the backup and must be retained separately.

This is a reference backup mechanism, not a completed real-data backup and disaster-recovery rehearsal.

## 7. Explicit blockers

Before hosted pilot persistence, Quantum still requires:

- encryption at rest with managed keys;
- a durable external receipt or signed checkpoint-root store;
- direct transactional integration with the runtime command path;
- a multi-instance production database backend;
- schema migrations and rollback policy;
- real-data backup and restore rehearsal;
- independent exact-head review.

## 8. Definition of Done

P2.2 is internally complete when:

1. all 24 repository regressions pass without resource warnings;
2. exact state round-trip and external-receipt verification pass;
3. append-only and tamper-detection tests pass;
4. concurrent checkpoint serialization passes;
5. plaintext bearer material is absent from the database;
6. backup/restore round-trip passes;
7. immutable manifest R27 validates;
8. Foundation CI and OSS Admission CI pass on the exact head;
9. no unresolved internal P0/P1 findings or review threads remain.

Protected-main merge, production persistence, deployment and real-user activation remain separately blocked.
