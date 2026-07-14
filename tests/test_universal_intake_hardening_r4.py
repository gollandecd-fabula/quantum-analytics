from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from quantum.pilot.universal_import import classify_payload, register_file


def _zip(entries: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return output.getvalue()


class UniversalIntakeHardeningR4Tests(unittest.TestCase):
    def test_unknown_archive_is_quarantined_until_adapter_exists(self):
        decision = classify_payload(
            _zip({"safe.txt": b"plain text"}),
            ".zip",
        )
        self.assertEqual(decision.status, "QUARANTINED_SECURITY")
        self.assertEqual(decision.detected_format, "ARCHIVE_REQUIRES_SANDBOX")
        self.assertIn(
            "ARCHIVE_REQUIRES_DEDICATED_ADAPTER",
            decision.reason_codes,
        )

    def test_nested_archive_is_quarantined(self):
        inner = _zip({"payload.txt": b"content"})
        decision = classify_payload(
            _zip({"nested.zip": inner}),
            ".zip",
        )
        self.assertEqual(decision.status, "QUARANTINED_SECURITY")
        self.assertIn(
            "NESTED_ARCHIVE_NOT_RECURSIVELY_INSPECTED",
            decision.reason_codes,
        )

    def test_ole_compound_is_quarantined_until_sandbox_adapter_exists(self):
        decision = classify_payload(
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 128,
            ".xls",
        )
        self.assertEqual(decision.status, "QUARANTINED_SECURITY")
        self.assertEqual(
            decision.detected_format,
            "OLE_COMPOUND_REQUIRES_SANDBOX",
        )

    def test_pdf_with_javascript_is_quarantined(self):
        decision = classify_payload(
            b"%PDF-1.7\n1 0 obj <</OpenAction 2 0 R /JavaScript true>>\n",
            ".pdf",
        )
        self.assertEqual(decision.status, "QUARANTINED_SECURITY")
        self.assertEqual(
            decision.detected_format,
            "PDF_ACTIVE_OR_ENCRYPTED_CONTENT",
        )

    def test_passive_pdf_is_accepted_partially_without_calculation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "report.pdf"
            source.write_bytes(b"%PDF-1.4\n1 0 obj <</Type /Catalog>>\n%%EOF")
            report = register_file(
                file_path=source,
                storage_root=root / "storage",
            )
        self.assertEqual(report["status"], "ACCEPTED_PARTIAL")
        self.assertEqual(report["detected_format"], "PDF")
        self.assertIsNone(report["calculation"])
        self.assertFalse(report["marketplace_write_enabled"])

    def test_quarantined_file_is_stored_only_in_quarantine_zone(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "legacy.xls"
            source.write_bytes(
                b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 128
            )
            report = register_file(
                file_path=source,
                storage_root=root / "storage",
            )
            stored = Path(str(report["stored_path"]))
            self.assertTrue(stored.is_file())
            self.assertIn("quarantine", stored.parts)
            self.assertNotIn("inbox", stored.parts)


if __name__ == "__main__":
    unittest.main()
