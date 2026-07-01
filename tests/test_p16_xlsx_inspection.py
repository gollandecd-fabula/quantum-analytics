import unittest

from tests.p16_fixtures import *  # noqa: F403
class XlsxPackageInspectorTests(unittest.TestCase):
    def test_direct_xlsx_matches_without_exposing_headers(self):
        payload = build_xlsx()
        result = XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertTrue(result.matched)
        self.assertEqual(result.package_kind, "XLSX")
        self.assertEqual(result.data_row_count, 1)
        self.assertEqual(result.formula_count, 0)
        serialized = json.dumps(result.__dict__ if hasattr(result, "__dict__") else {
            field: getattr(result, field) for field in result.__dataclass_fields__
        })
        self.assertNotIn("operation_id", serialized)
        self.assertNotIn("SALE", serialized)

    def test_outer_zip_with_one_xlsx_matches(self):
        payload = wrap_xlsx(build_xlsx())
        result = XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertTrue(result.matched)
        self.assertEqual(result.package_kind, "ZIP_XLSX")

    def test_unknown_headers_remain_unmatched(self):
        result = XlsxPackageInspector().inspect(
            payload=build_xlsx(headers=("other", "columns", "here")),
            policy=policy(),
        )
        self.assertFalse(result.matched)
        self.assertIn("XLSX_SCHEMA_UNKNOWN", result.diagnostics)
        self.assertIn("XLSX_HEADER_HASH_MISMATCH", result.diagnostics)

    def test_direct_identifier_header_blocks_schema(self):
        headers = ("operation_id", "customer phone", "amount")
        result = XlsxPackageInspector().inspect(
            payload=build_xlsx(headers=headers),
            policy=policy(headers=headers),
        )
        self.assertFalse(result.matched)
        self.assertEqual(result.prohibited_header_count, 1)
        self.assertIn("XLSX_DIRECT_IDENTIFIER_HEADER_PRESENT", result.diagnostics)

    def test_formula_exceeding_schema_limit_is_quarantinable_mismatch(self):
        result = XlsxPackageInspector().inspect(
            payload=build_xlsx(formula=True),
            policy=policy(formulas=0),
        )
        self.assertFalse(result.matched)
        self.assertIn("XLSX_FORMULA_COUNT_EXCEEDED", result.diagnostics)

    def test_macro_is_hard_rejected(self):
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=build_xlsx(macro=True), policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ACTIVE_CONTENT_FORBIDDEN")

    def test_external_relationship_is_hard_rejected(self):
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=build_xlsx(external=True), policy=policy())
        self.assertEqual(error.exception.code, "XLSX_EXTERNAL_RELATIONSHIP_FORBIDDEN")

    def test_doctype_is_hard_rejected(self):
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=build_xlsx(doctype=True), policy=policy())
        self.assertEqual(error.exception.code, "XLSX_XML_ENTITY_DECLARATION_FORBIDDEN")

    def test_zip_slip_is_hard_rejected(self):
        payload = wrap_xlsx(build_xlsx(), name="../weekly-report.xlsx")
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ARCHIVE_PATH_INVALID")

    def test_outer_archive_with_extra_file_is_rejected(self):
        buffer = BytesIO()
        with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as zf:
            zf.writestr("weekly-report.xlsx", build_xlsx())
            zf.writestr("note.txt", b"extra")
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=buffer.getvalue(), policy=policy())
        self.assertEqual(error.exception.code, "XLSX_OUTER_ARCHIVE_CONTENT_INVALID")

    def test_policy_hash_is_deterministic(self):
        self.assertEqual(policy().content_hash, policy().content_hash)
        self.assertEqual(len(policy().content_hash), 64)

    def test_extra_sheet_prevents_schema_match(self):
        result = XlsxPackageInspector().inspect(
            payload=build_xlsx(extra_sheet=True),
            policy=policy(),
        )
        self.assertFalse(result.matched)
        self.assertEqual(result.sheet_count, 2)
        self.assertIn("XLSX_SHEET_COUNT_MISMATCH", result.diagnostics)

    def test_compression_ratio_limit_is_enforced(self):
        base = policy()
        strict = XlsxInspectionPolicy(
            policy_id=base.policy_id,
            version=base.version + 1,
            limits=replace(base.limits, max_compression_ratio=1),
            schemas=base.schemas,
            prohibited_header_tokens=base.prohibited_header_tokens,
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=build_xlsx(), policy=strict)
        self.assertEqual(
            error.exception.code,
            "XLSX_ARCHIVE_COMPRESSION_RATIO_EXCEEDED",
        )

    def test_row_index_above_limit_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(b'<row r="2">', b'<row r="1001">'),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ROW_INDEX_INVALID")

    def test_header_cell_row_mismatch_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(b'<c r="A1"', b'<c r="A2"', 1),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_CELL_ROW_MISMATCH")

    def test_schema_profile_cannot_approve_direct_identifiers(self):
        base = policy().schemas[0]
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxSchemaExpectation(
                schema_id=base.schema_id,
                schema_version=base.schema_version,
                schema_authority_reference=base.schema_authority_reference,
                direct_identifiers_expected=True,
                package_kind=base.package_kind,
                sheet_name=base.sheet_name,
                sheet_count=base.sheet_count,
                header_row_index=base.header_row_index,
                header_sha256=base.header_sha256,
                column_count=base.column_count,
                min_data_rows=base.min_data_rows,
                max_data_rows=base.max_data_rows,
                max_formula_count=base.max_formula_count,
            )
        self.assertEqual(
            error.exception.code,
            "XLSX_PERSONAL_DATA_SCHEMA_NOT_APPROVED",
        )

    def test_schema_authority_is_bound_to_match(self):
        result = XlsxPackageInspector().inspect(
            payload=build_xlsx(),
            policy=policy(),
        )
        self.assertEqual(
            result.matched_schema_authority_reference,
            "schema-review-001",
        )



if __name__ == "__main__":
    unittest.main()
