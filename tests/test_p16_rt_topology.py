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


if __name__ == "__main__":
    unittest.main()
