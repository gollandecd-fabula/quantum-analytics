# Quantum — Runtime Persistence Bridge Foundation v1

**Unit:** `P2.3 SYNTHETIC_RUNTIME_PERSISTENCE_BRIDGE`  
**Risk class:** `R3`  
**State:** `IN_DEVELOPMENT`  
**Release:** `RELEASE_BLOCKED`

## Scope

P2.3 connects the process-local P2.1 runtime state to the P2.2 attested SQLite checkpoint repository for synthetic testing only. It does not replace a live runtime store and does not activate restored identities.

## Atomic export

The exporter acquires the runtime store lock, verifies every secondary index, converts immutable runtime records to the persistent schema, and saves one attested checkpoint. The returned bridge checkpoint includes the external receipt-attestation SHA-256 that must be retained outside SQLite.

Terminal invites are excluded from checkpoints because the runtime removes their secret verifier after acceptance. Invite history remains represented by metadata-only audit events. Issued invites remain checkpointed because their verifier is still required.

## Detached quarantine restore

Restore always creates a new detached store. The caller must provide:

- the exact attested checkpoint receipt;
- the externally retained receipt-attestation SHA-256;
- the exact expected tenant set;
- a minimum acceptable checkpoint timestamp;
- a bounded maximum checkpoint age.

The restored store is quarantined:

- active or provisioning tenants become suspended;
- active or invited accounts become suspended;
- every account authentication epoch is incremented;
- active memberships become suspended;
- all sessions become revoked;
- issued invites become revoked.

No API exists to swap the restored store into a live runtime or reactivate principals.

## Integrity boundary

Export rejects mismatched tenant-alias, pseudonym, membership, and session-digest indexes. Restore rebuilds those indexes from canonical primary records and rejects duplicate aliases, pseudonyms, memberships, unknown audit event types, tenant-set mismatches, stale receipts, rollback attempts, and attestation mismatches.

Only the exact reviewed runtime store and attested repository classes are accepted. Subclass overrides are rejected at this stage.

## Limitations and blockers

The bridge remains synthetic-only. Production use still requires a durable external attestation store, encryption at rest, a production multi-instance database, transaction coordination with live commands, a separately approved quarantine activation workflow, real-data restore rehearsal, and independent exact-head review.

## Definition of Done

1. 28 focused bridge tests pass;
2. combined P2.2 and P2.3 regression suite passes;
3. compilation passes;
4. immutable manifest R33 validates;
5. Foundation CI and OSS Admission CI pass on the exact head;
6. no unresolved internal P0/P1 findings or review threads remain.

Protected-main merge, deployment, real-data processing, and release remain separately blocked.
