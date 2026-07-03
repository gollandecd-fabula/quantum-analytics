from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
import hashlib
import sqlite3
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
from quantum.pilot.persistence import (
    PersistedVerifier,
    PersistentAuditEvent,
    PersistentPilotState,
    PersistenceLimits,
    PilotPersistenceError,
    SessionTokenDigestRecord,
    SqlitePilotIdentityRepository,
    VerifierPurpose,
    state_sha256,
)

NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)


def verifier(record_id: str, purpose: VerifierPurpose) -> PersistedVerifier:
    return PersistedVerifier(
        record_id=record_id,
        purpose=purpose,
        algorithm="argon2id",
        verifier="$argon2id$test$" + hashlib.sha256(record_id.encode()).hexdigest(),
        created_at=NOW,
    )


def sample_state() -> PersistentPilotState:
    tenant = Tenant("tenant-a", "tenant-alpha", TenantStatus.ACTIVE, NOW)
    password = verifier("verifier-password", VerifierPurpose.PASSWORD)
    recovery = verifier("verifier-recovery", VerifierPurpose.RECOVERY)
    invite_verifier = verifier("verifier-invite", VerifierPurpose.INVITE)
    account = PseudonymousAccount(
        "account-a",
        "owner_alpha",
        password.record_id,
        recovery.record_id,
        "argon2id",
        1,
        AccountStatus.ACTIVE,
        NOW,
    )
    membership = TenantMembership(
        "membership-a",
        tenant.tenant_id,
        account.account_id,
        TenantRole.TENANT_OWNER,
        MembershipStatus.ACTIVE,
        NOW,
    )
    invite = TenantInvite(
        "invite-a",
        tenant.tenant_id,
        TenantRole.TENANT_VIEWER,
        invite_verifier.record_id,
        InviteStatus.ISSUED,
        NOW,
        NOW + timedelta(hours=1),
    )
    session = SessionPrincipal(
        "session-a",
        account.account_id,
        tenant.tenant_id,
        membership.membership_id,
        membership.role,
        1,
        SessionStatus.ACTIVE,
        NOW,
        NOW + timedelta(hours=1),
    )
    digest = SessionTokenDigestRecord(
        session.session_id,
        hashlib.sha256(b"synthetic-session-token").hexdigest(),
    )
    audit = PersistentAuditEvent(
        "audit-a",
        "SESSION_ISSUED",
        account.account_id,
        tenant.tenant_id,
        session.session_id,
        NOW,
        ("synthetic",),
    )
    return PersistentPilotState(
        tenants=(tenant,),
        accounts=(account,),
        memberships=(membership,),
        invites=(invite,),
        sessions=(session,),
        verifiers=(password, recovery, invite_verifier),
        session_token_digests=(digest,),
        audit_events=(audit,),
    )


class PersistentIdentityRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "pilot.db"
        self.repo = SqlitePilotIdentityRepository(self.path)
        self.repo.initialize()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_round_trip_and_digest(self):
        state = sample_state()
        receipt = self.repo.save_checkpoint(
            checkpoint_id="checkpoint-a",
            state=state,
            created_at=NOW,
        )
        self.assertEqual(receipt.state_sha256, state_sha256(state))
        self.assertEqual(
            self.repo.load_checkpoint(
                "checkpoint-a", expected_state_sha256=receipt.state_sha256
            ),
            state,
        )

    def test_repository_is_explicitly_not_production_ready(self):
        status = self.repo.status()
        self.assertEqual(status.schema_version, 1)
        self.assertEqual(status.integrity_check, "ok")
        self.assertFalse(status.production_ready)
        self.assertFalse(status.encryption_at_rest)

    def test_file_database_is_required(self):
        with self.assertRaisesRegex(PilotPersistenceError, "FILE_DATABASE_REQUIRED"):
            SqlitePilotIdentityRepository(":memory:")

    def test_duplicate_checkpoint_is_rejected_without_mutation(self):
        state = sample_state()
        self.repo.save_checkpoint(checkpoint_id="checkpoint-a", state=state, created_at=NOW)
        with self.assertRaisesRegex(
            PilotPersistenceError,
            "CHECKPOINT_CONFLICT_OR_INVALID",
        ):
            self.repo.save_checkpoint(
                checkpoint_id="checkpoint-a",
                state=state,
                created_at=NOW + timedelta(minutes=1),
            )
        self.assertEqual(self.repo.status().checkpoint_count, 1)

    def test_checkpoint_rows_are_append_only(self):
        self.repo.save_checkpoint(
            checkpoint_id="checkpoint-a",
            state=sample_state(),
            created_at=NOW,
        )
        with closing(sqlite3.connect(self.path)) as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "UPDATE pilot_tenants SET tenant_alias = 'mutated' WHERE checkpoint_id = 'checkpoint-a'"
                )

    def test_tampering_is_detected(self):
        receipt = self.repo.save_checkpoint(
            checkpoint_id="checkpoint-a",
            state=sample_state(),
            created_at=NOW,
        )
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("DROP TRIGGER pilot_tenants_immutable_update")
            conn.execute(
                "UPDATE pilot_tenants SET tenant_alias = 'tampered' WHERE checkpoint_id = 'checkpoint-a'"
            )
            conn.commit()
        with self.assertRaisesRegex(
            PilotPersistenceError,
            "CHECKPOINT_DIGEST_MISMATCH",
        ):
            self.repo.load_checkpoint(
                "checkpoint-a", expected_state_sha256=receipt.state_sha256
            )

    def test_backup_restores_checkpoint(self):
        state = sample_state()
        receipt = self.repo.save_checkpoint(
            checkpoint_id="checkpoint-a", state=state, created_at=NOW
        )
        backup = Path(self.tmp.name) / "backup.db"
        self.repo.backup_to(backup)
        restored = SqlitePilotIdentityRepository(backup)
        self.assertEqual(
            restored.load_checkpoint(
                "checkpoint-a", expected_state_sha256=receipt.state_sha256
            ),
            state,
        )

    def test_plaintext_bearer_is_not_persisted(self):
        self.repo.save_checkpoint(
            checkpoint_id="checkpoint-a",
            state=sample_state(),
            created_at=NOW,
        )
        self.assertNotIn(b"synthetic-session-token", self.path.read_bytes())

    def test_session_requires_exactly_one_digest(self):
        state = sample_state()
        with self.assertRaisesRegex(
            PilotPersistenceError,
            "SESSION_DIGEST_CARDINALITY_INVALID",
        ):
            replace(state, session_token_digests=())

    def test_cross_tenant_session_reference_is_rejected(self):
        state = sample_state()
        bad_session = replace(state.sessions[0], tenant_id="tenant-other")
        with self.assertRaisesRegex(PilotPersistenceError, "SESSION_REFERENCE_INVALID"):
            replace(state, sessions=(bad_session,))

    def test_wrong_verifier_purpose_is_rejected(self):
        state = sample_state()
        password = next(
            item for item in state.verifiers
            if item.purpose is VerifierPurpose.PASSWORD
        )
        bad = replace(password, purpose=VerifierPurpose.RECOVERY)
        verifiers = tuple(
            bad if item.record_id == password.record_id else item
            for item in state.verifiers
        )
        with self.assertRaisesRegex(
            PilotPersistenceError,
            "ACCOUNT_CREDENTIAL_REFERENCE_INVALID",
        ):
            replace(state, verifiers=verifiers)

    def test_unknown_checkpoint_fails_closed(self):
        with self.assertRaisesRegex(PilotPersistenceError, "CHECKPOINT_NOT_FOUND"):
            self.repo.load_checkpoint(
                "missing-checkpoint", expected_state_sha256="0" * 64
            )

    def test_uninitialized_database_fails_closed(self):
        other = SqlitePilotIdentityRepository(Path(self.tmp.name) / "other.db")
        with self.assertRaisesRegex(PilotPersistenceError, "SCHEMA_NOT_INITIALIZED"):
            other.status()

    def test_state_digest_is_order_independent(self):
        state = sample_state()
        reordered = replace(state, verifiers=tuple(reversed(state.verifiers)))
        self.assertEqual(state_sha256(state), state_sha256(reordered))

    def test_external_receipt_detects_metadata_rewrite(self):
        state = sample_state()
        receipt = self.repo.save_checkpoint(
            checkpoint_id="checkpoint-a", state=state, created_at=NOW
        )
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("DROP TRIGGER pilot_checkpoints_immutable_update")
            conn.execute(
                "UPDATE pilot_checkpoints SET state_sha256 = ? WHERE checkpoint_id = ?",
                ("0" * 64, "checkpoint-a"),
            )
            conn.commit()
        with self.assertRaisesRegex(
            PilotPersistenceError, "CHECKPOINT_RECEIPT_MISMATCH"
        ):
            self.repo.load_checkpoint(
                "checkpoint-a",
                expected_state_sha256=receipt.state_sha256,
            )

    def test_corrupt_enum_is_typed_failure(self):
        receipt = self.repo.save_checkpoint(
            checkpoint_id="checkpoint-a", state=sample_state(), created_at=NOW
        )
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("DROP TRIGGER pilot_tenants_immutable_update")
            conn.execute(
                "UPDATE pilot_tenants SET status = 'UNKNOWN' WHERE checkpoint_id = 'checkpoint-a'"
            )
            conn.commit()
        with self.assertRaisesRegex(PilotPersistenceError, "PERSISTED_STATE_INVALID"):
            self.repo.load_checkpoint(
                "checkpoint-a", expected_state_sha256=receipt.state_sha256
            )

    def test_repository_limits_fail_before_insert(self):
        limited = SqlitePilotIdentityRepository(
            Path(self.tmp.name) / "limited.db",
            limits=PersistenceLimits(max_tenants=1),
        )
        limited.initialize()
        state = sample_state()
        other = replace(
            state.tenants[0], tenant_id="tenant-b", tenant_alias="tenant-beta"
        )
        with self.assertRaisesRegex(PilotPersistenceError, "TENANT_CAPACITY_EXCEEDED"):
            limited.save_checkpoint(
                checkpoint_id="checkpoint-a",
                state=replace(state, tenants=(state.tenants[0], other)),
                created_at=NOW,
            )
        self.assertEqual(limited.status().checkpoint_count, 0)

    def test_database_permissions_are_restricted(self):
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_backup_requires_initialized_source(self):
        source = SqlitePilotIdentityRepository(Path(self.tmp.name) / "blank.db")
        with self.assertRaisesRegex(PilotPersistenceError, "SCHEMA_NOT_INITIALIZED"):
            source.backup_to(Path(self.tmp.name) / "blank-backup.db")

    def test_external_receipt_is_required(self):
        self.repo.save_checkpoint(
            checkpoint_id="checkpoint-a", state=sample_state(), created_at=NOW
        )
        with self.assertRaisesRegex(
            PilotPersistenceError, "EXPECTED_CHECKPOINT_DIGEST_REQUIRED"
        ):
            self.repo.load_checkpoint("checkpoint-a")

    def test_concurrent_distinct_checkpoints_are_serialized(self):
        state = sample_state()

        def save(index: int):
            repository = SqlitePilotIdentityRepository(self.path)
            return repository.save_checkpoint(
                checkpoint_id=f"checkpoint-{index}",
                state=state,
                created_at=NOW + timedelta(seconds=index),
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(save, (1, 2)))
        self.assertEqual(len(receipts), 2)
        self.assertEqual(self.repo.status().checkpoint_count, 2)

    def test_checkpoint_capacity_is_bounded(self):
        limited = SqlitePilotIdentityRepository(
            Path(self.tmp.name) / "checkpoint-limited.db",
            limits=PersistenceLimits(max_checkpoints=1),
        )
        limited.initialize()
        state = sample_state()
        limited.save_checkpoint(
            checkpoint_id="checkpoint-1", state=state, created_at=NOW
        )
        with self.assertRaisesRegex(
            PilotPersistenceError, "CHECKPOINT_CAPACITY_EXCEEDED"
        ):
            limited.save_checkpoint(
                checkpoint_id="checkpoint-2",
                state=state,
                created_at=NOW + timedelta(seconds=1),
            )
        self.assertEqual(limited.status().checkpoint_count, 1)

    def test_state_items_are_typed(self):
        with self.assertRaisesRegex(PilotPersistenceError, "STATE_ITEM_INVALID"):
            PersistentPilotState(tenants=(object(),))

    def test_audit_code_count_is_bounded(self):
        with self.assertRaisesRegex(PilotPersistenceError, "AUDIT_CODES_INVALID"):
            PersistentAuditEvent(
                "audit-many",
                "EVENT",
                "actor",
                "tenant-a",
                "subject",
                NOW,
                tuple(f"code-{index}" for index in range(33)),
            )


if __name__ == "__main__":
    unittest.main()
