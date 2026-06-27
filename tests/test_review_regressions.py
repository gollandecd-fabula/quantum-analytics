import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from quantum.adapters.wildberries.synthetic import validate_row
from quantum.domain.events import CanonicalEvent, EventStatus
from quantum.infrastructure.json_event_ledger import JsonEventLedger


def make_event(
    *,
    event_id="evt-1",
    idempotency_key="a" * 64,
    semantic_payload_hash="b" * 64,
    payload=None,
    provenance=None,
):
    timestamp = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
    return CanonicalEvent(
        event_id=event_id,
        organization_id="org",
        marketplace_account_id="account",
        event_type="SALE_RECOGNIZED",
        event_time=timestamp,
        recognition_time=timestamp,
        stable_business_key="sale:1",
        source_row_key="csv:row:1",
        revision=1,
        idempotency_key=idempotency_key,
        semantic_payload_hash=semantic_payload_hash,
        import_batch_id="batch-1",
        source_record_id="src-1",
        schema_version="wb-synthetic-operations-v1",
        payload=payload or {"gross_amount": {"value": "100.00"}},
        provenance=provenance or {"source_file_sha256": "c" * 64},
        status=EventStatus.VALID,
        created_at=timestamp,
    )


class ReviewRegressionTests(unittest.TestCase):
    def test_canonical_event_detaches_and_deeply_freezes_nested_data(self):
        source_payload = {
            "gross_amount": {"value": "100.00"},
            "lines": [{"quantity": 1}],
        }
        source_provenance = {
            "source_file_sha256": "c" * 64,
            "adapter": {"version": "1.0"},
        }
        event = make_event(payload=source_payload, provenance=source_provenance)

        source_payload["gross_amount"]["value"] = "999.00"
        source_provenance["adapter"]["version"] = "2.0"

        self.assertEqual(event.payload["gross_amount"]["value"], "100.00")
        self.assertEqual(event.provenance["adapter"]["version"], "1.0")
        with self.assertRaises(TypeError):
            event.payload["gross_amount"]["value"] = "200.00"
        with self.assertRaises(TypeError):
            event.payload["lines"][0]["quantity"] = 2

    def test_ledger_rejects_same_event_id_with_different_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = JsonEventLedger(Path(tmp) / "events.json")
            first = make_event(
                event_id="evt-sale-1-r1",
                idempotency_key="a" * 64,
                semantic_payload_hash="b" * 64,
                payload={"quantity": {"value": 1}},
            )
            conflicting = make_event(
                event_id="evt-sale-1-r1",
                idempotency_key="d" * 64,
                semantic_payload_hash="e" * 64,
                payload={"quantity": {"value": 2}},
            )

            self.assertTrue(ledger.add_if_absent(first))
            with self.assertRaisesRegex(RuntimeError, "Event-id collision"):
                ledger.add_if_absent(conflicting)
            self.assertEqual(len(ledger.list_events()), 1)

    def test_ledger_serializes_recursively_immutable_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = JsonEventLedger(Path(tmp) / "events.json")
            event = make_event(
                payload={"lines": [{"quantity": 1}]},
                provenance={
                    "source_file_sha256": "c" * 64,
                    "adapter": {"version": "1.0"},
                },
            )

            self.assertTrue(ledger.add_if_absent(event))
            stored = ledger.list_events()[0]
            self.assertEqual(stored["payload"]["lines"][0]["quantity"], 1)
            self.assertEqual(stored["provenance"]["adapter"]["version"], "1.0")

    def test_non_finite_gross_amounts_are_validation_errors(self):
        base_row = {
            "row_id": "1",
            "operation_id": "sale-1",
            "operation_type": "SALE",
            "event_time": "2026-06-27T10:00:00+00:00",
            "recognition_time": "2026-06-27T10:00:00+00:00",
            "product_external_id": "sku-1",
            "quantity": "1",
            "gross_amount": "100.00",
            "currency": "RUB",
            "revision": "1",
            "supersedes_event_id": "",
            "reversal_of_event_id": "",
        }

        for value in ("NaN", "Infinity", "-Infinity"):
            row = dict(base_row, gross_amount=value)
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "must be finite"):
                    validate_row(row)

    def test_schema_allows_emitted_source_adapter_version(self):
        root = Path(__file__).resolve().parents[1]
        schema = json.loads(
            (root / "schemas/canonical-event.schema.json").read_text(encoding="utf-8")
        )
        provenance_properties = schema["properties"]["provenance"]["properties"]

        self.assertIn("source_adapter_version", provenance_properties)
        self.assertEqual(
            provenance_properties["source_adapter_version"]["type"],
            "string",
        )


if __name__ == "__main__":
    unittest.main()
