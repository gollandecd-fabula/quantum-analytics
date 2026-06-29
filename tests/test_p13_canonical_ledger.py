from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from quantum.access import TenantContext
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


def receipt(tenant: TenantContext, payload: bytes) -> ImmutableUploadReceipt:
    digest = sha256(payload).hexdigest()
    return ImmutableUploadReceipt(
        raw_file_id=str(uuid4()),
        tenant_id=tenant.tenant_id,
        sha256=digest,
        size_bytes=len(payload),
        sanitized_filename="report.csv",
        storage_key="untrusted",
        duplicate=False,
    )


class P13CanonicalLedgerTests(unittest.TestCase):
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

    @staticmethod
    def valid_payload() -> bytes:
        rows = (
            "1,sale-001,SALE,2026-06-01T10:00:00Z,"
            "2026-06-01T10:05:00Z,product-a,1,1000.00,RUB,1,,",
            "2,sale-002,SALE,2026-06-02T11:00:00Z,"
            "2026-06-02T11:05:00Z,product-b,1,1500.00,RUB,1,,",
            "3,sale-002,SALE,2026-06-02T11:00:00Z,"
            "2026-06-03T09:00:00Z,product-b,1,1400.00,RUB,2,"
            "evt-sale-002-r1,",
            "4,return-001,RETURN,2026-06-04T14:00:00Z,"
            "2026-06-04T14:05:00Z,product-a,1,1000.00,RUB,1,,"
            "evt-sale-001-r1",
        )
        return (HEADERS + "\n" + "\n".join(rows) + "\n").encode()

    def prepare(self, payload: bytes) -> str:
        item = receipt(self.tenant, payload)
        self.storage.store(
            tenant=self.tenant,
            receipt=item,
            payload=payload,
        )
        gate = CsvSchemaGate(self.storage).inspect(
            tenant=self.tenant,
            raw_file_id=item.raw_file_id,
        )
        self.assertEqual(gate.record.state, RawFileState.VALID)
        return item.raw_file_id

    def ingest(self, raw_file_id: str):
        return self.ingestor.ingest(
            tenant=self.tenant,
            raw_file_id=raw_file_id,
            marketplace_account_id="wb-account",
            ingested_at=datetime(2026, 6, 30, 12, 0, tzinfo=UTC),
        )

    def test_valid_file_creates_source_rows_events_and_lineage(self) -> None:
        raw_file_id = self.prepare(self.valid_payload())
        result = self.ingest(raw_file_id)

        self.assertEqual(result.total_rows, 4)
        self.assertEqual(result.inserted_source_rows, 4)
        self.assertEqual(result.inserted_events, 4)
        self.assertEqual(result.quarantined_rows, 0)

        trace = self.ledger.trace_event(
            tenant=self.tenant,
            event_id="evt-sale-002-r2",
        )
        self.assertEqual(trace.raw_file_id, raw_file_id)
        self.assertEqual(trace.event.supersedes_event_id, "evt-sale-002-r1")
        self.assertEqual(trace.source_row.row_number, 4)
        self.assertEqual(
            trace.event.provenance["source_file_sha256"],
            trace.source_file_sha256,
        )

    def test_reimport_is_idempotent(self) -> None:
        raw_file_id = self.prepare(self.valid_payload())
        first = self.ingest(raw_file_id)
        second = self.ingest(raw_file_id)

        self.assertEqual(first.inserted_events, 4)
        self.assertEqual(second.inserted_source_rows, 0)
        self.assertEqual(second.inserted_events, 0)
        self.assertEqual(second.duplicate_source_rows, 4)
        self.assertEqual(second.duplicate_events, 4)
        self.assertEqual(len(self.ledger.list_events(tenant=self.tenant)), 4)

    def test_semantic_row_error_is_quarantined_without_data_loss(self) -> None:
        payload = (
            HEADERS
            + "\n1,sale-001,SALE,2026-06-01T10:00:00Z,"
            "2026-06-01T10:05:00Z,product-a,one,1000.00,RUB,1,,\n"
        ).encode()
        raw_file_id = self.prepare(payload)
        result = self.ingest(raw_file_id)

        self.assertEqual(result.inserted_events, 0)
        self.assertEqual(result.quarantined_rows, 1)
        rows = self.ledger.list_source_rows(tenant=self.tenant)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].validation_status, SourceRowStatus.QUARANTINED)
        self.assertIn("quantity: invalid integer", rows[0].diagnostics[0])

    def test_missing_revision_target_is_quarantined(self) -> None:
        payload = (
            HEADERS
            + "\n3,sale-002,SALE,2026-06-02T11:00:00Z,"
            "2026-06-03T09:00:00Z,product-b,1,1400.00,RUB,2,"
            "evt-sale-002-r1,\n"
        ).encode()
        raw_file_id = self.prepare(payload)
        result = self.ingest(raw_file_id)

        self.assertEqual(result.inserted_events, 0)
        self.assertEqual(result.quarantined_rows, 1)
        row = self.ledger.list_source_rows(tenant=self.tenant)[0]
        self.assertEqual(
            row.diagnostics,
            ("EVENT_SUPERSEDED_TARGET_MISSING",),
        )

    def test_cumulative_reversal_cannot_exceed_original(self) -> None:
        rows = (
            "1,sale-001,SALE,2026-06-01T10:00:00Z,"
            "2026-06-01T10:05:00Z,product-a,2,1000.00,RUB,1,,",
            "2,return-001,RETURN,2026-06-02T10:00:00Z,"
            "2026-06-02T10:05:00Z,product-a,1,500.00,RUB,1,,"
            "evt-sale-001-r1",
            "3,return-002,RETURN,2026-06-03T10:00:00Z,"
            "2026-06-03T10:05:00Z,product-a,2,600.00,RUB,1,,"
            "evt-sale-001-r1",
        )
        raw_file_id = self.prepare(
            (HEADERS + "\n" + "\n".join(rows) + "\n").encode()
        )
        result = self.ingest(raw_file_id)

        self.assertEqual(result.inserted_events, 2)
        self.assertEqual(result.quarantined_rows, 1)
        quarantined = [
            row
            for row in self.ledger.list_source_rows(tenant=self.tenant)
            if row.validation_status is SourceRowStatus.QUARANTINED
        ]
        self.assertEqual(
            quarantined[0].diagnostics,
            ("EVENT_REVERSAL_EXCEEDS_ORIGINAL",),
        )

    def test_cross_tenant_trace_does_not_reveal_event(self) -> None:
        raw_file_id = self.prepare(self.valid_payload())
        self.ingest(raw_file_id)
        other = TenantContext(str(uuid4()), str(uuid4()))

        with self.assertRaisesRegex(
            CanonicalLedgerError,
            "EVENT_NOT_FOUND",
        ):
            self.ledger.trace_event(
                tenant=other,
                event_id="evt-sale-001-r1",
            )

    def test_source_row_payload_is_immutable(self) -> None:
        raw_file_id = self.prepare(self.valid_payload())
        self.ingest(raw_file_id)
        row = self.ledger.list_source_rows(tenant=self.tenant)[0]

        with self.assertRaises(TypeError):
            row.raw_payload["quantity"] = "99"

    def test_concurrent_reimport_produces_one_ledger_copy(self) -> None:
        raw_file_id = self.prepare(self.valid_payload())

        def run(_: int):
            return self.ingest(raw_file_id)

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(run, range(16)))

        self.assertEqual(
            sum(item.inserted_events for item in results),
            4,
        )
        self.assertEqual(len(self.ledger.list_events(tenant=self.tenant)), 4)
        self.assertEqual(
            len(self.ledger.list_source_rows(tenant=self.tenant)),
            4,
        )

    def test_raw_file_must_pass_schema_gate(self) -> None:
        payload = self.valid_payload()
        item = receipt(self.tenant, payload)
        self.storage.store(
            tenant=self.tenant,
            receipt=item,
            payload=payload,
        )

        with self.assertRaisesRegex(
            CanonicalLedgerError,
            "RAW_FILE_NOT_VALID",
        ):
            self.ingest(item.raw_file_id)

    def test_source_row_locator_conflict_is_rejected(self) -> None:
        raw_file_id = str(uuid4())
        common = dict(
            tenant_id=self.tenant.tenant_id,
            raw_file_id=raw_file_id,
            source_file_sha256="a" * 64,
            import_batch_id="batch",
            row_number=2,
            source_row_key="csv:row:1",
            raw_row_hash="b" * 64,
            raw_payload={"row_id": "1"},
            structural_fingerprint={"sha256": "c" * 64},
            semantic_fingerprint={"sha256": "d" * 64},
            validation_status=SourceRowStatus.QUARANTINED,
            diagnostics=("TEST",),
            adapter_id="adapter",
            adapter_version="1",
            schema_version="schema",
            ingested_at=datetime(2026, 6, 30, tzinfo=UTC),
        )
        first = ImmutableSourceRow(source_record_id="src-1", **common)
        second = ImmutableSourceRow(source_record_id="src-2", **common)
        self.ledger.append(
            tenant=self.tenant,
            source_row=first,
            event=None,
        )

        with self.assertRaisesRegex(
            CanonicalLedgerError,
            "SOURCE_ROW_LOCATOR_CONFLICT",
        ):
            self.ledger.append(
                tenant=self.tenant,
                source_row=second,
                event=None,
            )


if __name__ == "__main__":
    unittest.main()
