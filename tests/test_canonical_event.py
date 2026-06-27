import unittest
from datetime import UTC, datetime

from quantum.domain.events import CanonicalEvent, EventStatus


def event(**overrides):
    values = dict(
        event_id="evt-1",
        organization_id="org",
        marketplace_account_id="account",
        event_type="SALE_RECOGNIZED",
        event_time=datetime.now(UTC),
        recognition_time=datetime.now(UTC),
        stable_business_key="sale:1",
        source_row_key="sheet:2",
        revision=1,
        idempotency_key="a" * 64,
        semantic_payload_hash="b" * 64,
        import_batch_id="batch-1",
        source_record_id="src-1",
        schema_version="1.0",
        payload={"quantity": 1},
        provenance={"source_file_sha256": "c" * 64},
        status=EventStatus.VALID,
        created_at=datetime.now(UTC),
        supersedes_event_id=None,
        reversal_of_event_id=None,
    )
    values.update(overrides)
    return CanonicalEvent(**values)


class CanonicalEventTests(unittest.TestCase):
    def test_revision_must_start_at_one(self):
        with self.assertRaises(ValueError):
            event(revision=0)

    def test_event_cannot_reverse_itself(self):
        with self.assertRaises(ValueError):
            event(reversal_of_event_id="evt-1")

    def test_payload_is_immutable_view(self):
        item = event()
        with self.assertRaises(TypeError):
            item.payload["quantity"] = 2


if __name__ == "__main__":
    unittest.main()
