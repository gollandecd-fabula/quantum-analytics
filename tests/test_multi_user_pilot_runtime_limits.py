from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import unittest

from quantum.pilot.runtime_v2 import (
    PilotIdentityRuntime,
    PilotRuntimeError,
    PilotRuntimeLimits,
)

NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)
INVITE_SECRET = "owner-invite-secret-000001"
PASSWORD = "Owner-password-long-000001"
RECOVERY = "Owner-recovery-key-0000001"


class Argon2idTestDouble:
    algorithm = "argon2id"

    def hash_secret(self, secret: str) -> str:
        digest = hashlib.sha256(("test-pepper:" + secret).encode()).hexdigest()
        return "$argon2id$test-double$" + digest

    def verify_secret(self, verifier: str, secret: str) -> bool:
        return hmac.compare_digest(verifier, self.hash_secret(secret))


class PilotRuntimeLimitTests(unittest.TestCase):
    def runtime(self, **limit_overrides) -> PilotIdentityRuntime:
        return PilotIdentityRuntime(
            hasher=Argon2idTestDouble(),
            limits=PilotRuntimeLimits(**limit_overrides),
        )

    def bootstrap_account(self, runtime: PilotIdentityRuntime):
        tenant, invite = runtime.bootstrap_tenant_with_owner_invite(
            operator_reference="operator-bootstrap",
            tenant_alias="tenant-alpha",
            invite_secret=INVITE_SECRET,
            now=NOW,
            invite_expires_at=NOW + timedelta(hours=2),
        )
        runtime.accept_invite(
            invite_id=invite.invite_id,
            invite_secret=INVITE_SECRET,
            pseudonym="owner_alpha",
            password=PASSWORD,
            recovery_key=RECOVERY,
            now=NOW + timedelta(minutes=1),
        )
        return tenant

    def test_runtime_limits_must_be_positive(self):
        with self.assertRaisesRegex(PilotRuntimeError, "RUNTIME_LIMIT_INVALID"):
            PilotRuntimeLimits(max_tenants=0)

    def test_tenant_capacity_fails_closed_without_partial_state(self):
        runtime = self.runtime(max_tenants=1)
        runtime.bootstrap_tenant_with_owner_invite(
            operator_reference="operator-bootstrap",
            tenant_alias="tenant-one",
            invite_secret=INVITE_SECRET,
            now=NOW,
            invite_expires_at=NOW + timedelta(hours=2),
        )
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "TENANT_CAPACITY_EXCEEDED",
        ):
            runtime.bootstrap_tenant_with_owner_invite(
                operator_reference="operator-bootstrap",
                tenant_alias="tenant-two",
                invite_secret="second-owner-invite-secret-0001",
                now=NOW + timedelta(minutes=1),
                invite_expires_at=NOW + timedelta(hours=2),
            )
        self.assertEqual(runtime.snapshot().tenant_count, 1)

    def test_audit_capacity_preflight_is_atomic(self):
        runtime = self.runtime(max_audit_events=2)
        _, invite = runtime.bootstrap_tenant_with_owner_invite(
            operator_reference="operator-bootstrap",
            tenant_alias="tenant-audit-bound",
            invite_secret=INVITE_SECRET,
            now=NOW,
            invite_expires_at=NOW + timedelta(hours=2),
        )
        with self.assertRaisesRegex(PilotRuntimeError, "AUDIT_CAPACITY_EXCEEDED"):
            runtime.accept_invite(
                invite_id=invite.invite_id,
                invite_secret=INVITE_SECRET,
                pseudonym="owner_audit_bound",
                password=PASSWORD,
                recovery_key=RECOVERY,
                now=NOW + timedelta(minutes=1),
            )
        snapshot = runtime.snapshot()
        self.assertEqual(snapshot.account_count, 0)
        self.assertEqual(snapshot.membership_count, 0)
        self.assertEqual(snapshot.audit_event_count, 2)

    def test_active_session_limit_and_pruning(self):
        runtime = self.runtime(max_active_sessions_per_account=1)
        tenant = self.bootstrap_account(runtime)
        first = runtime.authenticate(
            pseudonym="owner_alpha",
            password=PASSWORD,
            tenant_id=tenant.tenant_id,
            now=NOW + timedelta(minutes=2),
        )
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "ACCOUNT_ACTIVE_SESSION_CAPACITY_EXCEEDED",
        ):
            runtime.authenticate(
                pseudonym="owner_alpha",
                password=PASSWORD,
                tenant_id=tenant.tenant_id,
                now=NOW + timedelta(minutes=3),
            )
        runtime.revoke_session(
            session_token=first.session_token,
            now=NOW + timedelta(minutes=3),
        )
        replacement = runtime.authenticate(
            pseudonym="owner_alpha",
            password=PASSWORD,
            tenant_id=tenant.tenant_id,
            now=NOW + timedelta(minutes=4),
        )
        self.assertNotEqual(first.session_token, replacement.session_token)
        self.assertEqual(runtime.snapshot().active_session_count, 1)

    def test_cross_purpose_credential_swap_is_forbidden(self):
        runtime = self.runtime()
        self.bootstrap_account(runtime)
        for new_password, new_recovery in (
            (RECOVERY, "Owner-recovery-key-NEW-000001"),
            ("Owner-password-NEW-long-000001", PASSWORD),
        ):
            with self.assertRaisesRegex(
                PilotRuntimeError,
                "CREDENTIAL_REUSE_FORBIDDEN",
            ):
                runtime.rotate_credentials_with_recovery(
                    pseudonym="owner_alpha",
                    recovery_key=RECOVERY,
                    new_password=new_password,
                    new_recovery_key=new_recovery,
                    now=NOW + timedelta(minutes=3),
                )


if __name__ == "__main__":
    unittest.main()
