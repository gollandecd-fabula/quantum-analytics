from __future__ import annotations

import unittest

import tests.test_multi_user_pilot_runtime as _v1
from quantum.pilot.runtime import InMemoryPilotIdentityStore
from quantum.pilot.runtime_v2 import PilotIdentityRuntime, PilotRuntimeError


class PilotRuntimeV2RegressionTests(_v1.PilotRuntimeTests):
    """Run the complete R1 behavioral contract against authoritative runtime v2."""

    def setUp(self) -> None:
        self.store = InMemoryPilotIdentityStore()
        self.runtime = PilotIdentityRuntime(
            hasher=_v1.Argon2idTestDouble(),
            store=self.store,
        )

    def test_requires_argon2id_backend(self):
        with self.assertRaisesRegex(
            PilotRuntimeError,
            "ARGON2ID_BACKEND_REQUIRED",
        ):
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


if __name__ == "__main__":
    unittest.main()
