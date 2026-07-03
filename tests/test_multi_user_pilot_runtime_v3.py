from __future__ import annotations

import tests.test_multi_user_pilot_runtime as _v1
from quantum.pilot.identity_contracts import TenantRole
from quantum.pilot.runtime import InMemoryPilotIdentityStore
from quantum.pilot.runtime_v3 import (
    PilotIdentityRuntime,
    PilotRuntimeError,
    PilotRuntimeLimits,
)


class PilotRuntimeV3RegressionTests(_v1.PilotRuntimeTests):
    def setUp(self) -> None:
        self.store = InMemoryPilotIdentityStore()
        self.runtime = PilotIdentityRuntime(
            hasher=_v1.Argon2idTestDouble(),
            store=self.store,
        )

    def test_requires_argon2id_backend(self):
        with self.assertRaisesRegex(PilotRuntimeError, "ARGON2ID_BACKEND_REQUIRED"):
            PilotIdentityRuntime(hasher=_v1.BadAlgorithmBackend())

    def test_rejects_backend_that_returns_plaintext(self):
        runtime = PilotIdentityRuntime(hasher=_v1.PlaintextBackend())
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "CREDENTIAL_BACKEND_INVALID_OUTPUT",
        ):
            runtime.bootstrap_tenant_with_owner_invite(
                operator_reference="operator-bootstrap",
                tenant_alias="tenant-alpha",
                invite_secret=_v1.OWNER_INVITE_SECRET,
                now=_v1.NOW,
                invite_expires_at=_v1.NOW + _v1.timedelta(hours=2),
            )

    def test_rejects_invalid_session_lifetime_configuration(self):
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "SESSION_LIFETIME_CONFIGURATION_INVALID",
        ):
            PilotIdentityRuntime(
                hasher=_v1.Argon2idTestDouble(),
                session_lifetime=_v1.timedelta(hours=13),
            )

    def test_non_boolean_backend_verification_fails_closed(self):
        runtime = PilotIdentityRuntime(hasher=_v1.NonBooleanVerifyBackend())
        _, invite = runtime.bootstrap_tenant_with_owner_invite(
            operator_reference="operator-bootstrap",
            tenant_alias="tenant-nonbool",
            invite_secret=_v1.OWNER_INVITE_SECRET,
            now=_v1.NOW,
            invite_expires_at=_v1.NOW + _v1.timedelta(hours=2),
        )
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "CREDENTIAL_BACKEND_INVALID_OUTPUT",
        ):
            runtime.accept_invite(
                invite_id=invite.invite_id,
                invite_secret=_v1.OWNER_INVITE_SECRET,
                pseudonym="owner_nonbool",
                password=_v1.OWNER_PASSWORD,
                recovery_key=_v1.OWNER_RECOVERY,
                now=_v1.NOW + _v1.timedelta(minutes=1),
            )

    def test_wrong_password_precedes_session_capacity(self):
        self.runtime = PilotIdentityRuntime(
            hasher=_v1.Argon2idTestDouble(),
            store=self.store,
            limits=PilotRuntimeLimits(max_active_sessions_per_account=1),
        )
        tenant, _, _ = self.bootstrap_owner()
        with self.assertRaisesRegex(PilotRuntimeError, "AUTHENTICATION_FAILED"):
            self.runtime.authenticate(
                pseudonym="owner_alpha",
                password="incorrect-value",
                tenant_id=tenant.tenant_id,
                now=_v1.NOW + _v1.timedelta(minutes=3),
            )
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "ACCOUNT_ACTIVE_SESSION_CAPACITY_EXCEEDED",
        ):
            self.runtime.authenticate(
                pseudonym="owner_alpha",
                password=_v1.OWNER_PASSWORD,
                tenant_id=tenant.tenant_id,
                now=_v1.NOW + _v1.timedelta(minutes=3),
            )

    def test_wrong_invite_secret_precedes_account_capacity(self):
        self.runtime = PilotIdentityRuntime(
            hasher=_v1.Argon2idTestDouble(),
            store=self.store,
            limits=PilotRuntimeLimits(max_accounts=1),
        )
        tenant, _, owner = self.bootstrap_owner()
        invite = self.runtime.issue_invite(
            actor_session_token=owner.session_token,
            tenant_id=tenant.tenant_id,
            role=TenantRole.TENANT_VIEWER,
            invite_secret="member-invite-secret-000001",
            now=_v1.NOW + _v1.timedelta(minutes=3),
            expires_at=_v1.NOW + _v1.timedelta(hours=2),
        )
        common = {
            "invite_id": invite.invite_id,
            "pseudonym": "viewer_alpha",
            "password": "Viewer-password-0001",
            "recovery_key": "Viewer-recovery-key-000001",
            "now": _v1.NOW + _v1.timedelta(minutes=4),
        }
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "INVITE_AUTHENTICATION_FAILED",
        ):
            self.runtime.accept_invite(
                invite_secret="incorrect-invite-value-0001",
                **common,
            )
        with self.assertRaisesRegex(PilotRuntimeError, "ACCOUNT_CAPACITY_EXCEEDED"):
            self.runtime.accept_invite(
                invite_secret="member-invite-secret-000001",
                **common,
            )

    def test_invalid_owner_session_precedes_invite_capacity(self):
        self.runtime = PilotIdentityRuntime(
            hasher=_v1.Argon2idTestDouble(),
            store=self.store,
            limits=PilotRuntimeLimits(max_invites=1),
        )
        tenant, _, owner = self.bootstrap_owner()
        common = {
            "tenant_id": tenant.tenant_id,
            "role": TenantRole.TENANT_VIEWER,
            "invite_secret": "member-invite-secret-000001",
            "now": _v1.NOW + _v1.timedelta(minutes=3),
            "expires_at": _v1.NOW + _v1.timedelta(hours=2),
        }
        with self.assertRaisesRegex(PilotRuntimeError, "SESSION_NOT_FOUND"):
            self.runtime.issue_invite(
                actor_session_token="unknown-session-reference-00000001",
                **common,
            )
        with self.assertRaisesRegex(PilotRuntimeError, "INVITE_CAPACITY_EXCEEDED"):
            self.runtime.issue_invite(
                actor_session_token=owner.session_token,
                **common,
            )
