import unittest
from dataclasses import replace

from tests.p16_fixtures import *  # noqa: F403


class P16SeventhReviewFollowupTests(unittest.TestCase):
    def test_wrapped_workbook_auxiliary_xml_respects_inner_limits(self):
        base_policy = policy()
        limited_policy = replace(
            base_policy,
            limits=replace(base_policy.limits, max_xml_bytes=1024),
        )
        workbook = build_xlsx(
            extra_entries={
                "docProps/core.xml": b"<core>" + (b"x" * 4096) + b"</core>",
            }
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(
                payload=wrap_xlsx(workbook),
                policy=limited_policy,
            )
        self.assertEqual(error.exception.code, "XLSX_XML_SIZE_EXCEEDED")

    def test_inner_archive_limits_precede_relationship_parsing(self):
        base_policy = policy()
        limited_policy = replace(
            base_policy,
            limits=replace(base_policy.limits, max_entries=4),
        )
        workbook = rewrite_xlsx_part(
            build_xlsx(),
            "_rels/.rels",
            lambda value: value.replace(
                b'Target="xl/workbook.xml"',
                b'Target="https://example.invalid/workbook.xml"',
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(
                payload=wrap_xlsx(workbook),
                policy=limited_policy,
            )
        self.assertEqual(error.exception.code, "XLSX_ENTRY_LIMIT_EXCEEDED")

    def test_blank_root_relationship_id_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "_rels/.rels",
            lambda value: value.replace(b'Id="rId1"', b'Id="   "', 1),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ROOT_RELATIONSHIP_INVALID")

    def test_row_outside_sheet_data_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"</sheetData>",
                b'</sheetData><row r="3"><c r="A3" t="inlineStr">'
                b"<is><t>hidden</t></is></c></row>",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ROW_OUTSIDE_SHEET_DATA")


if __name__ == "__main__":
    unittest.main()
