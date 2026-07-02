import unittest
from io import BytesIO
from zipfile import ZipFile

from tests.p16_fixtures import *  # noqa: F403


def _with_zip_comment(payload: bytes) -> bytes:
    buffer = BytesIO(payload)
    with ZipFile(buffer, "a") as zf:
        zf.comment = b"hidden-commercial-suffix"
    return buffer.getvalue()


class P16NinthReviewFollowupTests(unittest.TestCase):
    def test_zip_comment_is_rejected(self):
        payload = _with_zip_comment(build_xlsx())
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ARCHIVE_POLYGLOT_FORBIDDEN")

    def test_xml_comment_is_rejected_before_parsing(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<sheetData>",
                b"<!-- hidden-commercial-text --><sheetData>",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_XML_COMMENT_FORBIDDEN")

    def test_xml_processing_instruction_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<sheetData>",
                b"<?hidden commercial-data?><sheetData>",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_XML_PROCESSING_INSTRUCTION_FORBIDDEN",
        )

    def test_workbook_defined_name_text_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/workbook.xml",
            lambda value: value.replace(
                b"</workbook>",
                b'<definedNames><definedName name="secret">'
                b"hidden-commercial-text"
                b"</definedName></definedNames></workbook>",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_WORKBOOK_TEXT_UNMODELED")

    def test_standard_text_free_workbook_view_is_allowed(self):
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
