from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import unittest

from quantum.pilot import (
    AccountStatus,
    MembershipStatus,
    Permission,
    PilotIdentityError,
    PseudonymousAccount,
    SessionPrincipal,
    Tenant,
    TenantMembership,
    TenantRole,
    TenantStatus,
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

    def test_session_contract_requires_live_state_and_bounded_ttl(self):
        session = self.contract["identity"]["session"]
        self.assertTrue(
            session["live_account_membership_tenant_state_required_each_request"]
        )
        self.assertTrue(session["future_issued_session_rejected"])
        self.assertEqual(session["max_lifetime_hours"], 12)


class IdentityAndTenantIsolationTests(unittest.TestCase):
    def account(
        self,
        status: AccountStatus = AccountStatus.ACTIVE,
    ) -> PseudonymousAccount:
        return PseudonymousAccount(
            account_id="account-001",
            pseudonym="pilot_user",
            credential_record_id="credential-001",
            recovery_record_id="recovery-001",
            credential_algorithm="argon2id",
            status=status,
            created_at=NOW,
        )

    def tenant(
        self,
        status: TenantStatus = TenantStatus.ACTIVE,
    ) -> Tenant:
        return Tenant(
            tenant_id="tenant-a",
            tenant_alias="tenant-alpha",
            status=status,
            created_at=NOW,
        )

    def membership(
        self,
        role: TenantRole,
        status: MembershipStatus = MembershipStatus.ACTIVE,
    ) -> TenantMembership:
        return TenantMembership(
            membership_id="membership-001",
            tenant_id="tenant-a",
            account_id="account-001",
            role=role,
            status=status,
            created_at=NOW,
        )

    def principal(
        self,
        role: TenantRole,
        *,
        issued_at: datetime = NOW,
        expires_at: datetime | None = None,
    ) -> SessionPrincipal:
        return SessionPrincipal(
            session_id="session-001",
            account_id="account-001",
            tenant_id="tenant-a",
            membership_id="membership-001",
            role=role,
            issued_at=issued_at,
            expires_at=expires_at or issued_at + timedelta(hours=1),
        )

    def authorize_live(
        self,
        role: TenantRole,
        *,
        permission: Permission,
        now: datetime = NOW + timedelta(minutes=1),
        tenant_id: str = "tenant-a",
        account_status: AccountStatus = AccountStatus.ACTIVE,
        membership_status: MembershipStatus = MembershipStatus.ACTIVE,
        tenant_status: TenantStatus = TenantStatus.ACTIVE,
        principal: SessionPrincipal | None = None,
    ) -> None:
        active_principal = principal or self.principal(role)
        authorize(
            active_principal,
            account=self.account(account_status),
            membership=self.membership(role, membership_status),
            tenant=self.tenant(tenant_status),
            tenant_id=tenant_id,
            permission=permission,
            now=now,
        )

    def test_only_argon2id_is_admitted(self):
        account = self.account()
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

    def test_credential_and_recovery_references_must_differ(self):
        with self.assertRaisesRegex(
            PilotIdentityError,
            "ACCOUNT_RECOVERY_REFERENCE_REUSED",
        ):
            PseudonymousAccount(
                account_id="account-001",
                pseudonym="pilot_user",
                credential_record_id="same-reference",
                recovery_record_id="same-reference",
                credential_algorithm="argon2id",
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
            self.authorize_live(
                TenantRole.TENANT_OWNER,
                tenant_id="tenant-b",
                permission=Permission.VIEW_ANALYTICS,
            )

    def test_viewer_cannot_upload(self):
        with self.assertRaisesRegex(
            PilotIdentityError,
            "PERMISSION_DENIED",
        ):
            self.authorize_live(
                TenantRole.TENANT_VIEWER,
                permission=Permission.UPLOAD_DATASET,
            )

    def test_analyst_can_run_analysis_in_own_tenant(self):
        self.authorize_live(
            TenantRole.TENANT_ANALYST,
            permission=Permission.RUN_ANALYSIS,
        )

    def test_expired_session_fails_closed(self):
        with self.assertRaisesRegex(PilotIdentityError, "SESSION_EXPIRED"):
            self.authorize_live(
                TenantRole.TENANT_ANALYST,
                permission=Permission.RUN_ANALYSIS,
                now=NOW + timedelta(hours=1),
            )

    def test_future_issued_session_fails_closed(self):
        future = self.principal(
            TenantRole.TENANT_ANALYST,
            issued_at=NOW + timedelta(minutes=5),
        )
        with self.assertRaisesRegex(
            PilotIdentityError,
            "SESSION_NOT_YET_VALID",
        ):
            self.authorize_live(
                TenantRole.TENANT_ANALYST,
                principal=future,
                permission=Permission.RUN_ANALYSIS,
                now=NOW + timedelta(minutes=1),
            )

    def test_overlong_session_is_rejected(self):
        with self.assertRaisesRegex(
            PilotIdentityError,
            "SESSION_LIFETIME_EXCEEDED",
        ):
            self.principal(
                TenantRole.TENANT_ANALYST,
                expires_at=NOW + timedelta(hours=13),
            )

    def test_revoked_account_fails_closed(self):
        with self.assertRaisesRegex(
            PilotIdentityError,
            "ACCOUNT_NOT_ACTIVE",
        ):
            self.authorize_live(
                TenantRole.TENANT_ANALYST,
                account_status=AccountStatus.REVOKED,
                permission=Permission.RUN_ANALYSIS,
            )

    def test_suspended_membership_fails_closed(self):
        with self.assertRaisesRegex(
            PilotIdentityError,
            "MEMBERSHIP_NOT_ACTIVE",
        ):
            self.authorize_live(
                TenantRole.TENANT_ANALYST,
                membership_status=MembershipStatus.SUSPENDED,
                permission=Permission.RUN_ANALYSIS,
            )

    def test_suspended_tenant_fails_closed(self):
        with self.assertRaisesRegex(
            PilotIdentityError,
            "TENANT_NOT_ACTIVE",
        ):
            self.authorize_live(
                TenantRole.TENANT_ANALYST,
                tenant_status=TenantStatus.SUSPENDED,
                permission=Permission.RUN_ANALYSIS,
            )


if __name__ == "__main__":
    unittest.main()
