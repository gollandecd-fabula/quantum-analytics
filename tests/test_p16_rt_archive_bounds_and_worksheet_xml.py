import unittest

from tests.p16_fixtures import *  # noqa: F403


class P16ArchiveBoundsAndWorksheetXmlTests(unittest.TestCase):
    def test_direct_xlsx_rejects_prefix_and_suffix_bytes(self):
        workbook = build_xlsx()
        payloads = {
            "prefix": b"unmodeled-prefix" + workbook,
            "suffix": workbook + b"unmodeled-suffix",
        }
        for name, payload in payloads.items():
            with self.subTest(name=name):
                with self.assertRaises(XlsxInspectionError) as error:
                    XlsxPackageInspector().inspect(payload=payload, policy=policy())
                self.assertEqual(
                    error.exception.code,
                    "XLSX_ARCHIVE_POLYGLOT_FORBIDDEN",
                )

    def test_wrapped_xlsx_rejects_inner_prefix_bytes(self):
        workbook = b"unmodeled-prefix" + build_xlsx()
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(
                payload=wrap_xlsx(workbook),
                policy=policy(),
            )
        self.assertEqual(
            error.exception.code,
            "XLSX_ARCHIVE_POLYGLOT_FORBIDDEN",
        )

    def test_hidden_text_outside_sheet_data_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"</worksheet>",
                b"<extLst><ext><secret>hidden-text</secret></ext>"
                b"</extLst></worksheet>",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_UNMODELED_WORKSHEET_TEXT",
        )

    def test_standard_text_free_worksheet_structure_is_allowed(self):
        structure = (
            b'<dimension ref="A1:C2"/>'
            b'<sheetViews><sheetView workbookViewId="0">'
            b'<selection activeCell="A1" sqref="A1"/>'
            b"</sheetView></sheetViews>"
            b'<sheetFormatPr defaultRowHeight="15"/>'
        )
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<sheetData>",
                structure + b"<sheetData>",
                1,
            ),
        )
        result = XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertIsNotNone(result.matched_schema_id)
        self.assertEqual(result.diagnostics, ())


if __name__ == "__main__":
    unittest.main()
