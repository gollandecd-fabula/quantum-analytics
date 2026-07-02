import unittest
from tests.p16_fixtures import *  # noqa: F403


class P16RedTeamTopologyTests(unittest.TestCase):
    def test_cell_outside_row_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"</sheetData>",
                b'<c r="D2" t="inlineStr"><is><t>hidden</t></is></c></sheetData>',
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_CELL_OUTSIDE_ROW")

    def test_multiple_sheet_data_nodes_are_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(b"</worksheet>", b"<sheetData></sheetData></worksheet>"),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_SHEET_DATA_STRUCTURE_INVALID")

    def test_utf16_xml_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda _value: '<?xml version="1.0" encoding="UTF-16"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>'.encode("utf-16"),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_XML_ENCODING_UNSUPPORTED")

    def test_orphan_worksheet_part_is_rejected(self):
        secret = b'''<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>customer phone</t></is></c></row></sheetData>
</worksheet>'''
        payload = build_xlsx(
            extra_entries={"xl/worksheets/secret.xml": secret},
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_WORKSHEET_TOPOLOGY_INVALID")

    def test_referenced_extra_sheet_content_is_unmatched(self):
        result = XlsxPackageInspector().inspect(
            payload=build_xlsx(extra_sheet=True),
            policy=policy(),
        )
        self.assertFalse(result.matched)
        self.assertIn("XLSX_UNMODELED_WORKSHEET_CONTENT", result.diagnostics)

    def test_populated_cell_beyond_schema_width_is_unmatched(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"</row></sheetData>",
                b'<c r="D2" t="inlineStr"><is><t>hidden</t></is></c></row></sheetData>',
                1,
            ),
        )
        result = XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertFalse(result.matched)
        self.assertIn("XLSX_DATA_COLUMN_COUNT_EXCEEDED", result.diagnostics)


if __name__ == "__main__":
    unittest.main()
