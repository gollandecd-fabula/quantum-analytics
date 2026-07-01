import unittest

from tests.p16_fixtures import *  # noqa: F403


class P16RedTeamRelationshipTests(unittest.TestCase):
    def test_uri_target_without_external_mode_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/_rels/workbook.xml.rels",
            lambda value: value.replace(
                b'Target="worksheets/sheet1.xml"',
                b'Target="https://example.invalid/sheet1.xml"',
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_EXTERNAL_RELATIONSHIP_FORBIDDEN",
        )

    def test_sheet_binding_requires_worksheet_relationship_type(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/_rels/workbook.xml.rels",
            lambda value: value.replace(
                b"/relationships/worksheet\"",
                b"/relationships/styles\"",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_WORKSHEET_RELATIONSHIP_TYPE_INVALID",
        )

    def test_root_binding_requires_office_document_type(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "_rels/.rels",
            lambda value: value.replace(
                b"/relationships/officeDocument\"",
                b"/relationships/styles\"",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_ROOT_RELATIONSHIP_INVALID",
        )

    def test_root_binding_requires_workbook_target(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "_rels/.rels",
            lambda value: value.replace(
                b'Target="xl/workbook.xml"',
                b'Target="xl/worksheets/sheet1.xml"',
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_ROOT_RELATIONSHIP_INVALID",
        )


if __name__ == "__main__":
    unittest.main()
