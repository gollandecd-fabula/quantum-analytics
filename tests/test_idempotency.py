import unittest

from quantum.domain.idempotency import (
    canonical_json_hash,
    event_idempotency_key,
    file_idempotency_key,
)


class IdempotencyTests(unittest.TestCase):
    def test_canonical_json_hash_is_order_independent(self):
        left = canonical_json_hash({"a": 1, "b": 2})
        right = canonical_json_hash({"b": 2, "a": 1})
        self.assertEqual(left, right)

    def test_file_key_changes_with_adapter_version(self):
        common = dict(
            organization_id="org",
            marketplace_account_id="account",
            source_file_sha256="a" * 64,
            adapter_id="wb",
        )
        self.assertNotEqual(
            file_idempotency_key(**common, adapter_version="1"),
            file_idempotency_key(**common, adapter_version="2"),
        )

    def test_event_revision_participates_in_key(self):
        common = dict(
            organization_id="org",
            marketplace_account_id="account",
            event_type="SALE_RECOGNIZED",
            stable_business_key="sale:1",
            semantic_payload_hash="b" * 64,
        )
        self.assertNotEqual(
            event_idempotency_key(**common, revision=1),
            event_idempotency_key(**common, revision=2),
        )


if __name__ == "__main__":
    unittest.main()
