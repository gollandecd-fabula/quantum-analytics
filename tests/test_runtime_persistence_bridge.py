from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
import hashlib
import tempfile
import unittest

from quantum.pilot.identity_contracts import (
    AccountStatus, InviteStatus, MembershipStatus, PseudonymousAccount,
    SessionPrincipal, SessionStatus, Tenant, TenantInvite, TenantMembership,
    TenantRole, TenantStatus,
)
from quantum.pilot.persistence_v2 import AttestedSqlitePilotIdentityRepository
from quantum.pilot.runtime import (
    AuditEventType, CredentialVerifierRecord, InMemoryPilotIdentityStore,
    PilotAuditEvent, VerifierPurpose,
)
from quantum.pilot.runtime_persistence_bridge import (
    DetachedRestoreGuard, RuntimePersistenceBridgeError,
    SyntheticRuntimePersistenceBridge,
)

NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)


def verifier(record_id, purpose):
    return CredentialVerifierRecord(
        record_id, purpose, "argon2id",
        "$argon2id$test$" + hashlib.sha256(record_id.encode()).hexdigest(),
        NOW,
    )


def sample_store():
    tenant = Tenant("tenant-a", "tenant-alpha", TenantStatus.ACTIVE, NOW)
    password = verifier("verifier-password", VerifierPurpose.PASSWORD)
    recovery = verifier("verifier-recovery", VerifierPurpose.RECOVERY)
    invite_verifier = verifier("verifier-invite", VerifierPurpose.INVITE)
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
        membership.membership_id, membership.role, 3, SessionStatus.ACTIVE,
        NOW, NOW + timedelta(hours=1),
    )
    store = InMemoryPilotIdentityStore()
    with store._lock:
        store._tenants = {tenant.tenant_id: tenant}
        store._tenant_alias_owners = {"tenant-alpha": tenant.tenant_id}
        store._accounts = {account.account_id: account}
        store._pseudonym_owners = {"owner_alpha": account.account_id}
        store._memberships = {membership.membership_id: membership}
        store._membership_by_tenant_account = {
            (tenant.tenant_id, account.account_id): membership.membership_id
        }
        store._invites = {invite.invite_id: invite}
        store._sessions = {session.session_id: session}
        store._session_digest_owners = {
            hashlib.sha256(b"synthetic-session-token").hexdigest(): session.session_id
        }
        store._verifiers = {
            item.record_id: item for item in (password, recovery, invite_verifier)
        }
        store._audit_events = [PilotAuditEvent(
            "audit-a", AuditEventType.SESSION_ISSUED, account.account_id,
            tenant.tenant_id, session.session_id, NOW, ("synthetic",),
        )]
    return store


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "bridge.db"
        self.repo = AttestedSqlitePilotIdentityRepository(self.path)
        self.repo.initialize()
        self.bridge = SyntheticRuntimePersistenceBridge()
        self.store = sample_store()

    def tearDown(self):
        self.tmp.cleanup()

    def checkpoint(self):
        return self.bridge.save_checkpoint(
            repository=self.repo, store=self.store,
            checkpoint_id="checkpoint-a",
            created_at=NOW + timedelta(minutes=5),
        )

    def guard(self, checkpoint, **changes):
        data = dict(
            expected_attestation_sha256=checkpoint.external_attestation_sha256,
            expected_tenant_ids=("tenant-a",),
            minimum_checkpoint_created_at=NOW,
            maximum_checkpoint_age=timedelta(days=1),
        )
        data.update(changes)
        return DetachedRestoreGuard(**data)

    def restore(self, checkpoint=None, guard=None, restored_at=None):
        checkpoint = checkpoint or self.checkpoint()
        return self.bridge.restore_quarantined(
            repository=self.repo,
            receipt=checkpoint.receipt,
            guard=guard or self.guard(checkpoint),
            restored_at=restored_at or NOW + timedelta(minutes=6),
        )

    def test_capture_collections(self):
        state = self.bridge.capture_state(self.store)
        self.assertEqual(
            tuple(map(len, (
                state.tenants, state.accounts, state.memberships,
                state.invites, state.sessions, state.session_token_digests,
                state.audit_events,
            ))),
            (1, 1, 1, 1, 1, 1, 1),
        )
        self.assertEqual(len(state.verifiers), 3)

    def test_checkpoint_metadata(self):
        checkpoint = self.checkpoint()
        self.assertEqual(
            checkpoint.external_attestation_sha256,
            checkpoint.receipt.attestation_sha256,
        )
        self.assertEqual(
            (checkpoint.tenant_count, checkpoint.account_count,
             checkpoint.session_count, checkpoint.excluded_terminal_invite_count),
            (1, 1, 1, 0),
        )

    def test_quarantine_transform(self):
        result = self.restore()
        store = result.store
        account = next(iter(store._accounts.values()))
        self.assertEqual(next(iter(store._tenants.values())).status, TenantStatus.SUSPENDED)
        self.assertEqual((account.status, account.authentication_epoch), (AccountStatus.SUSPENDED, 4))
        self.assertEqual(next(iter(store._memberships.values())).status, MembershipStatus.SUSPENDED)
        self.assertEqual(next(iter(store._sessions.values())).status, SessionStatus.REVOKED)
        self.assertEqual(next(iter(store._invites.values())).status, InviteStatus.REVOKED)

    def test_secondary_indexes_rebuilt(self):
        store = self.restore().store
        self.assertEqual(store._tenant_alias_owners, {"tenant-alpha": "tenant-a"})
        self.assertEqual(store._pseudonym_owners, {"owner_alpha": "account-a"})
        self.assertEqual(store._membership_by_tenant_account, {("tenant-a", "account-a"): "membership-a"})
        self.assertEqual(set(store._session_digest_owners.values()), {"session-a"})

    def test_source_is_unchanged_and_detached(self):
        before = self.bridge.capture_state(self.store)
        restored = self.restore().store
        restored._tenants.clear()
        self.assertEqual(self.bridge.capture_state(self.store), before)
        self.assertEqual(len(self.store._tenants), 1)

    def test_terminal_invite_is_excluded(self):
        invite = replace(next(iter(self.store._invites.values())), status=InviteStatus.ACCEPTED)
        self.store._invites = {invite.invite_id: invite}
        self.store._verifiers.pop(invite.secret_verifier_record_id)
        checkpoint = self.checkpoint()
        self.assertEqual(checkpoint.excluded_terminal_invite_count, 1)
        self.assertEqual(self.repo.load_checkpoint(checkpoint.receipt).invites, ())
        self.assertEqual(self.restore(checkpoint).store._invites, {})

    def test_issued_invite_is_revoked(self):
        self.assertEqual(
            next(iter(self.restore().store._invites.values())).status,
            InviteStatus.REVOKED,
        )

    def test_unknown_audit_event_is_rejected(self):
        state = self.bridge.capture_state(self.store)
        state = replace(
            state,
            audit_events=(replace(state.audit_events[0], event_type="FUTURE_EVENT"),),
        )
        receipt = self.repo.save_checkpoint(
            checkpoint_id="checkpoint-future",
            state=state,
            created_at=NOW + timedelta(minutes=5),
        )
        guard = DetachedRestoreGuard(
            receipt.attestation_sha256, ("tenant-a",), NOW, timedelta(days=1)
        )
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "PERSISTED_AUDIT_EVENT_UNSUPPORTED"):
            self.bridge.restore_quarantined(
                repository=self.repo, receipt=receipt, guard=guard,
                restored_at=NOW + timedelta(minutes=6),
            )

    def test_concurrent_capture(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            states = list(pool.map(lambda _: self.bridge.capture_state(self.store), range(8)))
        self.assertTrue(all(state == states[0] for state in states))

    def test_plaintext_token_absent(self):
        self.checkpoint()
        self.assertNotIn(b"synthetic-session-token", self.path.read_bytes())

    def test_quarantine_digest_changes(self):
        result = self.restore()
        self.assertNotEqual(result.source_state_sha256, result.quarantined_state_sha256)

    def test_repository_subclass_rejected(self):
        class Subclass(AttestedSqlitePilotIdentityRepository):
            pass
        repo = Subclass(Path(self.tmp.name) / "subclass.db")
        repo.initialize()
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "ATTESTED_REPOSITORY_REQUIRED"):
            self.bridge.save_checkpoint(
                repository=repo, store=self.store,
                checkpoint_id="subclass", created_at=NOW,
            )

    def test_store_subclass_rejected(self):
        class Subclass(InMemoryPilotIdentityStore):
            pass
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, "RUNTIME_STORE_REQUIRED"):
            self.bridge.capture_state(Subclass())

    def test_bridge_checkpoint_is_attested(self):
        checkpoint = self.checkpoint()
        self.assertEqual(len(checkpoint.external_attestation_sha256), 64)


