from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import unittest

from quantum.access import AccessError, AccessRegistry
from quantum.ingestion import UploadReceiptRegistry


class P1ConcurrencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
        self.access = AccessRegistry()

    def test_one_invite_has_exactly_one_concurrent_winner(self) -> None:
        code = self.access.issue_invite(
            expires_at=self.now + timedelta(days=1),
            now=self.now,
        )

        def activate(_: int):
            try:
                return self.access.activate_invite(code, now=self.now)
            except AccessError as exc:
                return exc.code

        with ThreadPoolExecutor(max_workers=16) as executor:
            results = list(executor.map(activate, range(32)))
        winners = [result for result in results if not isinstance(result, str)]
        losers = [result for result in results if isinstance(result, str)]
        self.assertEqual(len(winners), 1)
        self.assertEqual(set(losers), {"INVITE_ALREADY_USED"})

    def test_same_upload_has_one_concurrent_receipt(self) -> None:
        code = self.access.issue_invite(
            expires_at=self.now + timedelta(days=1),
            now=self.now,
        )
        tenant = self.access.activate_invite(code, now=self.now).tenant
        registry = UploadReceiptRegistry()

        def receive(_: int):
            return registry.receive(
                tenant=tenant,
                payload=b"same-payload",
                filename="report.xlsx",
            )

        with ThreadPoolExecutor(max_workers=16) as executor:
            receipts = list(executor.map(receive, range(32)))
        self.assertEqual(len({receipt.raw_file_id for receipt in receipts}), 1)
        self.assertEqual(sum(not receipt.duplicate for receipt in receipts), 1)


if __name__ == "__main__":
    unittest.main()
