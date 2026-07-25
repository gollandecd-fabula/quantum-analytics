from __future__ import annotations

from io import BytesIO
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
import unittest
from unittest import mock
from zipfile import ZIP_DEFLATED, ZipFile

from quantum.pilot import universal_gateway
from quantum.pilot.universal_import import classify_payload, register_file


STATUSES = {
    "ROUTE_XLSX",
    "ACCEPTED_PARTIAL",
    "ACCEPTED_UNPARSED",
    "QUARANTINED_SECURITY",
    "QUARANTINED_CORRUPTED",
    "ERROR",
}


def make_zip(entries: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return output.getvalue()


class UniversalAnyFileContractR4Tests(unittest.TestCase):
    def test_500_random_payloads_are_deterministic_and_never_raise(self):
        random = Random(20260705)
        suffixes = (".bin", ".xlsx", ".json", ".pdf", ".txt", ".zip", "")
        for index in range(500):
            payload = random.randbytes(random.randint(1, 4096))
            suffix = suffixes[index % len(suffixes)]
            first = classify_payload(payload, suffix)
            second = classify_payload(payload, suffix)
            self.assertEqual(first, second)
            self.assertIn(first.status, STATUSES)

    def test_content_signature_overrides_extension(self):
        json_result = classify_payload(b'[{"sku":"A","sales":1}]', ".xlsx")
        self.assertEqual(json_result.detected_format, "JSON_TABLE")
        executable = classify_payload(b"MZ" + b"0" * 64, ".txt")
        self.assertEqual(executable.status, "QUARANTINED_SECURITY")
        pdf = classify_payload(b"%PDF-1.4\n%%EOF", ".json")
        self.assertEqual(pdf.detected_format, "PDF")

    def test_opaque_containers_fail_closed(self):
        cases = (
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 64,
            make_zip({"plain.txt": b"plain"}),
            make_zip({"nested.zip": make_zip({"data.txt": b"data"})}),
            b"%PDF-1.7\n<</OpenAction 1 0 R /JavaScript true>>",
        )
        for payload in cases:
            self.assertEqual(
                classify_payload(payload, ".dat").status,
                "QUARANTINED_SECURITY",
            )

    def test_corrupted_inputs_return_controlled_status(self):
        self.assertEqual(
            classify_payload(b'{"broken":', ".json").status,
            "QUARANTINED_CORRUPTED",
        )
        self.assertEqual(
            classify_payload(b"PK\x03\x04broken", ".zip").status,
            "QUARANTINED_CORRUPTED",
        )
        entity_xml = b'<!DOCTYPE x [<!ENTITY y "z">]><x>&y;</x>'
        self.assertEqual(
            classify_payload(entity_xml, ".xml").status,
            "QUARANTINED_SECURITY",
        )

    def test_empty_missing_and_oversize_files_return_reports(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            empty = root / "empty.dat"
            empty.write_bytes(b"")
            empty_report = register_file(file_path=empty, storage_root=root / "data")
            missing_report = register_file(
                file_path=root / "missing.dat",
                storage_root=root / "data",
            )
            large = root / "large.dat"
            large.write_bytes(b"0" * 17)
            with mock.patch.object(universal_gateway, "_MAX_FILE_BYTES", 16):
                large_report = register_file(file_path=large, storage_root=root / "data")
        self.assertEqual(empty_report["reason_codes"], ["FILE_EMPTY"])
        self.assertEqual(missing_report["reason_codes"], ["FILE_NOT_FOUND"])
        self.assertEqual(large_report["reason_codes"], ["FILE_SIZE_EXCEEDED"])

    def test_non_xlsx_files_never_claim_financial_success(self):
        payloads = (
            b'[{"sku":"A","sales":1}]',
            b"sku;sales\nA;1\n",
            b"%PDF-1.4\n%%EOF",
            bytes(range(64)) * 2,
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for index, payload in enumerate(payloads):
                source = root / f"source-{index}.dat"
                source.write_bytes(payload)
                report = register_file(file_path=source, storage_root=root / "data")
                self.assertIn(report["status"], STATUSES)
                self.assertIsNone(report["calculation"])
                self.assertFalse(report["marketplace_write_enabled"])
                self.assertFalse(report["raw_rows_in_report"])


if __name__ == "__main__":
    unittest.main()
