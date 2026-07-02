import unittest

from tests.p16_fixtures import *  # noqa: F403


class P16ThirteenthReviewFollowupTests(unittest.TestCase):
    def test_workbook_relationship_identifier_channel_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/workbook.xml",
            lambda value: value.replace(
                b'r:id="rId1"',
                b'r:id="customer_email_alice@example.com"',
                1,
            ),
        )
        payload = rewrite_xlsx_part(
            payload,
            "xl/_rels/workbook.xml.rels",
            lambda value: value.replace(
                b'Id="rId1"',
                b'Id="customer_email_alice@example.com"',
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertIn(
            error.exception.code,
            {"XLSX_SHEET_RELATIONSHIP_MISSING", "XLSX_WORKBOOK_RELATIONSHIPS_INVALID"},
        )

    def test_formula_text_identifier_channel_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(formula=True),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<f>1+1</f>",
                b"<f>customer_email_alice@example.com</f>",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy(formulas=1))
        self.assertEqual(error.exception.code, "XLSX_FORMULA_CONTENT_UNMODELED")

    def test_formula_attribute_identifier_channel_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(formula=True),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<f>1+1</f>",
                b'<f ca="customer_email_alice@example.com">1+1</f>',
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy(formulas=1))
        self.assertEqual(error.exception.code, "XLSX_FORMULA_CONTENT_UNMODELED")

    def test_modeled_formula_remains_allowed(self):
        result = XlsxPackageInspector().inspect(
            payload=build_xlsx(formula=True),
            policy=policy(formulas=1),
        )
        self.assertIsNotNone(result.matched_schema_id)
        self.assertEqual(result.formula_count, 1)
        self.assertEqual(result.diagnostics, ())

    def test_modeled_function_formula_remains_allowed(self):
        payload = rewrite_xlsx_part(
            build_xlsx(formula=True),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<f>1+1</f>",
                b"<f>SUM(A2:C2)</f>",
                1,
            ),
        )
        result = XlsxPackageInspector().inspect(
            payload=payload,
            policy=policy(formulas=1),
        )
        self.assertIsNotNone(result.matched_schema_id)
        self.assertEqual(result.formula_count, 1)
        self.assertEqual(result.diagnostics, ())


if __name__ == "__main__":
    unittest.main()
