from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import unittest

from quantum.pilot.identity_contracts import (
    Permission,
    PilotIdentityError,
    SessionStatus,
    TenantRole,
)
from quantum.pilot.runtime import (
    AuditEventType,
    InMemoryPilotIdentityStore,
    PilotIdentityRuntime,
    PilotRuntimeError,
)


NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
OWNER_INVITE_SECRET = "owner-invite-secret-000001"
OWNER_PASSWORD = "Owner-password-0001"
OWNER_RECOVERY = "Owner-recovery-key-0000001"


class Argon2idTestDouble:
    algorithm = "argon2id"

    def hash_secret(self, secret: str) -> str:
        digest = hashlib.sha256(("test-pepper:" + secret).encode()).hexdigest()
        return "$argon2id$test-double$" + digest

    def verify_secret(self, verifier: str, secret: str) -> bool:
        return hmac.compare_digest(verifier, self.hash_secret(secret))


class BadAlgorithmBackend(Argon2idTestDouble):
    algorithm = "bcrypt"


class PlaintextBackend(Argon2idTestDouble):
    def hash_secret(self, secret: str) -> str:
        return "$argon2id$" + secret


class NonBooleanVerifyBackend(Argon2idTestDouble):
    def verify_secret(self, verifier: str, secret: str):
        return 1


class PilotRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryPilotIdentityStore()
        self.runtime = PilotIdentityRuntime(
            hasher=Argon2idTestDouble(),
            store=self.store,
        )

    def bootstrap_owner(self):
        tenant, invite = self.runtime.bootstrap_tenant_with_owner_invite(
            operator_reference="operator-bootstrap",
            tenant_alias="tenant-alpha",
            invite_secret=OWNER_INVITE_SECRET,
            now=NOW,
            invite_expires_at=NOW + timedelta(hours=2),
        )
        accepted = self.runtime.accept_invite(
            invite_id=invite.invite_id,
            invite_secret=OWNER_INVITE_SECRET,
            pseudonym="owner_alpha",
            password=OWNER_PASSWORD,
            recovery_key=OWNER_RECOVERY,
            now=NOW + timedelta(minutes=1),
        )
        issued = self.runtime.authenticate(
            pseudonym="owner_alpha",
            password=OWNER_PASSWORD,
            tenant_id=tenant.tenant_id,
            now=NOW + timedelta(minutes=2),
        )
        return tenant, accepted, issued

    def issue_and_accept_member(
        self,
        *,
        owner_token: str,
        tenant_id: str,
        role: TenantRole,
        pseudonym: str,
        offset: int,
    ):
        invite_secret = f"member-invite-secret-{offset:06d}"
        password = f"Member-password-{offset:04d}"
        recovery = f"Member-recovery-key-{offset:08d}"
        invite = self.runtime.issue_invite(
            actor_session_token=owner_token,
            tenant_id=tenant_id,
            role=role,
            invite_secret=invite_secret,
            now=NOW + timedelta(minutes=offset),
            expires_at=NOW + timedelta(hours=2),
        )
        accepted = self.runtime.accept_invite(
            invite_id=invite.invite_id,
            invite_secret=invite_secret,
            pseudonym=pseudonym,
            password=password,
            recovery_key=recovery,
            now=NOW + timedelta(minutes=offset + 1),
        )
        return accepted, password, recovery

    def test_requires_argon2id_backend(self):
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "ARGON2ID_BACKEND_REQUIRED",
        ):
            PilotIdentityRuntime(hasher=BadAlgorithmBackend())

    def test_rejects_backend_that_returns_plaintext(self):
        runtime = PilotIdentityRuntime(hasher=PlaintextBackend())
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "CREDENTIAL_BACKEND_INVALID_OUTPUT",
        ):
            runtime.bootstrap_tenant_with_owner_invite(
                operator_reference="operator-bootstrap",
                tenant_alias="tenant-alpha",
                invite_secret=OWNER_INVITE_SECRET,
                now=NOW,
                invite_expires_at=NOW + timedelta(hours=2),
            )

    def test_rejects_invalid_session_lifetime_configuration(self):
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "SESSION_LIFETIME_CONFIGURATION_INVALID",
        ):
            PilotIdentityRuntime(
                hasher=Argon2idTestDouble(),
                session_lifetime=timedelta(hours=13),
            )

    def test_non_boolean_backend_verification_fails_closed(self):
        runtime = PilotIdentityRuntime(hasher=NonBooleanVerifyBackend())
        _, invite = runtime.bootstrap_tenant_with_owner_invite(
            operator_reference="operator-bootstrap",
            tenant_alias="tenant-nonbool",
            invite_secret=OWNER_INVITE_SECRET,
            now=NOW,
            invite_expires_at=NOW + timedelta(hours=2),
        )
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "CREDENTIAL_BACKEND_INVALID_OUTPUT",
        ):
            runtime.accept_invite(
                invite_id=invite.invite_id,
                invite_secret=OWNER_INVITE_SECRET,
                pseudonym="owner_nonbool",
                password=OWNER_PASSWORD,
                recovery_key=OWNER_RECOVERY,
                now=NOW + timedelta(minutes=1),
            )

    def test_account_contract_has_no_direct_identifier_fields(self):
        _, accepted, _ = self.bootstrap_owner()
        fields = set(accepted.account.__dataclass_fields__)
        self.assertTrue(
            {"full_name", "email", "phone", "postal_address"}.isdisjoint(fields)
        )

    def test_bootstrap_accept_and_authenticate_owner(self):
        tenant, accepted, issued = self.bootstrap_owner()
        self.assertEqual(accepted.tenant, tenant)
        self.assertEqual(accepted.membership.role, TenantRole.TENANT_OWNER)
        self.assertEqual(issued.account_id, accepted.account.account_id)
        self.assertEqual(issued.tenant_id, tenant.tenant_id)
        self.assertNotIn(issued.session_token, repr(issued))

    def test_session_token_is_not_stored_in_plaintext(self):
        _, _, issued = self.bootstrap_owner()
        self.assertNotIn(issued.session_token, repr(self.store.__dict__))
        digest = hashlib.sha256(issued.session_token.encode()).hexdigest()
        self.assertIn(digest, self.store._session_digest_owners)

    def test_owner_can_issue_analyst_invite(self):
        tenant, _, owner = self.bootstrap_owner()
        accepted, _, _ = self.issue_and_accept_member(
            owner_token=owner.session_token,
            tenant_id=tenant.tenant_id,
            role=TenantRole.TENANT_ANALYST,
            pseudonym="analyst_alpha",
            offset=3,
        )
        self.assertEqual(accepted.membership.role, TenantRole.TENANT_ANALYST)

    def test_viewer_cannot_issue_invite(self):
        tenant, _, owner = self.bootstrap_owner()
        _, password, _ = self.issue_and_accept_member(
            owner_token=owner.session_token,
            tenant_id=tenant.tenant_id,
            role=TenantRole.TENANT_VIEWER,
            pseudonym="viewer_alpha",
            offset=3,
        )
        viewer = self.runtime.authenticate(
            pseudonym="viewer_alpha",
            password=password,
            tenant_id=tenant.tenant_id,
            now=NOW + timedelta(minutes=5),
        )
        with self.assertRaisesRegex(PilotIdentityError, "PERMISSION_DENIED"):
            self.runtime.issue_invite(
                actor_session_token=viewer.session_token,
                tenant_id=tenant.tenant_id,
                role=TenantRole.TENANT_VIEWER,
                invite_secret="another-invite-secret-000001",
                now=NOW + timedelta(minutes=6),
                expires_at=NOW + timedelta(hours=2),
            )

    def test_invite_cannot_be_accepted_before_issue_time(self):
        _, invite = self.runtime.bootstrap_tenant_with_owner_invite(
            operator_reference="operator-bootstrap",
            tenant_alias="tenant-future-invite",
            invite_secret=OWNER_INVITE_SECRET,
            now=NOW + timedelta(minutes=5),
            invite_expires_at=NOW + timedelta(hours=2),
        )
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "INVITE_NOT_YET_VALID",
        ):
            self.runtime.accept_invite(
                invite_id=invite.invite_id,
                invite_secret=OWNER_INVITE_SECRET,
                pseudonym="future_owner",
                password=OWNER_PASSWORD,
                recovery_key=OWNER_RECOVERY,
                now=NOW,
            )

    def test_wrong_invite_secret_fails_closed(self):
        _, invite = self.runtime.bootstrap_tenant_with_owner_invite(
            operator_reference="operator-bootstrap",
            tenant_alias="tenant-wrong-secret",
            invite_secret=OWNER_INVITE_SECRET,
            now=NOW,
            invite_expires_at=NOW + timedelta(hours=2),
        )
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "INVITE_AUTHENTICATION_FAILED",
        ):
            self.runtime.accept_invite(
                invite_id=invite.invite_id,
                invite_secret="wrong-invite-secret-000001",
                pseudonym="owner_wrong_secret",
                password=OWNER_PASSWORD,
                recovery_key=OWNER_RECOVERY,
                now=NOW + timedelta(minutes=1),
            )

    def test_invite_is_one_time(self):
        _, _, _ = self.bootstrap_owner()
        invite = next(iter(self.store._invites.values()))
        with self.assertRaisesRegex(PilotRuntimeError, "INVITE_NOT_ACTIVE"):
            self.runtime.accept_invite(
                invite_id=invite.invite_id,
                invite_secret=OWNER_INVITE_SECRET,
                pseudonym="second_owner",
                password="Second-password-0001",
                recovery_key="Second-recovery-key-000001",
                now=NOW + timedelta(minutes=3),
            )

    def test_expired_invite_fails_closed(self):
        tenant, invite = self.runtime.bootstrap_tenant_with_owner_invite(
            operator_reference="operator-bootstrap",
            tenant_alias="tenant-expired",
            invite_secret=OWNER_INVITE_SECRET,
            now=NOW,
            invite_expires_at=NOW + timedelta(minutes=1),
        )
        self.assertIsNotNone(tenant)
        with self.assertRaisesRegex(PilotRuntimeError, "INVITE_EXPIRED"):
            self.runtime.accept_invite(
                invite_id=invite.invite_id,
                invite_secret=OWNER_INVITE_SECRET,
                pseudonym="late_owner",
                password=OWNER_PASSWORD,
                recovery_key=OWNER_RECOVERY,
                now=NOW + timedelta(minutes=1),
            )

    def test_invite_lifetime_is_bounded(self):
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "INVITE_LIFETIME_INVALID",
        ):
            self.runtime.bootstrap_tenant_with_owner_invite(
                operator_reference="operator-bootstrap",
                tenant_alias="tenant-long-invite",
                invite_secret=OWNER_INVITE_SECRET,
                now=NOW,
                invite_expires_at=NOW + timedelta(days=8),
            )

    def test_pseudonym_is_case_insensitively_unique(self):
        tenant, _, owner = self.bootstrap_owner()
        invite = self.runtime.issue_invite(
            actor_session_token=owner.session_token,
            tenant_id=tenant.tenant_id,
            role=TenantRole.TENANT_VIEWER,
            invite_secret="case-invite-secret-0000001",
            now=NOW + timedelta(minutes=3),
            expires_at=NOW + timedelta(hours=2),
        )
        with self.assertRaisesRegex(PilotRuntimeError, "PSEUDONYM_CONFLICT"):
            self.runtime.accept_invite(
                invite_id=invite.invite_id,
                invite_secret="case-invite-secret-0000001",
                pseudonym="OWNER_ALPHA",
                password="Other-password-0001",
                recovery_key="Other-recovery-key-000001",
                now=NOW + timedelta(minutes=4),
            )

    def test_authentication_before_account_creation_fails_closed(self):
        tenant, _, _ = self.bootstrap_owner()
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "AUTHENTICATION_FAILED",
        ):
            self.runtime.authenticate(
                pseudonym="owner_alpha",
                password=OWNER_PASSWORD,
                tenant_id=tenant.tenant_id,
                now=NOW,
            )

    def test_wrong_password_is_generic_failure(self):
        tenant, _, _ = self.bootstrap_owner()
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "AUTHENTICATION_FAILED",
        ):
            self.runtime.authenticate(
                pseudonym="owner_alpha",
                password="Wrong-password-0001",
                tenant_id=tenant.tenant_id,
                now=NOW + timedelta(minutes=3),
            )

    def test_cross_tenant_authentication_is_generic_failure(self):
        _, _, _ = self.bootstrap_owner()
        other_tenant, _ = self.runtime.bootstrap_tenant_with_owner_invite(
            operator_reference="operator-bootstrap",
            tenant_alias="tenant-beta",
            invite_secret="beta-owner-invite-secret-0001",
            now=NOW + timedelta(minutes=3),
            invite_expires_at=NOW + timedelta(hours=2),
        )
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "AUTHENTICATION_FAILED",
        ):
            self.runtime.authenticate(
                pseudonym="owner_alpha",
                password=OWNER_PASSWORD,
                tenant_id=other_tenant.tenant_id,
                now=NOW + timedelta(minutes=4),
            )

    def test_authorize_session_enforces_tenant_scope(self):
        tenant, _, issued = self.bootstrap_owner()
        principal = self.runtime.authorize_session(
            session_token=issued.session_token,
            tenant_id=tenant.tenant_id,
            permission=Permission.MANAGE_MEMBERS,
            now=NOW + timedelta(minutes=3),
        )
        self.assertEqual(principal.account_id, issued.account_id)
        with self.assertRaisesRegex(PilotIdentityError, "TENANT_SCOPE_MISMATCH"):
            self.runtime.authorize_session(
                session_token=issued.session_token,
                tenant_id="tenant-other",
                permission=Permission.VIEW_ANALYTICS,
                now=NOW + timedelta(minutes=3),
            )

    def test_session_cannot_be_revoked_before_issue_time(self):
        _, _, issued = self.bootstrap_owner()
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "SESSION_REVOCATION_TIME_REGRESSION",
        ):
            self.runtime.revoke_session(
                session_token=issued.session_token,
                now=NOW + timedelta(minutes=1),
            )

    def test_session_revocation_denies_immediately(self):
        tenant, _, issued = self.bootstrap_owner()
        revoked = self.runtime.revoke_session(
            session_token=issued.session_token,
            now=NOW + timedelta(minutes=3),
        )
        self.assertEqual(revoked.status, SessionStatus.REVOKED)
        with self.assertRaisesRegex(PilotIdentityError, "SESSION_NOT_ACTIVE"):
            self.runtime.authorize_session(
                session_token=issued.session_token,
                tenant_id=tenant.tenant_id,
                permission=Permission.VIEW_ANALYTICS,
                now=NOW + timedelta(minutes=4),
            )

    def test_credential_rotation_rejects_time_regression(self):
        self.bootstrap_owner()
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "CREDENTIAL_ROTATION_TIME_REGRESSION",
        ):
            self.runtime.rotate_credentials_with_recovery(
                pseudonym="owner_alpha",
                recovery_key=OWNER_RECOVERY,
                new_password="Owner-password-NEW-0001",
                new_recovery_key="Owner-recovery-key-NEW-000001",
                now=NOW,
            )

    def test_credential_rotation_revokes_sessions_and_old_credentials(self):
        tenant, accepted, issued = self.bootstrap_owner()
        rotated = self.runtime.rotate_credentials_with_recovery(
            pseudonym="owner_alpha",
            recovery_key=OWNER_RECOVERY,
            new_password="Owner-password-NEW-0001",
            new_recovery_key="Owner-recovery-key-NEW-000001",
            now=NOW + timedelta(minutes=3),
        )
        self.assertEqual(
            rotated.authentication_epoch,
            accepted.account.authentication_epoch + 1,
        )
        with self.assertRaisesRegex(PilotIdentityError, "SESSION_NOT_ACTIVE"):
            self.runtime.authorize_session(
                session_token=issued.session_token,
                tenant_id=tenant.tenant_id,
                permission=Permission.VIEW_ANALYTICS,
                now=NOW + timedelta(minutes=4),
            )
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "AUTHENTICATION_FAILED",
        ):
            self.runtime.authenticate(
                pseudonym="owner_alpha",
                password=OWNER_PASSWORD,
                tenant_id=tenant.tenant_id,
                now=NOW + timedelta(minutes=4),
            )
        new_session = self.runtime.authenticate(
            pseudonym="owner_alpha",
            password="Owner-password-NEW-0001",
            tenant_id=tenant.tenant_id,
            now=NOW + timedelta(minutes=4),
        )
        self.assertEqual(new_session.account_id, accepted.account.account_id)
        with self.assertRaisesRegex(PilotRuntimeError, "RECOVERY_FAILED"):
            self.runtime.rotate_credentials_with_recovery(
                pseudonym="owner_alpha",
                recovery_key=OWNER_RECOVERY,
                new_password="Another-password-0001",
                new_recovery_key="Another-recovery-key-000001",
                now=NOW + timedelta(minutes=5),
            )

    def test_credential_reuse_is_forbidden(self):
        self.bootstrap_owner()
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "CREDENTIAL_REUSE_FORBIDDEN",
        ):
            self.runtime.rotate_credentials_with_recovery(
                pseudonym="owner_alpha",
                recovery_key=OWNER_RECOVERY,
                new_password=OWNER_PASSWORD,
                new_recovery_key="Owner-recovery-key-NEW-000001",
                now=NOW + timedelta(minutes=3),
            )

    def test_tenant_alias_is_unique_case_insensitively(self):
        self.runtime.bootstrap_tenant_with_owner_invite(
            operator_reference="operator-bootstrap",
            tenant_alias="Tenant-Alpha",
            invite_secret=OWNER_INVITE_SECRET,
            now=NOW,
            invite_expires_at=NOW + timedelta(hours=2),
        )
        with self.assertRaisesRegex(PilotRuntimeError, "TENANT_ALIAS_CONFLICT"):
            self.runtime.bootstrap_tenant_with_owner_invite(
                operator_reference="operator-bootstrap",
                tenant_alias="tenant-alpha",
                invite_secret="different-owner-invite-000001",
                now=NOW + timedelta(minutes=1),
                invite_expires_at=NOW + timedelta(hours=2),
            )

    def test_concurrent_invite_acceptance_has_single_winner(self):
        _, invite = self.runtime.bootstrap_tenant_with_owner_invite(
            operator_reference="operator-bootstrap",
            tenant_alias="tenant-concurrent",
            invite_secret=OWNER_INVITE_SECRET,
            now=NOW,
            invite_expires_at=NOW + timedelta(hours=2),
        )

        def accept(index: int) -> str:
            try:
                self.runtime.accept_invite(
                    invite_id=invite.invite_id,
                    invite_secret=OWNER_INVITE_SECRET,
                    pseudonym=f"owner_{index}",
                    password=f"Owner-password-{index:04d}",
                    recovery_key=f"Owner-recovery-key-{index:08d}",
                    now=NOW + timedelta(minutes=1),
                )
                return "accepted"
            except PilotRuntimeError as exc:
                return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(accept, (1, 2)))
        self.assertEqual(results.count("accepted"), 1)
        self.assertEqual(results.count("INVITE_NOT_ACTIVE"), 1)

    def test_snapshot_declares_non_persistent_runtime(self):
        self.bootstrap_owner()
        snapshot = self.runtime.snapshot()
        self.assertFalse(snapshot.persistent)
        self.assertEqual(snapshot.credential_backend, "argon2id")
        self.assertEqual(snapshot.tenant_count, 1)
        self.assertEqual(snapshot.account_count, 1)
        self.assertEqual(snapshot.active_session_count, 1)

    def test_audit_and_store_representations_contain_no_plaintext_secrets(self):
        _, _, issued = self.bootstrap_owner()
        serialized = repr(self.runtime.audit_events()) + repr(self.store)
        for secret in (
            OWNER_INVITE_SECRET,
            OWNER_PASSWORD,
            OWNER_RECOVERY,
            issued.session_token,
        ):
            self.assertNotIn(secret, serialized)
        event_types = {event.event_type for event in self.runtime.audit_events()}
        self.assertIn(AuditEventType.TENANT_PROVISIONED, event_types)
        self.assertIn(AuditEventType.INVITE_ACCEPTED, event_types)
        self.assertIn(AuditEventType.SESSION_ISSUED, event_types)


if __name__ == "__main__":
    unittest.main()
