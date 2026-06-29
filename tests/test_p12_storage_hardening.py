from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from quantum.access import TenantContext
from quantum.ingestion import (
    CsvSchemaGate,
    ImmutableUploadReceipt,
    LocalRawStorage,
    RawFileState,
    RawStorageError,
)
from quantum.ingestion.schema_registry import detect_csv_schema as real_detect


HEADERS = (
    "row_id,operation_id,operation_type,event_time,recognition_time,"
    "product_external_id,quantity,gross_amount,currency,revision,"
    "supersedes_event_id,reversal_of_event_id"
)


class P12StorageHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.tenant = TenantContext(str(uuid4()), str(uuid4()))
        self.storage = LocalRawStorage(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def receipt(self, payload: bytes) -> ImmutableUploadReceipt:
        digest = sha256(payload).hexdigest()
        return ImmutableUploadReceipt(
            raw_file_id=str(uuid4()),
            tenant_id=self.tenant.tenant_id,
            sha256=digest,
            size_bytes=len(payload),
            sanitized_filename="report.csv",
            storage_key="untrusted",
            duplicate=False,
        )

    def valid_payload(self) -> bytes:
        row = (
            "1,op1,sale,2026-01-01T00:00:00Z,2026-01-01T00:00:00Z,"
            "p1,1,100,RUB,1,,"
        )
        return f"{HEADERS}\n{row}\n".encode()

    def test_persisted_valid_state_requires_evidence(self) -> None:
        payload = b"metadata-state"
        receipt = self.receipt(payload)
        self.storage.store(
            tenant=self.tenant,
            receipt=receipt,
            payload=payload,
        )
        tenant_dir = next((self.root / "tenants").iterdir())
        metadata = tenant_dir / "metadata" / f"{receipt.raw_file_id}.json"
        data = json.loads(metadata.read_text(encoding="utf-8"))
        data["state"] = "VALID"
        metadata.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(
            RawStorageError,
            "STORAGE_METADATA_INVALID",
        ):
            self.storage.get_record(
                tenant=self.tenant,
                raw_file_id=receipt.raw_file_id,
            )

    def test_storage_instances_share_validation_coordination(self) -> None:
        payload = self.valid_payload()
        receipt = self.receipt(payload)
        self.storage.store(
            tenant=self.tenant,
            receipt=receipt,
            payload=payload,
        )
        other_storage = LocalRawStorage(self.root)
        gates = (CsvSchemaGate(self.storage), CsvSchemaGate(other_storage))
        call_count = 0
        call_lock = Lock()

        def slow_detect(path: Path):
            nonlocal call_count
            with call_lock:
                call_count += 1
            time.sleep(0.03)
            return real_detect(path)

        def inspect(index: int):
            return gates[index % 2].inspect(
                tenant=self.tenant,
                raw_file_id=receipt.raw_file_id,
            )

        with patch(
            "quantum.ingestion.storage.detect_csv_schema",
            side_effect=slow_detect,
        ):
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(inspect, range(16)))

        self.assertEqual(
            {result.record.state for result in results},
            {RawFileState.VALID},
        )
        self.assertEqual(call_count, 1)

    def test_metadata_raw_file_id_must_match_lookup_id(self) -> None:
        payload = b"metadata-id"
        receipt = self.receipt(payload)
        self.storage.store(
            tenant=self.tenant,
            receipt=receipt,
            payload=payload,
        )
        tenant_dir = next((self.root / "tenants").iterdir())
        metadata = tenant_dir / "metadata" / f"{receipt.raw_file_id}.json"
        data = json.loads(metadata.read_text(encoding="utf-8"))
        data["raw_file_id"] = str(uuid4())
        metadata.write_text(json.dumps(data), encoding="utf-8")

        with self.assertRaisesRegex(
            RawStorageError,
            "STORAGE_METADATA_INVALID",
        ):
            self.storage.get_record(
                tenant=self.tenant,
                raw_file_id=receipt.raw_file_id,
            )

    def test_extra_csv_fields_are_rejected(self) -> None:
        row = (
            "1,op1,sale,2026-01-01T00:00:00Z,2026-01-01T00:00:00Z,"
            "p1,1,100,RUB,1,,,unexpected"
        )
        payload = f"{HEADERS}\n{row}\n".encode()
        receipt = self.receipt(payload)
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


if __name__ == "__main__":
    unittest.main()
