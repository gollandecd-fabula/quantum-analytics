from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from quantum.access.contracts import AccessError, AccessRegistry, TenantContext
from quantum.ingestion.receipts import IngestionError, UploadReceiptRegistry


class P1AccessAndIngestion(unittest.TestCase):
    def setUp(self) -> None:
        self.access = AccessRegistry()
        self.now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)

    def activate(self, feature_profile: str = "PILOT_TESTER"):
        code = self.access.issue_invite(
            expires_at=self.now + timedelta(days=1),
            feature_profile=feature_profile,
            now=self.now,
        )
        return code, self.access.activate_invite(code, now=self.now)

    def test_invite_is_one_time_and_account_is_pseudonymous(self):
        code, activation = self.activate("BETA_LIMITED")
        self.assertTrue(activation.account.account_alias.startswith("QTM-"))
        self.assertEqual(activation.account.feature_profile, "BETA_LIMITED")
        self.assertEqual(activation.tenant.feature_profile, "BETA_LIMITED")
        self.assertNotIn(code, repr(self.access.__dict__))
        self.assertNotIn(activation.recovery_key, repr(self.access.__dict__))
        self.assertTrue(
            self.access.verify_recovery_key(
                activation.account.account_id,
                activation.recovery_key,
            )
        )
        with self.assertRaisesRegex(AccessError, "INVITE_ALREADY_USED"):
            self.access.activate_invite(code, now=self.now)

    def test_invite_expiry_and_malformed_inputs_are_fail_closed(self):
        code = self.access.issue_invite(
            expires_at=self.now + timedelta(minutes=1),
            now=self.now,
        )
        with self.assertRaisesRegex(AccessError, "INVITE_EXPIRED"):
            self.access.activate_invite(
                code,
                now=self.now + timedelta(minutes=1),
            )
        with self.assertRaisesRegex(AccessError, "INVITE_INVALID"):
            self.access.activate_invite(7, now=self.now)  # type: ignore[arg-type]
        with self.assertRaisesRegex(AccessError, "FEATURE_PROFILE_INVALID"):
            self.access.issue_invite(
                expires_at=self.now + timedelta(days=1),
                feature_profile=7,  # type: ignore[arg-type]
                now=self.now,
            )
        with self.assertRaisesRegex(AccessError, "TENANT_ID_INVALID"):
            TenantContext(tenant_id="", account_id="account")

    def test_upload_receipt_is_immutable_and_idempotent_per_tenant(self):
        _, first = self.activate()
        registry = UploadReceiptRegistry()
        payload = b"synthetic-only"
        receipt = registry.receive(
            tenant=first.tenant,
            payload=payload,
            filename="../../dangerous report.xlsx",
        )
        duplicate = registry.receive(
            tenant=first.tenant,
            payload=payload,
            filename="other-name.xlsx",
        )
        self.assertFalse(receipt.duplicate)
        self.assertTrue(duplicate.duplicate)
        self.assertEqual(receipt.raw_file_id, duplicate.raw_file_id)
        self.assertEqual(receipt.sha256, duplicate.sha256)
        self.assertEqual(receipt.sanitized_filename, "dangerous_report.xlsx")
        self.assertTrue(receipt.storage_key.startswith("tenants/"))

    def test_cross_tenant_lookup_does_not_reveal_existence(self):
        _, first = self.activate()
        code = self.access.issue_invite(
            expires_at=self.now + timedelta(days=1),
            now=self.now,
        )
        second = self.access.activate_invite(code, now=self.now)
        registry = UploadReceiptRegistry()
        one = registry.receive(
            tenant=first.tenant,
            payload=b"same-bytes",
            filename="a.xlsx",
        )
        two = registry.receive(
            tenant=second.tenant,
            payload=b"same-bytes",
            filename="a.xlsx",
        )
        self.assertNotEqual(one.raw_file_id, two.raw_file_id)
        self.assertNotEqual(one.storage_key, two.storage_key)
        for raw_file_id in (one.raw_file_id, "unknown"):
            with self.assertRaisesRegex(IngestionError, "RAW_FILE_NOT_FOUND"):
                registry.get(tenant=second.tenant, raw_file_id=raw_file_id)

    def test_invalid_upload_boundaries_are_rejected(self):
        _, activation = self.activate()
        registry = UploadReceiptRegistry()
        with self.assertRaisesRegex(IngestionError, "UPLOAD_EMPTY"):
            registry.receive(
                tenant=activation.tenant,
                payload=b"",
                filename="empty.xlsx",
            )
        with self.assertRaisesRegex(IngestionError, "UPLOAD_BYTES_REQUIRED"):
            registry.receive(  # type: ignore[arg-type]
                tenant=activation.tenant,
                payload="not-bytes",
                filename="bad.xlsx",
            )
        with self.assertRaisesRegex(IngestionError, "UPLOAD_FILENAME_INVALID"):
            registry.receive(
                tenant=activation.tenant,
                payload=b"data",
                filename=7,  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(IngestionError, "TENANT_CONTEXT_REQUIRED"):
            registry.receive(  # type: ignore[arg-type]
                tenant="tenant",
                payload=b"data",
                filename="bad.xlsx",
            )


if __name__ == "__main__":
    unittest.main()
