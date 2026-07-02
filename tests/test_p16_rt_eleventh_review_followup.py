import unittest

from tests.p16_fixtures import *  # noqa: F403


class P16EleventhReviewFollowupTests(unittest.TestCase):
    def test_unmodeled_root_relationship_child_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "_rels/.rels",
            lambda value: value.replace(
                b"</Relationships>",
                b"<Secret>hidden-commercial-text</Secret></Relationships>",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ROOT_RELATIONSHIP_INVALID")

    def test_root_relationship_extra_attribute_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "_rels/.rels",
            lambda value: value.replace(
                b'Id="rId1"',
                b'Id="rId1" secret="hidden-commercial-text"',
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ROOT_RELATIONSHIP_INVALID")

    def test_root_relationship_hidden_identifier_value_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "_rels/.rels",
            lambda value: value.replace(
                b'Id="rId1"',
                b'Id="customer_email_alice@example.com"',
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ROOT_RELATIONSHIP_INVALID")

    def test_root_relationship_unmodeled_target_mode_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "_rels/.rels",
            lambda value: value.replace(
                b'Target="xl/workbook.xml"',
                b'Target="xl/workbook.xml" TargetMode="hidden-commercial-text"',
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ROOT_RELATIONSHIP_INVALID")

    def test_root_relationship_internal_target_mode_is_allowed(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "_rels/.rels",
            lambda value: value.replace(
                b'Target="xl/workbook.xml"',
                b'Target="xl/workbook.xml" TargetMode="Internal"',
                1,
            ),
        )
        result = XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertIsNotNone(result.matched_schema_id)
        self.assertEqual(result.diagnostics, ())

    def test_defined_name_attribute_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/workbook.xml",
            lambda value: value.replace(
                b"</workbook>",
                b'<definedNames><definedName name="customer_email_alice@example.com"/>'
                b"</definedNames></workbook>",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")

    def test_unknown_workbook_view_attribute_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/workbook.xml",
            lambda value: value.replace(
                b"<sheets>",
                b'<bookViews><workbookView activeTab="0" secret="hidden"/>'
                b"</bookViews><sheets>",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_WORKBOOK_ATTRIBUTE_UNMODELED")

    def test_modeled_workbook_view_attribute_remains_allowed(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/workbook.xml",
            lambda value: value.replace(
                b"<sheets>",
                b'<bookViews><workbookView activeTab="0"/></bookViews><sheets>',
                1,
            ),
        )
        result = XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertIsNotNone(result.matched_schema_id)
        self.assertEqual(result.diagnostics, ())


if __name__ == "__main__":
    unittest.main()
