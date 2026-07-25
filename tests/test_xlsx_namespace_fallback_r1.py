from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from quantum.application._finance_schema_review import build_schema_review_preview
from quantum.pilot.universal_intake import register_file
from quantum.pilot.universal_tables import extract_tables
from tests.test_xlsx_real_office_compat import (
    REL_OFFICE,
    REL_PACKAGE,
    SPREADSHEET,
    build_realistic_xlsx,
)


STRICT_SPREADSHEET = "http://purl.oclc.org/ooxml/spreadsheetml/main"
STRICT_REL_PACKAGE = "http://purl.oclc.org/ooxml/package/relationships"
STRICT_REL_OFFICE = "http://purl.oclc.org/ooxml/officeDocument/relationships"


def _config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "reporting_period_start": "2026-01-01",
                "reporting_period_end": "2026-07-04",
                "inspection_policy": {
                    "limits": {
                        "max_file_bytes": 10_485_760,
                        "max_archive_entries": 1000,
                        "max_total_uncompressed_bytes": 52_428_800,
                        "max_entry_uncompressed_bytes": 10_485_760,
                        "max_compression_ratio": 100,
                        "max_xml_bytes": 10_485_760,
                        "max_rows": 10_000,
                        "max_columns": 256,
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _rewrite_xlsx(payload: bytes, changes: dict[str, tuple[bytes, bytes]]) -> bytes:
    output = BytesIO()
    with ZipFile(BytesIO(payload), "r") as source, ZipFile(
        output, "w", compression=ZIP_DEFLATED
    ) as target:
        for info in source.infolist():
            data = source.read(info)
            if info.filename in changes:
                old, new = changes[info.filename]
                if old not in data:
                    raise AssertionError(f"mutation marker not found: {info.filename}")
                data = data.replace(old, new, 1)
            target.writestr(info, data)
    return output.getvalue()


def _strict_namespace_workbook() -> bytes:
    payload = build_realistic_xlsx()
    payload = _rewrite_xlsx(
        payload,
        {
            "[Content_Types].xml": (
                b"http://schemas.openxmlformats.org/package/2006/content-types",
                b"http://purl.oclc.org/ooxml/package/content-types",
            ),
            "_rels/.rels": (REL_PACKAGE.encode(), STRICT_REL_PACKAGE.encode()),
            "xl/workbook.xml": (SPREADSHEET.encode(), STRICT_SPREADSHEET.encode()),
            "xl/_rels/workbook.xml.rels": (
                REL_PACKAGE.encode(), STRICT_REL_PACKAGE.encode()
            ),
            "xl/worksheets/sheet1.xml": (
                SPREADSHEET.encode(), STRICT_SPREADSHEET.encode()
            ),
        },
    )
    return _rewrite_xlsx(
        payload,
        {
            "_rels/.rels": (REL_OFFICE.encode(), STRICT_REL_OFFICE.encode()),
            "xl/workbook.xml": (REL_OFFICE.encode(), STRICT_REL_OFFICE.encode()),
            "xl/_rels/workbook.xml.rels": (
                REL_OFFICE.encode(), STRICT_REL_OFFICE.encode()
            ),
        },
    )


def _external_relationship_workbook() -> bytes:
    return _rewrite_xlsx(
        build_realistic_xlsx(),
        {
            "xl/_rels/workbook.xml.rels": (
                b'Target="worksheets/sheet1.xml"',
                b'Target="https://example.invalid/sheet1.xml" TargetMode="External"',
            )
        },
    )


def _entity_workbook() -> bytes:
    return _rewrite_xlsx(
        build_realistic_xlsx(),
        {
            "xl/worksheets/sheet1.xml": (
                b'<worksheet xmlns="',
                b'<!DOCTYPE worksheet [<!ENTITY xxe "forbidden">]><worksheet xmlns="',
            )
        },
    )


def _formula_workbook() -> bytes:
    return _rewrite_xlsx(
        build_realistic_xlsx(),
        {
            "xl/worksheets/sheet1.xml": (
                b'<c r="C2"><v>100</v></c>',
                b'<c r="C2"><f>1+1</f><v>999</v></c>',
            )
        },
    )


class XlsxNamespaceFallbackR1Tests(unittest.TestCase):
    def test_unknown_namespace_no_longer_blocks_schema_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "report.xlsx"
            config = root / "config.json"
            source.write_bytes(build_realistic_xlsx(used_unknown=True))
            _config(config)
            preview = build_schema_review_preview(source, config)
            self.assertFalse(preview.requires_schema_review)
            self.assertEqual("UNIVERSAL_FALLBACK", preview.inspection_status)
            self.assertIn("XLSX_XML_NAMESPACE_UNMODELED", preview.diagnostic_codes)
            self.assertEqual(
                ("Артикул", "Количество продаж", "Сумма продаж"),
                preview.headers,
            )
            self.assertEqual(1, preview.data_row_count)
            self.assertIn("универсальную обработку", preview.confirmation_text())

    def test_unknown_namespace_extracts_available_table(self) -> None:
        result = extract_tables(
            build_realistic_xlsx(used_unknown=True), source_name="report.xlsx"
        )
        self.assertEqual("COMPLETE", result.status)
        self.assertEqual(1, len(result.tables))
        self.assertEqual("SKU-1", result.tables[0].rows[0]["Артикул"])
        self.assertEqual("100", result.tables[0].rows[0]["Сумма продаж"])
        self.assertIn("XLSX_NAMESPACE_TOLERANT_SAFE_PARSE", result.reason_codes)

    def test_strict_ooxml_namespaces_extract_same_rows(self) -> None:
        result = extract_tables(_strict_namespace_workbook(), source_name="strict.xlsx")
        self.assertEqual("COMPLETE", result.status)
        self.assertEqual("SKU-1", result.tables[0].rows[0]["Артикул"])
        self.assertEqual("1", result.tables[0].rows[0]["Количество продаж"])

    def test_registration_accepts_namespace_extended_workbook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "report.xlsx"
            source.write_bytes(build_realistic_xlsx(used_unknown=True))
            report = register_file(
                file_path=source,
                storage_root=root / "storage",
                malware_scan_evidence_sha256="0" * 64,
                malware_scan_outcome="CLEAN",
            )
            self.assertEqual("ACCEPTED_PARTIAL", report["status"])
            self.assertEqual(1, report["universal_extraction"]["table_count"])
            self.assertTrue(Path(str(report["stored_path"])).is_file())

    def test_external_relationship_remains_quarantined(self) -> None:
        result = extract_tables(
            _external_relationship_workbook(), source_name="external.xlsx"
        )
        self.assertEqual("QUARANTINED_SECURITY", result.status)
        self.assertIn(
            "UNIVERSAL_XLSX_EXTERNAL_RELATIONSHIP_FORBIDDEN",
            result.reason_codes,
        )

    def test_registration_quarantines_external_relationship(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "external.xlsx"
            source.write_bytes(_external_relationship_workbook())
            report = register_file(
                file_path=source,
                storage_root=root / "storage",
                malware_scan_evidence_sha256="0" * 64,
                malware_scan_outcome="CLEAN",
            )
            self.assertEqual("QUARANTINED_SECURITY", report["status"])
            self.assertIn("quarantine", str(report["stored_path"]).casefold())

    def test_xml_entity_declaration_remains_quarantined(self) -> None:
        result = extract_tables(_entity_workbook(), source_name="entity.xlsx")
        self.assertEqual("QUARANTINED_SECURITY", result.status)
        self.assertIn("XLSX_XML_ENTITY_DECLARATION_FORBIDDEN", result.reason_codes)

    def test_formula_cached_value_is_not_treated_as_observed_data(self) -> None:
        result = extract_tables(_formula_workbook(), source_name="formula.xlsx")
        self.assertEqual("COMPLETE", result.status)
        self.assertEqual("", result.tables[0].rows[0]["Сумма продаж"])
        self.assertIn("XLSX_FORMULA_VALUES_OMITTED", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
