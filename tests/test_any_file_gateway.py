from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from quantum.pilot.any_file_gateway import intake_file


SPREADSHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_PACKAGE = "http://schemas.openxmlformats.org/package/2006/relationships"
REL_OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CONTENT_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
AP = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"


def _config() -> dict:
    return {
        "tenant_id": "tenant-home-local",
        "account_id": "operator-home-local",
        "verifier_account_id": "verifier-home-local",
        "source_internal_id": "local-test",
        "marketplace": "WILDBERRIES",
        "report_type": "SALES_REPORT",
        "reporting_period_start": "2026-01-01",
        "reporting_period_end": "2026-01-31",
        "timezone": "Europe/Moscow",
        "expected_row_count": 1,
        "control_totals_sha256": None,
        "data_categories": ["FINANCIAL", "SALES"],
        "owner_authority_reference": "HOME-LOCAL-OWNER-REVIEW",
        "lawful_authority_attested": True,
        "retention_deadline": "2030-01-01T00:00:00Z",
        "malware_scan_evidence_sha256": "0" * 64,
        "attestations": {
            "source_authority_verified": True,
            "report_period_verified": True,
            "control_totals_verified": True,
            "direct_identifiers_absent_or_approved": True,
            "malware_scan_clean": True,
        },
        "inspection_policy": {
            "policy_id": "any-file-test",
            "version": 1,
            "limits": {
                "max_file_bytes": 10_000_000,
                "max_archive_entries": 100,
                "max_total_uncompressed_bytes": 20_000_000,
                "max_entry_uncompressed_bytes": 10_000_000,
                "max_compression_ratio": 200,
                "max_xml_bytes": 10_000_000,
                "max_rows": 1000,
                "max_columns": 500,
            },
            "schemas": [{
                "schema_id": "TEMPLATE",
                "schema_version": "1",
                "schema_authority_reference": "test",
                "direct_identifiers_expected": False,
                "package_kind": "XLSX",
                "sheet_name": "DISCOVERY_REQUIRED",
                "sheet_count": 1,
                "header_row_index": 1,
                "header_sha256": "0" * 64,
                "column_count": 1,
                "min_data_rows": 0,
                "max_data_rows": 1000,
                "max_formula_count": 0,
            }],
            "prohibited_header_tokens": ["email", "phone"],
        },
        "finance_request": None,
        "reconciliation": None,
        "execution_mode": "ADMISSION_ONLY",
    }


def _xlsx(*, unmodeled_app_version: bool = False) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            f'''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="{CONTENT_TYPES}">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>''',
        )
        archive.writestr(
            "_rels/.rels",
            f'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{REL_PACKAGE}">
<Relationship Id="rId1" Type="{REL_OFFICE}/officeDocument" Target="xl/workbook.xml"/>
<Relationship Id="rId2" Type="{REL_OFFICE}/extended-properties" Target="docProps/app.xml"/>
</Relationships>''',
        )
        archive.writestr(
            "xl/workbook.xml",
            f'''<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="{SPREADSHEET}" xmlns:r="{REL_OFFICE}">
<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>''',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            f'''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="{REL_PACKAGE}">
<Relationship Id="rId1" Type="{REL_OFFICE}/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>''',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f'''<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="{SPREADSHEET}">
<sheetData>
<row r="1">
<c r="A1" t="inlineStr"><is><t>Артикул</t></is></c>
<c r="B1" t="inlineStr"><is><t>Количество</t></is></c>
<c r="C1" t="inlineStr"><is><t>Сумма</t></is></c>
</row>
<row r="2">
<c r="A2" t="inlineStr"><is><t>SKU-1</t></is></c>
<c r="B2"><v>1</v></c>
<c r="C2"><v>100</v></c>
</row>
</sheetData>
</worksheet>''',
        )
        app = f'<Properties xmlns="{AP}"><Application>Microsoft Excel</Application>'
        if unmodeled_app_version:
            app += "<AppVersion>16.0300</AppVersion>"
        app += "</Properties>"
        archive.writestr("docProps/app.xml", app)
    return buffer.getvalue()


class AnyFileGatewayTests(unittest.TestCase):
    def _run(self, source: Path, storage: Path) -> dict:
        return intake_file(
            file_path=source,
            config=_config(),
            storage_root=storage,
            authority_attested=True,
            schema_reviewed=True,
        )

    def test_unknown_binary_is_accepted_unparsed_and_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "data.weird"
            source.write_bytes(b"\x01\x02\x03\x04opaque")
            report = self._run(source, root / "storage")
            self.assertEqual(report["status"], "ACCEPTED_UNPARSED")
            stored = root / "storage" / report["storage_relative_path"]
            self.assertEqual(stored.read_bytes(), source.read_bytes())

    def test_json_is_accepted_partial_without_raw_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "data.json"
            source.write_text(json.dumps({"a": 1, "b": 2}), encoding="utf-8")
            report = self._run(source, root / "storage")
            self.assertEqual(report["status"], "ACCEPTED_PARTIAL")
            self.assertEqual(report["parse"]["key_count"], 2)
            self.assertFalse(report["raw_rows_in_report"])

    def test_executable_is_quarantined(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "payload.bin"
            source.write_bytes(b"MZ" + b"\x00" * 20)
            report = self._run(source, root / "storage")
            self.assertEqual(report["status"], "QUARANTINED_SECURITY")
            self.assertIn("ANY_FILE_EXECUTABLE_FORBIDDEN", report["diagnostics"])
            self.assertIn("quarantine-security", report["storage_relative_path"])

    def test_zip_traversal_is_quarantined(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "bad.zip"
            buffer = BytesIO()
            with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
                archive.writestr("../escape.txt", "x")
            source.write_bytes(buffer.getvalue())
            report = self._run(source, root / "storage")
            self.assertEqual(report["status"], "QUARANTINED_SECURITY")
            self.assertIn("ANY_FILE_ARCHIVE_PATH_INVALID", report["diagnostics"])

    def test_standard_xlsx_is_strictly_admitted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "good.xlsx"
            source.write_bytes(_xlsx())
            report = self._run(source, root / "storage")
            self.assertEqual(report["status"], "ACCEPTED_PARSED")
            self.assertEqual(report["strict_admission"]["status"], "ADMISSION_COMPLETE")
            self.assertEqual(report["parse"]["data_row_count"], 1)

    def test_unmodeled_office_metadata_degrades_to_partial(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "summary.xlsx"
            source.write_bytes(_xlsx(unmodeled_app_version=True))
            report = self._run(source, root / "storage")
            self.assertEqual(report["status"], "ACCEPTED_PARTIAL")
            self.assertIn("XLSX_AUXILIARY_CONTENT_UNMODELED", report["diagnostics"])
            self.assertEqual(report["parse"]["column_count"], 3)
            self.assertIn("STRICT_XLSX_MODEL_LIMITATION", report["limitations"])

    def test_source_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "data.json"
            source.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ANY_FILE_SOURCE_HASH_MISMATCH"):
                intake_file(
                    file_path=source,
                    config=_config(),
                    storage_root=root / "storage",
                    authority_attested=True,
                    schema_reviewed=True,
                    expected_file_sha256="0" * 64,
                )


if __name__ == "__main__":
    unittest.main()
