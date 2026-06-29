from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from uuid import uuid4

from quantum.access import TenantContext
from quantum.ingestion import (
    CsvSchemaGate,
    ImmutableUploadReceipt,
    LocalRawStorage,
    RawFileState,
    RawStorageError,
)


HEADERS = (
    "row_id",
    "operation_id",
    "operation_type",
    "event_time",
    "recognition_time",
    "product_external_id",
    "quantity",
    "gross_amount",
    "currency",
    "revision",
    "supersedes_event_id",
    "reversal_of_event_id",
)


def make_receipt(
    tenant: TenantContext,
    payload: bytes,
    filename: str = "report.csv",
) -> ImmutableUploadReceipt:
    digest = sha256(payload).hexdigest()
    return ImmutableUploadReceipt(
        raw_file_id=str(uuid4()),
        tenant_id=tenant.tenant_id,
        sha256=digest,
        size_bytes=len(payload),
        sanitized_filename=filename,
        storage_key=f"untrusted/{digest}",
        duplicate=False,
    )


class P12RawStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.storage = LocalRawStorage(Path(self.temp.name))
        self.tenant = TenantContext(str(uuid4()), str(uuid4()))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_roundtrip_is_idempotent_and_storage_key_is_canonical(self) -> None:
        payload = b"synthetic-only"
        receipt = make_receipt(self.tenant, payload)
        first = self.storage.store(
            tenant=self.tenant,
            receipt=receipt,
            payload=payload,
        )
        second = self.storage.store(
            tenant=self.tenant,
            receipt=receipt,
            payload=payload,
        )
        self.assertEqual(first, second)
        self.assertEqual(
            first.storage_key,
            f"tenants/{self.tenant.tenant_id}/raw/{receipt.sha256}",
        )
        self.assertEqual(
            self.storage.read(
                tenant=self.tenant,
                raw_file_id=receipt.raw_file_id,
            ),
            payload,
        )

    def test_concurrent_store_has_one_record(self) -> None:
        payload = b"concurrent"
        receipt = make_receipt(self.tenant, payload)

        def store(_: int):
            return self.storage.store(
                tenant=self.tenant,
                receipt=receipt,
                payload=payload,
            )

        with ThreadPoolExecutor(max_workers=12) as executor:
            records = list(executor.map(store, range(24)))
        self.assertEqual(len({record.raw_file_id for record in records}), 1)
        self.assertEqual(len({record.sha256 for record in records}), 1)

    def test_cross_tenant_lookup_hides_existence(self) -> None:
        payload = b"tenant-private"
        receipt = make_receipt(self.tenant, payload)
        self.storage.store(
            tenant=self.tenant,
            receipt=receipt,
            payload=payload,
        )
        other = TenantContext(str(uuid4()), str(uuid4()))
        for raw_file_id in (receipt.raw_file_id, str(uuid4())):
            with self.assertRaisesRegex(RawStorageError, "RAW_FILE_NOT_FOUND"):
                self.storage.get_record(
                    tenant=other,
                    raw_file_id=raw_file_id,
                )

    def test_content_tampering_is_detected(self) -> None:
        payload = b"original"
        receipt = make_receipt(self.tenant, payload)
        self.storage.store(
            tenant=self.tenant,
            receipt=receipt,
            payload=payload,
        )
        path = self.storage.content_path(
            tenant=self.tenant,
            raw_file_id=receipt.raw_file_id,
        )
        path.write_bytes(b"tampered")
        with self.assertRaisesRegex(RawStorageError, "STORAGE_INTEGRITY_FAILED"):
            self.storage.read(
                tenant=self.tenant,
                raw_file_id=receipt.raw_file_id,
            )

    def test_metadata_path_traversal_digest_is_rejected(self) -> None:
        payload = b"metadata"
        receipt = make_receipt(self.tenant, payload)
        self.storage.store(
            tenant=self.tenant,
            receipt=receipt,
            payload=payload,
        )
        tenant_dir = next((Path(self.temp.name) / "tenants").iterdir())
        metadata = tenant_dir / "metadata" / f"{receipt.raw_file_id}.json"
        data = json.loads(metadata.read_text(encoding="utf-8"))
        data["sha256"] = "../../escape"
        metadata.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(RawStorageError, "STORAGE_METADATA_INVALID"):
            self.storage.get_record(
                tenant=self.tenant,
                raw_file_id=receipt.raw_file_id,
            )

    def test_known_schema_becomes_valid_and_is_idempotent(self) -> None:
        row = (
            "1,op1,sale,2026-01-01T00:00:00Z,2026-01-01T00:00:00Z,"
            "p1,1,100,RUB,1,,"
        )
        payload = ((",".join(HEADERS)) + "\n" + row + "\n").encode()
        receipt = make_receipt(self.tenant, payload)
        self.storage.store(
            tenant=self.tenant,
            receipt=receipt,
            payload=payload,
        )
        gate = CsvSchemaGate(self.storage)
        first = gate.inspect(
            tenant=self.tenant,
            raw_file_id=receipt.raw_file_id,
        )
        second = gate.inspect(
            tenant=self.tenant,
            raw_file_id=receipt.raw_file_id,
        )
        self.assertEqual(first.record.state, RawFileState.VALID)
        self.assertEqual(first.record.schema_id, "wb-synthetic-operations-v1")
        self.assertEqual(
            first.record.semantic_fingerprint["descriptor"]["row_count"],
            1,
        )
        self.assertEqual(second.record, first.record)

    def test_unknown_schema_is_quarantined(self) -> None:
        headers = list(HEADERS)
        headers[7] = "gross_sales_amount"
        payload = ((",".join(headers)) + "\n").encode()
        receipt = make_receipt(self.tenant, payload)
        self.storage.store(
            tenant=self.tenant,
            receipt=receipt,
            payload=payload,
        )
        result = CsvSchemaGate(self.storage).inspect(
            tenant=self.tenant,
            raw_file_id=receipt.raw_file_id,
        )
        self.assertEqual(result.record.state, RawFileState.QUARANTINED)
        self.assertIn("missing_columns=gross_amount", result.record.diagnostics)
        self.assertIn(
            "unexpected_columns=gross_sales_amount",
            result.record.diagnostics,
        )

    def test_malformed_csv_is_rejected(self) -> None:
        payload = b"\xff\x00\xff"
        receipt = make_receipt(self.tenant, payload)
        self.storage.store(
            tenant=self.tenant,
            receipt=receipt,
            payload=payload,
        )
        result = CsvSchemaGate(self.storage).inspect(
            tenant=self.tenant,
            raw_file_id=receipt.raw_file_id,
        )
        self.assertEqual(result.record.state, RawFileState.REJECTED)
        self.assertEqual(
            result.record.diagnostics,
            ("CSV_SCHEMA_READ_FAILED",),
        )

    def test_invalid_transition_is_blocked(self) -> None:
        payload = b"state"
        receipt = make_receipt(self.tenant, payload)
        self.storage.store(
            tenant=self.tenant,
            receipt=receipt,
            payload=payload,
        )
        with self.assertRaisesRegex(
            RawStorageError,
            "RAW_FILE_STATE_TRANSITION_INVALID",
        ):
            self.storage.transition(
                tenant=self.tenant,
                raw_file_id=receipt.raw_file_id,
                state=RawFileState.VALID,
            )

    def test_valid_state_requires_schema_evidence(self) -> None:
        payload = b"evidence"
        receipt = make_receipt(self.tenant, payload)
        self.storage.store(
            tenant=self.tenant,
            receipt=receipt,
            payload=payload,
        )
        self.storage.transition(
            tenant=self.tenant,
            raw_file_id=receipt.raw_file_id,
            state=RawFileState.VALIDATING,
        )
        with self.assertRaisesRegex(
            RawStorageError,
            "RAW_FILE_STATE_PAYLOAD_INVALID",
        ):
            self.storage.transition(
                tenant=self.tenant,
                raw_file_id=receipt.raw_file_id,
                state=RawFileState.VALID,
            )

    def test_stale_validating_state_is_recovered(self) -> None:
        row = (
            "1,op1,sale,2026-01-01T00:00:00Z,2026-01-01T00:00:00Z,"
            "p1,1,100,RUB,1,,"
        )
        payload = ((",".join(HEADERS)) + "\n" + row + "\n").encode()
        receipt = make_receipt(self.tenant, payload)
        self.storage.store(
            tenant=self.tenant,
            receipt=receipt,
            payload=payload,
        )
        self.storage.transition(
            tenant=self.tenant,
            raw_file_id=receipt.raw_file_id,
            state=RawFileState.VALIDATING,
        )
        result = CsvSchemaGate(self.storage).inspect(
            tenant=self.tenant,
            raw_file_id=receipt.raw_file_id,
        )
        self.assertEqual(result.record.state, RawFileState.VALID)

    def test_conflicting_raw_id_does_not_leave_orphan_content(self) -> None:
        first_payload = b"first"
        first = make_receipt(self.tenant, first_payload)
        self.storage.store(
            tenant=self.tenant,
            receipt=first,
            payload=first_payload,
        )
        second_payload = b"second"
        second = ImmutableUploadReceipt(
            raw_file_id=first.raw_file_id,
            tenant_id=self.tenant.tenant_id,
            sha256=sha256(second_payload).hexdigest(),
            size_bytes=len(second_payload),
            sanitized_filename="report.csv",
            storage_key="ignored",
            duplicate=False,
        )
        with self.assertRaisesRegex(
            RawStorageError,
            "STORAGE_METADATA_CONFLICT",
        ):
            self.storage.store(
                tenant=self.tenant,
                receipt=second,
                payload=second_payload,
            )
        raw_dir = next((Path(self.temp.name) / "tenants").iterdir()) / "raw"
        self.assertEqual(
            {item.name for item in raw_dir.iterdir()},
            {first.sha256},
        )

    def test_invalid_receipt_filename_is_rejected(self) -> None:
        payload = b"filename"
        receipt = ImmutableUploadReceipt(
            raw_file_id=str(uuid4()),
            tenant_id=self.tenant.tenant_id,
            sha256=sha256(payload).hexdigest(),
            size_bytes=len(payload),
            sanitized_filename="../bad.csv",
            storage_key="ignored",
            duplicate=False,
        )
        with self.assertRaisesRegex(
            RawStorageError,
            "UPLOAD_FILENAME_INVALID",
        ):
            self.storage.store(
                tenant=self.tenant,
                receipt=receipt,
                payload=payload,
            )

    def test_concurrent_schema_inspection_is_serialized(self) -> None:
        row = (
            "1,op1,sale,2026-01-01T00:00:00Z,2026-01-01T00:00:00Z,"
            "p1,1,100,RUB,1,,"
        )
        payload = ((",".join(HEADERS)) + "\n" + row + "\n").encode()
        receipt = make_receipt(self.tenant, payload)
        self.storage.store(
            tenant=self.tenant,
            receipt=receipt,
            payload=payload,
        )
        gate = CsvSchemaGate(self.storage)

        def inspect(_: int):
            return gate.inspect(
                tenant=self.tenant,
                raw_file_id=receipt.raw_file_id,
            )

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(inspect, range(16)))
        self.assertEqual(
            {result.record.state for result in results},
            {RawFileState.VALID},
        )

    def test_noncanonical_metadata_storage_key_is_rejected(self) -> None:
        payload = b"storage-key"
        receipt = make_receipt(self.tenant, payload)
        self.storage.store(
            tenant=self.tenant,
            receipt=receipt,
            payload=payload,
        )
        tenant_dir = next((Path(self.temp.name) / "tenants").iterdir())
        metadata = tenant_dir / "metadata" / f"{receipt.raw_file_id}.json"
        data = json.loads(metadata.read_text(encoding="utf-8"))
        data["storage_key"] = "noncanonical"
        metadata.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(
            RawStorageError,
            "STORAGE_METADATA_INVALID",
        ):
            self.storage.get_record(
                tenant=self.tenant,
                raw_file_id=receipt.raw_file_id,
            )


if __name__ == "__main__":
    unittest.main()
