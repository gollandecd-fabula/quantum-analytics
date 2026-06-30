from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from quantum.access import TenantContext
from quantum.domain.idempotency import canonical_json_hash
from quantum.domain.source_rows import ImmutableSourceRow, SourceRowStatus
from quantum.infrastructure.in_memory_canonical_ledger import (
    CanonicalLedgerError,
    InMemoryCanonicalLedger,
)
from quantum.ingestion.canonical_pipeline import SyntheticCsvCanonicalIngestor
from quantum.ingestion.receipts import ImmutableUploadReceipt
from quantum.ingestion.storage import CsvSchemaGate, LocalRawStorage, RawFileState


HEADERS = (
    "row_id,operation_id,operation_type,event_time,recognition_time,"
    "product_external_id,quantity,gross_amount,currency,revision,"
    "supersedes_event_id,reversal_of_event_id"
)


class P13ReviewRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.tenant = TenantContext(str(uuid4()), str(uuid4()))
        self.storage = LocalRawStorage(Path(self.temp.name))
        self.ledger = InMemoryCanonicalLedger()
        self.ingestor = SyntheticCsvCanonicalIngestor(
            storage=self.storage,
            ledger=self.ledger,
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def prepare(self, rows: tuple[str, ...]) -> str:
        payload = (HEADERS + "\n" + "\n".join(rows) + "\n").encode()
        digest = sha256(payload).hexdigest()
        item = ImmutableUploadReceipt(
            raw_file_id=str(uuid4()),
            tenant_id=self.tenant.tenant_id,
            sha256=digest,
            size_bytes=len(payload),
            sanitized_filename="report.csv",
            storage_key="untrusted",
            duplicate=False,
        )
        self.storage.store(tenant=self.tenant, receipt=item, payload=payload)
        result = CsvSchemaGate(self.storage).inspect(
            tenant=self.tenant,
            raw_file_id=item.raw_file_id,
        )
        self.assertEqual(result.record.state, RawFileState.VALID)
        return item.raw_file_id

    def ingest(self, rows: tuple[str, ...]):
        return self.ingestor.ingest(
            tenant=self.tenant,
            raw_file_id=self.prepare(rows),
            marketplace_account_id="wb-account",
            ingested_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
        )

    def test_dependencies_are_resolved_independent_of_source_order(self) -> None:
        rows = (
            "4,return-001,RETURN,2026-06-04T14:00:00Z,"
            "2026-06-04T14:05:00Z,product-a,1,1000.00,RUB,1,,"
            "evt-sale-001-r1",
            "3,sale-002,SALE,2026-06-02T11:00:00Z,"
            "2026-06-03T09:00:00Z,product-b,1,1400.00,RUB,2,"
            "evt-sale-002-r1,",
            "2,sale-002,SALE,2026-06-02T11:00:00Z,"
            "2026-06-02T11:05:00Z,product-b,1,1500.00,RUB,1,,",
            "1,sale-001,SALE,2026-06-01T10:00:00Z,"
            "2026-06-01T10:05:00Z,product-a,1,1000.00,RUB,1,,",
        )
        result = self.ingest(rows)
        self.assertEqual(result.inserted_events, 4)
        self.assertEqual(result.quarantined_rows, 0)

    def test_superseded_reversal_is_not_double_counted(self) -> None:
        rows = (
            "1,sale-001,SALE,2026-06-01T10:00:00Z,"
            "2026-06-01T10:05:00Z,product-a,2,1000.00,RUB,1,,",
            "2,return-001,RETURN,2026-06-02T10:00:00Z,"
            "2026-06-02T10:05:00Z,product-a,2,1000.00,RUB,1,,"
            "evt-sale-001-r1",
            "3,return-001,RETURN,2026-06-03T10:00:00Z,"
            "2026-06-03T10:05:00Z,product-a,1,500.00,RUB,2,"
            "evt-return-001-r1,evt-sale-001-r1",
            "4,return-002,RETURN,2026-06-04T10:00:00Z,"
            "2026-06-04T10:05:00Z,product-a,1,500.00,RUB,1,,"
            "evt-sale-001-r1",
        )
        result = self.ingest(rows)
        self.assertEqual(result.inserted_events, 4)
        self.assertEqual(result.quarantined_rows, 0)

    def test_later_supersession_prevents_temporary_reversal_quarantine(self) -> None:
        rows = (
            "1,sale-001,SALE,2026-06-01T10:00:00Z,"
            "2026-06-01T10:05:00Z,product-a,2,1000.00,RUB,1,,",
            "2,return-a,RETURN,2026-06-02T10:00:00Z,"
            "2026-06-02T10:05:00Z,product-a,2,1000.00,RUB,1,,"
            "evt-sale-001-r1",
            "3,return-b,RETURN,2026-06-03T10:00:00Z,"
            "2026-06-03T10:05:00Z,product-a,1,500.00,RUB,1,,"
            "evt-sale-001-r1",
            "4,return-a,RETURN,2026-06-04T10:00:00Z,"
            "2026-06-04T10:05:00Z,product-a,1,500.00,RUB,2,"
            "evt-return-a-r1,evt-sale-001-r1",
        )
        result = self.ingest(rows)
        self.assertEqual(result.inserted_events, 4)
        self.assertEqual(result.quarantined_rows, 0)
        self.assertEqual(len(self.ledger.list_events(tenant=self.tenant)), 4)

    def test_duplicate_content_under_new_raw_id_is_idempotent(self) -> None:
        rows = (
            "1,sale-001,SALE,2026-06-01T10:00:00Z,"
            "2026-06-01T10:05:00Z,product-a,1,1000.00,RUB,1,,",
        )
        first_raw_id = self.prepare(rows)
        second_raw_id = self.prepare(rows)
        self.assertNotEqual(first_raw_id, second_raw_id)

        first = self.ingestor.ingest(
            tenant=self.tenant,
            raw_file_id=first_raw_id,
            marketplace_account_id="wb-account",
            ingested_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
        )
        second = self.ingestor.ingest(
            tenant=self.tenant,
            raw_file_id=second_raw_id,
            marketplace_account_id="wb-account",
            ingested_at=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
        )

        self.assertEqual(first.import_batch_id, second.import_batch_id)
        self.assertEqual(first.source_record_ids, second.source_record_ids)
        self.assertEqual(second.inserted_source_rows, 0)
        self.assertEqual(second.inserted_events, 0)
        self.assertEqual(second.duplicate_source_rows, 1)
        self.assertEqual(second.duplicate_events, 1)
        self.assertEqual(len(self.ledger.list_source_rows(tenant=self.tenant)), 1)
        self.assertEqual(len(self.ledger.list_events(tenant=self.tenant)), 1)

    def test_currency_mismatch_is_quarantined(self) -> None:
        rows = (
            "1,sale-001,SALE,2026-06-01T10:00:00Z,"
            "2026-06-01T10:05:00Z,product-a,1,1000.00,RUB,1,,",
            "2,return-001,RETURN,2026-06-02T10:00:00Z,"
            "2026-06-02T10:05:00Z,product-a,1,1000.00,USD,1,,"
            "evt-sale-001-r1",
        )
        result = self.ingest(rows)
        self.assertEqual(result.inserted_events, 1)
        self.assertEqual(result.quarantined_rows, 1)
        quarantined = self.ledger.list_source_rows(tenant=self.tenant)[1]
        self.assertEqual(
            quarantined.diagnostics,
            ("EVENT_REVERSAL_UNIT_MISMATCH",),
        )

    def test_product_mismatch_is_quarantined(self) -> None:
        rows = (
            "1,sale-001,SALE,2026-06-01T10:00:00Z,"
            "2026-06-01T10:05:00Z,product-a,1,1000.00,RUB,1,,",
            "2,return-001,RETURN,2026-06-02T10:00:00Z,"
            "2026-06-02T10:05:00Z,product-b,1,1000.00,RUB,1,,"
            "evt-sale-001-r1",
        )
        result = self.ingest(rows)
        self.assertEqual(result.inserted_events, 1)
        self.assertEqual(result.quarantined_rows, 1)

    def test_unexpected_conflict_rolls_back_whole_new_batch(self) -> None:
        original = (
            "1,sale-001,SALE,2026-06-01T10:00:00Z,"
            "2026-06-01T10:05:00Z,product-a,1,1000.00,RUB,1,,",
        )
        conflict = (
            "1,sale-002,SALE,2026-06-01T09:00:00Z,"
            "2026-06-01T09:05:00Z,product-b,1,500.00,RUB,1,,",
            "2,sale-001,SALE,2026-06-01T10:00:00Z,"
            "2026-06-01T10:05:00Z,product-a,1,900.00,RUB,1,,",
        )
        self.ingest(original)
        before_events = self.ledger.list_events(tenant=self.tenant)
        before_rows = self.ledger.list_source_rows(tenant=self.tenant)
        with self.assertRaisesRegex(CanonicalLedgerError, "EVENT_ID_CONFLICT"):
            self.ingest(conflict)
        self.assertEqual(self.ledger.list_events(tenant=self.tenant), before_events)
        self.assertEqual(self.ledger.list_source_rows(tenant=self.tenant), before_rows)

    def test_quarantine_reimport_reports_duplicate_separately(self) -> None:
        rows = (
            "1,sale-001,SALE,2026-06-01T10:00:00Z,"
            "2026-06-01T10:05:00Z,product-a,one,1000.00,RUB,1,,",
        )
        raw_file_id = self.prepare(rows)
        first = self.ingestor.ingest(
            tenant=self.tenant,
            raw_file_id=raw_file_id,
            marketplace_account_id="wb-account",
            ingested_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
        )
        second = self.ingestor.ingest(
            tenant=self.tenant,
            raw_file_id=raw_file_id,
            marketplace_account_id="wb-account",
            ingested_at=datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
        )
        self.assertEqual(first.inserted_quarantined_rows, 1)
        self.assertEqual(second.inserted_quarantined_rows, 0)
        self.assertEqual(second.duplicate_quarantined_rows, 1)

    def test_source_row_rejects_false_raw_hash(self) -> None:
        raw_payload = {"row_id": "1"}
        with self.assertRaisesRegex(ValueError, "does not match raw_payload"):
            ImmutableSourceRow(
                source_record_id="src",
                tenant_id=self.tenant.tenant_id,
                raw_file_id=str(uuid4()),
                source_file_sha256="a" * 64,
                import_batch_id="batch",
                row_number=2,
                source_row_key="csv:row:1",
                raw_row_hash="b" * 64,
                raw_payload=raw_payload,
                structural_fingerprint={"sha256": "c" * 64},
                semantic_fingerprint={"sha256": "d" * 64},
                validation_status=SourceRowStatus.VALID,
                diagnostics=(),
                adapter_id="adapter",
                adapter_version="1",
                schema_version="schema",
                ingested_at=datetime(2026, 6, 30, tzinfo=UTC),
            )
        self.assertNotEqual(canonical_json_hash(raw_payload), "b" * 64)

    def test_invalid_currency_is_row_quarantined(self) -> None:
        rows = (
            "1,sale-001,SALE,2026-06-01T10:00:00Z,"
            "2026-06-01T10:05:00Z,product-a,1,1000.00,rub,1,,",
        )
        result = self.ingest(rows)
        self.assertEqual(result.inserted_events, 0)
        self.assertEqual(result.quarantined_rows, 1)
        row = self.ledger.list_source_rows(tenant=self.tenant)[0]
        self.assertIn("currency:", row.diagnostics[0])


if __name__ == "__main__":
    unittest.main()
