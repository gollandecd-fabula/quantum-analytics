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
from quantum.pilot.universal_import import classify_payload, register_file
from tests.p16_fixtures import build_xlsx


HEADERS = ("Артикул", "Количество продаж", "Сумма продаж")
REL_PACKAGE = "http://schemas.openxmlformats.org/package/2006/relationships"
REL_OFFICE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
EXTENDED_PROPERTIES = (
    "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
)
ACTIVE_X = "http://schemas.microsoft.com/office/2006/activeX"


def _baseline_xlsx() -> bytes:
    return build_xlsx(
        headers=HEADERS,
        rows=(("SKU-1", "1", "100.00"),),
    )


def _with_app_metadata(*, company: str = "Wildberries", active: bool = False) -> bytes:
    source = _baseline_xlsx()
    with ZipFile(BytesIO(source)) as archive:
        entries = {
            info.filename: archive.read(info)
            for info in archive.infolist()
            if not info.is_dir()
        }
    content_types = entries["[Content_Types].xml"].decode("utf-8")
    content_types = content_types.replace(
        "</Types>",
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>",
    )
    entries["[Content_Types].xml"] = content_types.encode("utf-8")
    root_rels = entries["_rels/.rels"].decode("utf-8")
    root_rels = root_rels.replace(
        "</Relationships>",
        f'<Relationship Id="rId2" Type="{REL_OFFICE}/extended-properties" '
        'Target="docProps/app.xml"/></Relationships>',
    )
    entries["_rels/.rels"] = root_rels.encode("utf-8")
    active_namespace = f' xmlns:ax="{ACTIVE_X}"' if active else ""
    active_element = "<ax:payload/>" if active else ""
    entries["docProps/app.xml"] = (
        f'<Properties xmlns="{EXTENDED_PROPERTIES}"{active_namespace}>'
        "<Application>Microsoft Excel</Application>"
        f"<Company>{company}</Company>{active_element}</Properties>"
    ).encode("utf-8")
    target = BytesIO()
    with ZipFile(target, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return target.getvalue()


def _policy(policy_id: str) -> XlsxInspectionPolicy:
    limits = XlsxInspectionLimits(
        max_file_bytes=2_000_000,
        max_archive_entries=128,
        max_total_uncompressed_bytes=4_000_000,
        max_entry_uncompressed_bytes=2_000_000,
        max_compression_ratio=200,
        max_xml_bytes=1_000_000,
        max_rows=1000,
        max_columns=100,
    )
    schema = XlsxSchemaExpectation(
        schema_id="universal-r4",
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
        policy_id=policy_id,
        version=1,
        limits=limits,
        schemas=(schema,),
        prohibited_header_tokens=("email", "phone"),
    )


def _archive(entries: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return output.getvalue()


class UniversalGatewayTests(unittest.TestCase):
    def test_valid_xlsx_routes_to_existing_xlsx_pipeline(self):
        decision = classify_payload(_baseline_xlsx(), ".xlsx")
        self.assertEqual(decision.status, "ROUTE_XLSX")
        self.assertEqual(decision.route, "XLSX")
        self.assertEqual(decision.detected_format, "XLSX")

    def test_standard_relationship_type_uri_is_not_treated_as_external_target(self):
        decision = classify_payload(_baseline_xlsx(), ".xlsx")
        self.assertEqual(decision.status, "ROUTE_XLSX")

    def test_external_relationship_is_quarantined(self):
        payload = _archive(
            {
                "_rels/.rels": (
                    f'<Relationships xmlns="{REL_PACKAGE}">'
                    f'<Relationship Id="rId1" Type="{REL_OFFICE}/officeDocument" '
                    'Target="https://example.invalid/report.xlsx" TargetMode="External"/>'
                    "</Relationships>"
                ).encode("utf-8"),
                "data.txt": b"safe",
            }
        )
        decision = classify_payload(payload, ".zip")
        self.assertEqual(decision.status, "QUARANTINED_SECURITY")
        self.assertEqual(
            decision.detected_format,
            "ARCHIVE_EXTERNAL_RELATIONSHIP_FORBIDDEN",
        )

    def test_executable_magic_is_quarantined_even_with_text_extension(self):
        decision = classify_payload(b"MZ" + b"0" * 64, ".txt")
        self.assertEqual(decision.status, "QUARANTINED_SECURITY")

    def test_executable_inside_archive_is_quarantined(self):
        decision = classify_payload(
            _archive({"documents/report.txt": b"ok", "payload.bin": b"MZevil"}),
            ".zip",
        )
        self.assertEqual(decision.status, "QUARANTINED_SECURITY")
        self.assertEqual(decision.detected_format, "ARCHIVE_ACTIVE_CONTENT_FORBIDDEN")

    def test_path_traversal_archive_is_quarantined(self):
        decision = classify_payload(_archive({"../escape.txt": b"bad"}), ".zip")
        self.assertEqual(decision.status, "QUARANTINED_SECURITY")
        self.assertEqual(decision.detected_format, "ARCHIVE_PATH_INVALID")

    def test_xml_entity_declaration_is_quarantined(self):
        decision = classify_payload(
            b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY y "z">]><x>&y;</x>',
            ".xml",
        )
        self.assertEqual(decision.status, "QUARANTINED_SECURITY")

    def test_json_table_is_partially_extracted_without_raw_rows(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "report.json"
            source.write_text(
                json.dumps([{"sku": "A", "sales": 1}], ensure_ascii=False),
                encoding="utf-8",
            )
            report = register_file(file_path=source, storage_root=root / "storage")
            self.assertEqual(report["status"], "ACCEPTED_PARTIAL")
            self.assertEqual(report["detected_format"], "JSON_TABLE")
            self.assertEqual(report["metadata"]["headers"], ["sales", "sku"])
            self.assertFalse(report["raw_rows_in_report"])
            self.assertTrue(Path(report["stored_path"]).is_file())
            self.assertIsNone(report["calculation"])

    def test_cp1251_delimited_text_is_detected(self):
        decision = classify_payload(
            "Артикул;Продажи\nSKU-1;2\n".encode("cp1251"),
            ".csv",
        )
        self.assertEqual(decision.status, "ACCEPTED_PARTIAL")
        self.assertEqual(decision.detected_format, "DELIMITED_TEXT")
        self.assertEqual(decision.metadata["delimiter"], ";")

    def test_unknown_binary_is_preserved_as_unparsed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "opaque.bin"
            source.write_bytes(bytes(range(64)) * 4)
            report = register_file(file_path=source, storage_root=root / "storage")
            self.assertEqual(report["status"], "ACCEPTED_UNPARSED")
            self.assertEqual(report["detected_format"], "UNKNOWN_BINARY")
            self.assertTrue(Path(report["stored_path"]).is_file())

    def test_missing_file_returns_deterministic_error_report(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report = register_file(
                file_path=root / "missing.bin",
                storage_root=root / "storage",
            )
            self.assertEqual(report["status"], "ERROR")
            self.assertEqual(report["reason_codes"], ["FILE_NOT_FOUND"])
            self.assertFalse(report["marketplace_write_enabled"])


class PassiveAuxiliaryCompatibilityTests(unittest.TestCase):
    def test_strict_policy_rejects_unmodeled_company_metadata(self):
        with self.assertRaises(XlsxInspectionError) as captured:
            XlsxPackageInspector().inspect(
                payload=_with_app_metadata(),
                policy=_policy("strict-test-policy"),
            )
        self.assertEqual(
            captured.exception.code,
            "XLSX_AUXILIARY_CONTENT_UNMODELED",
        )

    def test_home_local_policy_hash_binds_passive_company_metadata(self):
        first = XlsxPackageInspector().inspect(
            payload=_with_app_metadata(company="Wildberries"),
            policy=_policy("wb-home-local-discovery"),
        )
        second = XlsxPackageInspector().inspect(
            payload=_with_app_metadata(company="Marketplace"),
            policy=_policy("wb-home-local-discovery"),
        )
        self.assertTrue(first.matched)
        self.assertEqual(first.diagnostics, ())
        self.assertNotEqual(
            first.structural_fingerprint_sha256,
            second.structural_fingerprint_sha256,
        )

    def test_active_namespace_inside_passive_part_remains_blocked(self):
        with self.assertRaises(XlsxInspectionError) as captured:
            XlsxPackageInspector().inspect(
                payload=_with_app_metadata(active=True),
                policy=_policy("wb-home-local-discovery"),
            )
        self.assertEqual(
            captured.exception.code,
            "XLSX_AUXILIARY_COMPAT_ACTIVE_CONTENT",
        )


if __name__ == "__main__":
    unittest.main()
