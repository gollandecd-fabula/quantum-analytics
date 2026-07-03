from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
import hashlib
import tempfile
import unittest

from quantum.pilot.identity_contracts import (
    AccountStatus,
    InviteStatus,
    MembershipStatus,
    PseudonymousAccount,
    SessionPrincipal,
    SessionStatus,
    Tenant,
    TenantInvite,
    TenantMembership,
    TenantRole,
    TenantStatus,
)
from quantum.pilot.persistence_v2 import (
    AttestedSqlitePilotIdentityRepository,
)
from quantum.pilot.runtime import (
    AuditEventType,
    CredentialVerifierRecord,
    InMemoryPilotIdentityStore,
    PilotAuditEvent,
    VerifierPurpose,
)
from quantum.pilot.runtime_persistence_bridge import (
    DetachedRestoreGuard,
    RuntimePersistenceBridgeError,
    SyntheticRuntimePersistenceBridge,
)


NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)


def runtime_verifier(
    record_id: str,
    purpose: VerifierPurpose,
) -> CredentialVerifierRecord:
    return CredentialVerifierRecord(
        record_id=record_id,
        purpose=purpose,
        algorithm="argon2id",
        verifier="$argon2id$test$" + hashlib.sha256(record_id.encode()).hexdigest(),
        created_at=NOW,
    )


def sample_store() -> InMemoryPilotIdentityStore:
    tenant = Tenant("tenant-a", "tenant-alpha", TenantStatus.ACTIVE, NOW)
    password = runtime_verifier("verifier-password", VerifierPurpose.PASSWORD)
    recovery = runtime_verifier("verifier-recovery", VerifierPurpose.RECOVERY)
    invite_verifier = runtime_verifier("verifier-invite", VerifierPurpose.INVITE)
    account = PseudonymousAccount(
        "account-a", "owner_alpha", password.record_id, recovery.record_id,
        "argon2id", 3, AccountStatus.ACTIVE, NOW,
    )
    membership = TenantMembership(
        "membership-a", tenant.tenant_id, account.account_id,
        TenantRole.TENANT_OWNER, MembershipStatus.ACTIVE, NOW,
    )
    invite = TenantInvite(
        "invite-a", tenant.tenant_id, TenantRole.TENANT_VIEWER,
        invite_verifier.record_id, InviteStatus.ISSUED,
        NOW, NOW + timedelta(hours=1),
    )
    session = SessionPrincipal(
        "session-a", account.account_id, tenant.tenant_id,
        membership.membership_id, membership.role,
        account.authentication_epoch, SessionStatus.ACTIVE,
        NOW, NOW + timedelta(hours=1),
    )
    digest = hashlib.sha256(b"synthetic-session-token").hexdigest()
    audit = PilotAuditEvent(
        "audit-a", AuditEventType.SESSION_ISSUED,
        account.account_id, tenant.tenant_id, session.session_id,
        NOW, ("synthetic",),
    )
    store = InMemoryPilotIdentityStore()
    with store._lock:
        store._tenants = {tenant.tenant_id: tenant}
        store._tenant_alias_owners = {tenant.tenant_alias.casefold(): tenant.tenant_id}
        store._accounts = {account.account_id: account}
        store._pseudonym_owners = {account.pseudonym.casefold(): account.account_id}
        store._memberships = {membership.membership_id: membership}
        store._membership_by_tenant_account = {
            (tenant.tenant_id, account.account_id): membership.membership_id
        }
        store._invites = {invite.invite_id: invite}
        store._sessions = {session.session_id: session}
        store._session_digest_owners = {digest: session.session_id}
        store._verifiers = {
            item.record_id: item for item in (password, recovery, invite_verifier)
        }
        store._audit_events = [audit]
    return store


class RuntimePersistenceBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "bridge.db"
        self.repository = AttestedSqlitePilotIdentityRepository(self.path)
        self.repository.initialize()
        self.bridge = SyntheticRuntimePersistenceBridge()
        self.store = sample_store()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def checkpoint(self):
        return self.bridge.save_checkpoint(
            repository=self.repository,
            store=self.store,
            checkpoint_id="checkpoint-a",
            created_at=NOW + timedelta(minutes=5),
        )

    def guard(self, checkpoint, **changes):
        values = {
            "expected_attestation_sha256": checkpoint.external_attestation_sha256,
            "expected_tenant_ids": ("tenant-a",),
            "minimum_checkpoint_created_at": NOW,
            "maximum_checkpoint_age": timedelta(days=1),
        }
        values.update(changes)
        return DetachedRestoreGuard(**values)

    def test_capture_maps_every_collection(self):
        state = self.bridge.capture_state(self.store)
        self.assertEqual(len(state.tenants), 1)
        self.assertEqual(len(state.accounts), 1)
        self.assertEqual(len(state.memberships), 1)
        self.assertEqual(len(state.invites), 1)
        self.assertEqual(len(state.sessions), 1)
        self.assertEqual(len(state.verifiers), 3)
        self.assertEqual(len(state.session_token_digests), 1)
        self.assertEqual(len(state.audit_events), 1)

    def test_capture_rejects_non_store(self):
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "RUNTIME_STORE_REQUIRED"):
            self.bridge.capture_state(object())

    def test_capture_rejects_alias_index_mismatch(self):
        self.store._tenant_alias_owners = {}
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "RUNTIME_TENANT_ALIAS_INDEX_MISMATCH"):
            self.bridge.capture_state(self.store)

    def test_capture_rejects_pseudonym_index_mismatch(self):
        self.store._pseudonym_owners = {}
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "RUNTIME_PSEUDONYM_INDEX_MISMATCH"):
            self.bridge.capture_state(self.store)

    def test_capture_rejects_membership_index_mismatch(self):
        self.store._membership_by_tenant_account = {}
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "RUNTIME_MEMBERSHIP_INDEX_MISMATCH"):
            self.bridge.capture_state(self.store)

    def test_capture_rejects_missing_session_digest(self):
        self.store._session_digest_owners = {}
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "RUNTIME_SESSION_DIGEST_INDEX_MISMATCH"):
            self.bridge.capture_state(self.store)

    def test_checkpoint_returns_external_attestation(self):
        checkpoint = self.checkpoint()
        self.assertEqual(checkpoint.external_attestation_sha256, checkpoint.receipt.attestation_sha256)
        self.assertEqual(checkpoint.tenant_count, 1)
        self.assertEqual(checkpoint.account_count, 1)
        self.assertEqual(checkpoint.session_count, 1)
        self.assertEqual(checkpoint.excluded_terminal_invite_count, 0)

    def test_checkpoint_rejects_non_attested_repository(self):
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "ATTESTED_REPOSITORY_REQUIRED"):
            self.bridge.save_checkpoint(
                repository=object(), store=self.store,
                checkpoint_id="checkpoint-a", created_at=NOW,
            )

    def test_checkpoint_rejects_repository_subclass(self):
        class RepositorySubclass(AttestedSqlitePilotIdentityRepository):
            pass
        repository = RepositorySubclass(Path(self.tmp.name) / "subclass.db")
        repository.initialize()
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "ATTESTED_REPOSITORY_REQUIRED"):
            self.bridge.save_checkpoint(
                repository=repository, store=self.store,
                checkpoint_id="checkpoint-subclass", created_at=NOW,
            )

    def test_capture_rejects_store_subclass(self):
        class StoreSubclass(InMemoryPilotIdentityStore):
            pass
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "RUNTIME_STORE_REQUIRED"):
            self.bridge.capture_state(StoreSubclass())

    def test_restore_requires_guard(self):
        checkpoint = self.checkpoint()
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "RESTORE_GUARD_REQUIRED"):
            self.bridge.restore_quarantined(
                repository=self.repository, receipt=checkpoint.receipt,
                guard=object(), restored_at=NOW + timedelta(minutes=6),
            )

    def test_restore_rejects_attestation_mismatch(self):
        checkpoint = self.checkpoint()
        guard = self.guard(checkpoint, expected_attestation_sha256="0" * 64)
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "RESTORE_ATTESTATION_MISMATCH"):
            self.bridge.restore_quarantined(
                repository=self.repository, receipt=checkpoint.receipt,
                guard=guard, restored_at=NOW + timedelta(minutes=6),
            )

    def test_restore_rejects_rollback_before_minimum(self):
        checkpoint = self.checkpoint()
        guard = self.guard(
            checkpoint,
            minimum_checkpoint_created_at=NOW + timedelta(minutes=6),
        )
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "RESTORE_ROLLBACK_GUARD_REJECTED"):
            self.bridge.restore_quarantined(
                repository=self.repository, receipt=checkpoint.receipt,
                guard=guard, restored_at=NOW + timedelta(minutes=7),
            )

    def test_restore_rejects_time_regression(self):
        checkpoint = self.checkpoint()
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "RESTORE_TIME_REGRESSION"):
            self.bridge.restore_quarantined(
                repository=self.repository, receipt=checkpoint.receipt,
                guard=self.guard(checkpoint), restored_at=NOW,
            )

    def test_restore_rejects_stale_checkpoint(self):
        checkpoint = self.checkpoint()
        guard = self.guard(checkpoint, maximum_checkpoint_age=timedelta(minutes=1))
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "RESTORE_CHECKPOINT_TOO_OLD"):
            self.bridge.restore_quarantined(
                repository=self.repository, receipt=checkpoint.receipt,
                guard=guard, restored_at=NOW + timedelta(minutes=7),
            )

    def test_restore_rejects_tenant_set_mismatch(self):
        checkpoint = self.checkpoint()
        guard = self.guard(checkpoint, expected_tenant_ids=("tenant-other",))
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "RESTORE_TENANT_SET_MISMATCH"):
            self.bridge.restore_quarantined(
                repository=self.repository, receipt=checkpoint.receipt,
                guard=guard, restored_at=NOW + timedelta(minutes=6),
            )

    def test_restore_quarantines_authority(self):
        checkpoint = self.checkpoint()
        restored = self.bridge.restore_quarantined(
            repository=self.repository, receipt=checkpoint.receipt,
            guard=self.guard(checkpoint), restored_at=NOW + timedelta(minutes=6),
        )
        store = restored.store
        account = next(iter(store._accounts.values()))
        self.assertEqual(next(iter(store._tenants.values())).status, TenantStatus.SUSPENDED)
        self.assertEqual(account.status, AccountStatus.SUSPENDED)
        self.assertEqual(account.authentication_epoch, 4)
        self.assertEqual(next(iter(store._memberships.values())).status, MembershipStatus.SUSPENDED)
        self.assertEqual(next(iter(store._invites.values())).status, InviteStatus.REVOKED)
        self.assertEqual(next(iter(store._sessions.values())).status, SessionStatus.REVOKED)

    def test_restore_rebuilds_secondary_indexes(self):
        checkpoint = self.checkpoint()
        store = self.bridge.restore_quarantined(
            repository=self.repository, receipt=checkpoint.receipt,
            guard=self.guard(checkpoint), restored_at=NOW + timedelta(minutes=6),
        ).store
        self.assertEqual(store._tenant_alias_owners, {"tenant-alpha": "tenant-a"})
        self.assertEqual(store._pseudonym_owners, {"owner_alpha": "account-a"})
        self.assertEqual(store._membership_by_tenant_account, {("tenant-a", "account-a"): "membership-a"})
        self.assertEqual(set(store._session_digest_owners.values()), {"session-a"})

    def test_restore_does_not_mutate_source_store(self):
        checkpoint = self.checkpoint()
        before = self.bridge.capture_state(self.store)
        self.bridge.restore_quarantined(
            repository=self.repository, receipt=checkpoint.receipt,
            guard=self.guard(checkpoint), restored_at=NOW + timedelta(minutes=6),
        )
        self.assertEqual(self.bridge.capture_state(self.store), before)

    def test_restored_store_is_detached(self):
        checkpoint = self.checkpoint()
        restored = self.bridge.restore_quarantined(
            repository=self.repository, receipt=checkpoint.receipt,
            guard=self.guard(checkpoint), restored_at=NOW + timedelta(minutes=6),
        ).store
        restored._tenants.clear()
        self.assertEqual(len(self.store._tenants), 1)

    def test_quarantined_digest_differs_from_source(self):
        checkpoint = self.checkpoint()
        restored = self.bridge.restore_quarantined(
            repository=self.repository, receipt=checkpoint.receipt,
            guard=self.guard(checkpoint), restored_at=NOW + timedelta(minutes=6),
        )
        self.assertNotEqual(restored.source_state_sha256, restored.quarantined_state_sha256)

    def test_restore_rejects_unknown_audit_event_type(self):
        state = self.bridge.capture_state(self.store)
        bad = replace(state.audit_events[0], event_type="FUTURE_EVENT")
        state = replace(state, audit_events=(bad,))
        receipt = self.repository.save_checkpoint(
            checkpoint_id="checkpoint-unknown-audit", state=state,
            created_at=NOW + timedelta(minutes=5),
        )
        guard = DetachedRestoreGuard(
            expected_attestation_sha256=receipt.attestation_sha256,
            expected_tenant_ids=("tenant-a",),
            minimum_checkpoint_created_at=NOW,
            maximum_checkpoint_age=timedelta(days=1),
        )
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "PERSISTED_AUDIT_EVENT_UNSUPPORTED"):
            self.bridge.restore_quarantined(
                repository=self.repository, receipt=receipt,
                guard=guard, restored_at=NOW + timedelta(minutes=6),
            )

    def test_terminal_invites_are_excluded_from_checkpoint(self):
        accepted = replace(next(iter(self.store._invites.values())), status=InviteStatus.ACCEPTED)
        verifier_id = accepted.secret_verifier_record_id
        self.store._invites = {accepted.invite_id: accepted}
        self.store._verifiers.pop(verifier_id)
        checkpoint = self.checkpoint()
        self.assertEqual(checkpoint.excluded_terminal_invite_count, 1)
        state = self.repository.load_checkpoint(checkpoint.receipt)
        self.assertEqual(state.invites, ())
        restored = self.bridge.restore_quarantined(
            repository=self.repository, receipt=checkpoint.receipt,
            guard=self.guard(checkpoint), restored_at=NOW + timedelta(minutes=6),
        )
        self.assertEqual(restored.store._invites, {})
        self.assertEqual(restored.revoked_invite_count, 0)

    def test_issued_invite_is_revoked_on_restore(self):
        checkpoint = self.checkpoint()
        restored = self.bridge.restore_quarantined(
            repository=self.repository, receipt=checkpoint.receipt,
            guard=self.guard(checkpoint), restored_at=NOW + timedelta(minutes=6),
        )
        self.assertEqual(next(iter(restored.store._invites.values())).status, InviteStatus.REVOKED)
        self.assertEqual(restored.revoked_invite_count, 1)

    def test_guard_rejects_empty_tenant_set(self):
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "RESTORE_EXPECTED_TENANTS_INVALID"):
            DetachedRestoreGuard(
                expected_attestation_sha256="0" * 64,
                expected_tenant_ids=(),
                minimum_checkpoint_created_at=NOW,
                maximum_checkpoint_age=timedelta(days=1),
            )

    def test_guard_rejects_unbounded_age(self):
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "RESTORE_MAXIMUM_AGE_INVALID"):
            DetachedRestoreGuard(
                expected_attestation_sha256="0" * 64,
                expected_tenant_ids=("tenant-a",),
                minimum_checkpoint_created_at=NOW,
                maximum_checkpoint_age=timedelta(days=366),
            )

    def test_concurrent_captures_are_consistent(self):
        def capture(_):
            return self.bridge.capture_state(self.store)
        with ThreadPoolExecutor(max_workers=4) as pool:
            states = list(pool.map(capture, range(8)))
        self.assertTrue(all(state == states[0] for state in states))

    def test_checkpoint_database_contains_no_plaintext_token(self):
        self.checkpoint()
        self.assertNotIn(b"synthetic-session-token", self.path.read_bytes())


if __name__ == "__main__":
    unittest.main()
