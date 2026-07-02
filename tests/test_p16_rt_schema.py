import unittest
from tests.p16_fixtures import *  # noqa: F403


class P16RedTeamSchemaTests(unittest.TestCase):
    def test_duplicate_match_profile_is_rejected(self):
        base = policy()
        first = base.schemas[0]
        duplicate = replace(first, schema_id="other-id", schema_authority_reference="review-2")
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxInspectionPolicy(
                policy_id="ambiguous",
                version=1,
                limits=base.limits,
                schemas=(first, duplicate),
                prohibited_header_tokens=base.prohibited_header_tokens,
            )
        self.assertEqual(error.exception.code, "XLSX_SCHEMA_PROFILE_AMBIGUOUS")

    def test_overlapping_profiles_fail_closed(self):
        base = policy()
        first = base.schemas[0]
        overlapping = replace(first, schema_id="overlap", schema_authority_reference="review-2", max_data_rows=200)
        result = XlsxPackageInspector().inspect(
            payload=build_xlsx(),
            policy=XlsxInspectionPolicy(
                policy_id="overlap-policy",
                version=1,
                limits=base.limits,
                schemas=(first, overlapping),
                prohibited_header_tokens=base.prohibited_header_tokens,
            ),
        )
        self.assertFalse(result.matched)
        self.assertIn("XLSX_SCHEMA_MATCH_AMBIGUOUS", result.diagnostics)

    def test_non_header_cell_row_mismatch_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(b'r="A2"', b'r="A999"', 1),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_CELL_ROW_MISMATCH")

    def test_empty_data_row_is_not_counted(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b'<row r="2"><c r="A2" t="inlineStr"><is><t>1</t></is></c><c r="B2" t="inlineStr"><is><t>SALE</t></is></c><c r="C2" t="inlineStr"><is><t>100.00</t></is></c></row>',
                b'<row r="2"></row>',
            ),
        )
        result = XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(result.data_row_count, 0)
        self.assertIn("XLSX_ROW_COUNT_OUT_OF_RANGE", result.diagnostics)

    def test_punctuation_cannot_bypass_identifier_token(self):
        headers = ("operation_id", "e" + "-mail", "amount")
        result = XlsxPackageInspector().inspect(
            payload=build_xlsx(headers=headers),
            policy=policy(headers=headers),
        )
        self.assertEqual(result.prohibited_header_count, 1)
        self.assertIn("XLSX_DIRECT_IDENTIFIER_HEADER_PRESENT", result.diagnostics)


if __name__ == "__main__":
    unittest.main()
