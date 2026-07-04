from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from quantum.ingestion._xlsx_contracts import (
    XlsxInspectionError,
    XlsxInspectionLimits,
    XlsxInspectionPolicy,
    XlsxSchemaExpectation,
    normalized_header_sha256,
)
from quantum.ingestion.xlsx_inspection import XlsxPackageInspector
from quantum.pilot.universal_import import register_file


SPREADSHEET = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_PACKAGE = "http://schemas.openxmlformats.org/package/2006/relationships"
REL_OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CONTENT_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
EXTENDED_PROPERTIES = (
    "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
)
HEADERS = ("Артикул", "Продажа", "Итого")


def _xlsx_with_unmodeled_app_property() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            f'''<Types xmlns="{CONTENT_TYPES}">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>''',
        )
        archive.writestr(
            "_rels/.rels",
            f'''<Relationships xmlns="{REL_PACKAGE}">
<Relationship Id="rId1" Type="{REL_OFFICE}/officeDocument" Target="xl/workbook.xml"/>
</Relationships>''',
        )
        archive.writestr(
            "xl/workbook.xml",
            f'''<workbook xmlns="{SPREADSHEET}" xmlns:r="{REL_OFFICE}">
<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>''',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            f'''<Relationships xmlns="{REL_PACKAGE}">
<Relationship Id="rId1" Type="{REL_OFFICE}/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>''',
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            f'''<worksheet xmlns="{SPREADSHEET}"><sheetData>
<row r="1"><c r="A1" t="inlineStr"><is><t>{HEADERS[0]}</t></is></c><c r="B1" t="inlineStr"><is><t>{HEADERS[1]}</t></is></c><c r="C1" t="inlineStr"><is><t>{HEADERS[2]}</t></is></c></row>
<row r="2"><c r="A2" t="inlineStr"><is><t>SKU</t></is></c><c r="B2"><v>1</v></c><c r="C2"><v>100</v></c></row>
</sheetData></worksheet>''',
        )
        archive.writestr(
            "docProps/app.xml",
            f'''<Properties xmlns="{EXTENDED_PROPERTIES}">
<Application>Microsoft Excel</Application><Company>Wildberries</Company>
</Properties>''',
        )
    return buffer.getvalue()


def _policy(*, compatibility: bool) -> XlsxInspectionPolicy:
    limits = XlsxInspectionLimits(
        max_file_bytes=2_000_000,
        max_archive_entries=64,
        max_total_uncompressed_bytes=4_000_000,
        max_entry_uncompressed_bytes=2_000_000,
        max_compression_ratio=200,
        max_xml_bytes=1_000_000,
        max_rows=1000,
        max_columns=100,
    )
    schema = XlsxSchemaExpectation(
        schema_id="universal-r3",
        schema_version="1",
        schema_authority_reference="test",
        direct_identifiers_expected=False,
        package_kind="XLSX",
        sheet_name="Sheet1",
        sheet_count=1,
        header_row_index=1,
        header_sha256=normalized_header_sha256(HEADERS),
        column_count=3,
        min_data_rows=1,
        max_data_rows=10,
        max_formula_count=0,
    )
    return XlsxInspectionPolicy(
        policy_id=(
            "wb-home-local-discovery"
            if compatibility
            else "universal-r3-policy"
        ),
        version=1,
        limits=limits,
        schemas=(schema,),
        prohibited_header_tokens=("email", "phone"),
    )


class AuxiliaryCompatibilityTests(unittest.TestCase):
    def test_strict_policy_still_rejects_unmodeled_auxiliary_content(self):
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(
                payload=_xlsx_with_unmodeled_app_property(),
                policy=_policy(compatibility=False),
            )
        self.assertEqual(error.exception.code, "XLSX_AUXILIARY_CONTENT_UNMODELED")

    def test_home_local_compatibility_accepts_auxiliary_content(self):
        inspection = XlsxPackageInspector().inspect(
            payload=_xlsx_with_unmodeled_app_property(),
            policy=_policy(compatibility=True),
        )
        self.assertTrue(inspection.matched)
        self.assertEqual(inspection.diagnostics, ())
        self.assertEqual(inspection.data_row_count, 1)


class UniversalImportTests(unittest.TestCase):
    def test_unknown_binary_is_preserved_as_unparsed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "opaque.bin"
            source.write_bytes(b"opaque\x00payload")
            report = register_file(file_path=source, storage_root=root / "storage")
            self.assertEqual(report["status"], "ACCEPTED_UNPARSED")
            self.assertTrue(Path(report["stored_path"]).is_file())

    def test_json_is_accepted_partially(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "data.json"
            source.write_text(json.dumps({"value": 1}), encoding="utf-8")
            report = register_file(file_path=source, storage_root=root / "storage")
            self.assertEqual(report["status"], "ACCEPTED_PARTIAL")
            self.assertEqual(report["detected_format"], "JSON")

    def test_executable_is_quarantined(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "bad.exe"
            source.write_bytes(b"MZ" + b"0" * 32)
            report = register_file(file_path=source, storage_root=root / "storage")
            self.assertEqual(report["status"], "QUARANTINED_SECURITY")
            self.assertIn("quarantine", report["stored_path"])

    def test_xlsx_is_routed_without_duplicate_storage(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "report.xlsx"
            source.write_bytes(_xlsx_with_unmodeled_app_property())
            report = register_file(file_path=source, storage_root=root / "storage")
            self.assertEqual(report["status"], "ROUTE_XLSX")
            self.assertIsNone(report["stored_path"])


if __name__ == "__main__":
    unittest.main()
