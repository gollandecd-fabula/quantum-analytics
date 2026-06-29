from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from quantum.access.contracts import AccessError, AccessRegistry
from quantum.ingestion.receipts import IngestionError, UploadReceiptRegistry


class P1AccessAndIngestion(unittest.TestCase):
    def setUp(self) -> None:
        self.access = AccessRegistry()
        self.now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)

    def activate(self):
        code = self.access.issue_invite(
            expires_at=self.now + timedelta(days=1),
            now=self.now,
        )
        return code, self.access.activate_invite(code, now=self.now)

    def test_invite_is_one_time_and_account_is_pseudonymous(self):
        code, activation = self.activate()
        self.assertTrue(activation.account.account_alias.startswith("QTM-"))
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

    def test_invite_expiry_is_fail_closed(self):
        code = self.access.issue_invite(
            expires_at=self.now + timedelta(minutes=1),
            now=self.now,
        )
        with self.assertRaisesRegex(AccessError, "INVITE_EXPIRED"):
            self.access.activate_invite(
                code,
                now=self.now + timedelta(minutes=1),
            )

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

    def test_same_bytes_are_isolated_between_tenants(self):
        _, first = self.activate()
        code = self.access.issue_invite(
            expires_at=self.now + timedelta(days=1),
            now=self.now,
        )
        second = self.access.activate_invite(code, now=self.now)
        registry = UploadReceiptRegistry()
        payload = b"same-bytes"
        one = registry.receive(
            tenant=first.tenant,
            payload=payload,
            filename="a.xlsx",
        )
        two = registry.receive(
            tenant=second.tenant,
            payload=payload,
            filename="a.xlsx",
        )
        self.assertNotEqual(one.raw_file_id, two.raw_file_id)
        self.assertNotEqual(one.storage_key, two.storage_key)
        with self.assertRaisesRegex(AccessError, "TENANT_SCOPE_MISMATCH"):
            registry.get(tenant=second.tenant, raw_file_id=one.raw_file_id)

    def test_empty_or_non_bytes_upload_is_rejected(self):
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


if __name__ == "__main__":
    unittest.main()