def _error_case(name, code, action):
    def test(self):
        checkpoint = None
        if name not in {"store_required", "alias_index", "pseudonym_index",
                        "membership_index", "digest_index", "repository_required",
                        "guard_empty", "guard_age"}:
            checkpoint = self.checkpoint()
        with self.assertRaisesRegex(RuntimePersistenceBridgeError, code):
            action(self, checkpoint)
    test.__name__ = f"test_error_{name}"
    setattr(BridgeTests, test.__name__, test)


_error_case("store_required", "RUNTIME_STORE_REQUIRED",
            lambda self, _: self.bridge.capture_state(object()))
_error_case("alias_index", "RUNTIME_TENANT_ALIAS_INDEX_MISMATCH",
            lambda self, _: (setattr(self.store, "_tenant_alias_owners", {}),
                             self.bridge.capture_state(self.store))[-1])
_error_case("pseudonym_index", "RUNTIME_PSEUDONYM_INDEX_MISMATCH",
            lambda self, _: (setattr(self.store, "_pseudonym_owners", {}),
                             self.bridge.capture_state(self.store))[-1])
_error_case("membership_index", "RUNTIME_MEMBERSHIP_INDEX_MISMATCH",
            lambda self, _: (setattr(self.store, "_membership_by_tenant_account", {}),
                             self.bridge.capture_state(self.store))[-1])
