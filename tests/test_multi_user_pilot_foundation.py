from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import unittest

from quantum.pilot import (
    AccountStatus,
    Permission,
    PilotIdentityError,
    PseudonymousAccount,
    SessionPrincipal,
    TenantRole,
    authorize,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs/pilot/MULTI_USER_PILOT_CONTRACT_v1.json"
NOW = datetime(2026, 7, 3, 12, 0, tzinfo=UTC)


class MultiUserPilotContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_pilot_is_closed_pseudonymous_and_free(self):
        pilot = self.contract["pilot"]
        self.assertEqual(
            pilot["access"],
            "INVITE_OR_APPROVED_REQUEST_ONLY",
        )
        self.assertEqual(
            pilot["commercial_terms"],
            "FREE_TESTING_FOR_FIRST_CLIENTS",
        )
        self.assertFalse(pilot["public_self_registration"])
        self.assertFalse(pilot["direct_identifiers_required"])
        self.assertEqual(
            pilot["allowed_registration_fields"],
            ["pseudonym", "password", "recovery_key"],
        )

    def test_hosted_storage_requires_encryption(self):
        storage = self.contract["storage"]
        self.assertEqual(storage["environment"], "HOSTED_EXTERNAL")
        self.assertTrue(storage["tls_required"])
        self.assertTrue(storage["encryption_at_rest_required"])
        self.assertTrue(storage["tenant_scoped_paths"])

    def test_private_learning_and_read_only_are_hard_boundaries(self):
        learning = self.contract["learning"]
        project = self.contract["project"]
        self.assertEqual(learning["default_scope"], "PRIVATE_PER_TENANT")
        self.assertFalse(learning["cross_tenant_raw_training"])
        self.assertFalse(learning["global_learning_enabled"])
        self.assertFalse(project["marketplace_write_enabled"])
        self.assertEqual(project["release_state"], "RELEASE_BLOCKED")

    def test_real_users_are_legally_and_operationally_gated(self):
        gates = set(self.contract["release_gates"]["real_user_pilot"])
        self.assertIn("LEGAL_OPERATOR_DEFINED", gates)
        self.assertIn("ROSKOMNADZOR_NOTIFICATION_CONFIRMED", gates)
        self.assertIn("RUSSIAN_HOSTING_CONFIRMED", gates)
        self.assertIn("EXPLICIT_USER_APPROVAL", gates)


class IdentityAndTenantIsolationTests(unittest.TestCase):
    def principal(self, role: TenantRole) -> SessionPrincipal:
        return SessionPrincipal(
            session_id="session-001",
            account_id="account-001",
            tenant_id="tenant-a",
            membership_id="membership-001",
            role=role,
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )

    def test_only_argon2id_is_admitted(self):
        account = PseudonymousAccount(
            account_id="account-001",
            pseudonym="pilot_user",
            credential_record_id="credential-001",
            recovery_record_id="recovery-001",
            credential_algorithm="argon2id",
            status=AccountStatus.ACTIVE,
            created_at=NOW,
        )
        self.assertEqual(account.credential_algorithm, "argon2id")

        with self.assertRaisesRegex(
            PilotIdentityError,
            "ACCOUNT_CREDENTIAL_ALGORITHM_INVALID",
        ):
            PseudonymousAccount(
                account_id="account-002",
                pseudonym="other_user",
                credential_record_id="credential-002",
                recovery_record_id="recovery-002",
                credential_algorithm="bcrypt",
                status=AccountStatus.ACTIVE,
                created_at=NOW,
            )

    def test_email_like_pseudonym_is_rejected(self):
        with self.assertRaisesRegex(
            PilotIdentityError,
            "ACCOUNT_PSEUDONYM_INVALID",
        ):
            PseudonymousAccount(
                account_id="account-001",
                pseudonym="person@example.com",
                credential_record_id="credential-001",
                recovery_record_id="recovery-001",
                credential_algorithm="argon2id",
                status=AccountStatus.ACTIVE,
                created_at=NOW,
            )

    def test_cross_tenant_access_fails_closed(self):
        with self.assertRaisesRegex(
            PilotIdentityError,
            "TENANT_SCOPE_MISMATCH",
        ):
            authorize(
                self.principal(TenantRole.TENANT_OWNER),
                tenant_id="tenant-b",
                permission=Permission.VIEW_ANALYTICS,
                now=NOW + timedelta(minutes=1),
            )

    def test_viewer_cannot_upload(self):
        with self.assertRaisesRegex(
            PilotIdentityError,
            "PERMISSION_DENIED",
        ):
            authorize(
                self.principal(TenantRole.TENANT_VIEWER),
                tenant_id="tenant-a",
                permission=Permission.UPLOAD_DATASET,
                now=NOW + timedelta(minutes=1),
            )

    def test_analyst_can_run_analysis_in_own_tenant(self):
        authorize(
            self.principal(TenantRole.TENANT_ANALYST),
            tenant_id="tenant-a",
            permission=Permission.RUN_ANALYSIS,
            now=NOW + timedelta(minutes=1),
        )

    def test_expired_session_fails_closed(self):
        with self.assertRaisesRegex(PilotIdentityError, "SESSION_EXPIRED"):
            authorize(
                self.principal(TenantRole.TENANT_ANALYST),
                tenant_id="tenant-a",
                permission=Permission.RUN_ANALYSIS,
                now=NOW + timedelta(hours=1),
            )


if __name__ == "__main__":
    unittest.main()