_error_case("digest_index", "RUNTIME_SESSION_DIGEST_INDEX_MISMATCH",
            lambda self, _: (setattr(self.store, "_session_digest_owners", {}),
                             self.bridge.capture_state(self.store))[-1])
_error_case("repository_required", "ATTESTED_REPOSITORY_REQUIRED",
            lambda self, _: self.bridge.save_checkpoint(
                repository=object(), store=self.store,
                checkpoint_id="bad", created_at=NOW))
_error_case("guard_required", "RESTORE_GUARD_REQUIRED",
            lambda self, cp: self.bridge.restore_quarantined(
                repository=self.repo, receipt=cp.receipt,
                guard=object(), restored_at=NOW + timedelta(minutes=6)))
_error_case("attestation", "RESTORE_ATTESTATION_MISMATCH",
            lambda self, cp: self.restore(
                cp, self.guard(cp, expected_attestation_sha256="0" * 64)))
_error_case("rollback", "RESTORE_ROLLBACK_GUARD_REJECTED",
            lambda self, cp: self.restore(
                cp, self.guard(cp, minimum_checkpoint_created_at=NOW + timedelta(minutes=6))))
_error_case("time_regression", "RESTORE_TIME_REGRESSION",
            lambda self, cp: self.restore(cp, restored_at=NOW))
_error_case("stale", "RESTORE_CHECKPOINT_TOO_OLD",
            lambda self, cp: self.restore(
                cp, self.guard(cp, maximum_checkpoint_age=timedelta(minutes=1)),
                NOW + timedelta(minutes=7)))
_error_case("tenant_set", "RESTORE_TENANT_SET_MISMATCH",
            lambda self, cp: self.restore(
                cp, self.guard(cp, expected_tenant_ids=("tenant-other",))))
_error_case("guard_empty", "RESTORE_EXPECTED_TENANTS_INVALID",
            lambda self, _: DetachedRestoreGuard(
                "0" * 64, (), NOW, timedelta(days=1)))
_error_case("guard_age", "RESTORE_MAXIMUM_AGE_INVALID",
            lambda self, _: DetachedRestoreGuard(
                "0" * 64, ("tenant-a",), NOW, timedelta(days=366)))


if __name__ == "__main__":
    unittest.main()
