from io import BytesIO
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from tests.p16_fixtures import *  # noqa: F403


_SPREADSHEET_NS = (
    b"http://schemas.openxmlformats.org/spreadsheetml/2006/main"
)
_MC_NS = b"http://schemas.openxmlformats.org/markup-compatibility/2006"
_X14AC_NS = b"http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"
_X15_NS = b"http://schemas.microsoft.com/office/spreadsheetml/2010/11/main"
_EXTRA_FIELD = b"\xca\xfe\x04\x00hide"


def _with_zip_extra_field(payload: bytes, target: str) -> bytes:
    output = BytesIO()
    with ZipFile(BytesIO(payload)) as current, ZipFile(
        output,
        "w",
        compression=ZIP_DEFLATED,
    ) as rewritten:
        for info in current.infolist():
            data = current.read(info)
            if info.filename == target:
                info.extra = _EXTRA_FIELD
            rewritten.writestr(info, data)
    return output.getvalue()


def _worksheet_root(payload: bytes, replacement: bytes) -> bytes:
    return rewrite_xlsx_part(
        payload,
        "xl/worksheets/sheet1.xml",
        lambda value: value.replace(
            b'<worksheet xmlns="' + _SPREADSHEET_NS + b'">',
            replacement,
            1,
        ),
    )


class P16FifteenthReviewFollowupTests(unittest.TestCase):
    def test_direct_xlsx_rejects_zip_extra_fields(self):
        payload = _with_zip_extra_field(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_ARCHIVE_POLYGLOT_FORBIDDEN",
        )

    def test_wrapped_xlsx_rejects_inner_zip_extra_fields(self):
        workbook = _with_zip_extra_field(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(
                payload=wrap_xlsx(workbook),
                policy=policy(),
            )
        self.assertEqual(
            error.exception.code,
            "XLSX_ARCHIVE_POLYGLOT_FORBIDDEN",
        )

    def test_wrapped_xlsx_rejects_outer_zip_extra_fields(self):
        payload = _with_zip_extra_field(
            wrap_xlsx(build_xlsx()),
            "weekly-report.xlsx",
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_ARCHIVE_POLYGLOT_FORBIDDEN",
        )

    def test_unused_x15_worksheet_namespace_is_rejected(self):
        payload = _worksheet_root(
            build_xlsx(),
            b'<worksheet xmlns="' + _SPREADSHEET_NS
            + b'" xmlns:x15="' + _X15_NS + b'">',
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_XML_NAMESPACE_UNMODELED",
        )

    def test_worksheet_namespace_declared_below_root_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<sheetData>",
                b'<sheetData xmlns:x14ac="' + _X14AC_NS + b'">',
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_XML_NAMESPACE_UNMODELED",
        )

    def test_duplicate_ignorable_tokens_are_rejected(self):
        payload = _worksheet_root(
            build_xlsx(),
            b'<worksheet xmlns="' + _SPREADSHEET_NS
            + b'" xmlns:mc="' + _MC_NS
            + b'" xmlns:x14ac="' + _X14AC_NS
            + b'" mc:Ignorable="x14ac x14ac">',
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_WORKSHEET_ATTRIBUTE_VALUE_INVALID",
        )

    def test_duplicate_rich_text_properties_are_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<is><t>1</t></is>",
                b'<is><r><rPr><b val="1"/><b val="1"/></rPr>'
                b"<t>1</t></r></is>",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_RICH_TEXT_PROPERTIES_UNMODELED",
        )

    def test_rich_text_property_order_is_deterministic(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<is><t>1</t></is>",
                b'<is><r><rPr><i val="1"/><b val="1"/></rPr>'
                b"<t>1</t></r></is>",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_RICH_TEXT_PROPERTIES_UNMODELED",
        )

    def test_exact_x14ac_and_rich_property_contract_remains_allowed(self):
        payload = _worksheet_root(
            build_xlsx(),
            b'<worksheet xmlns="' + _SPREADSHEET_NS
            + b'" xmlns:mc="' + _MC_NS
            + b'" xmlns:x14ac="' + _X14AC_NS
            + b'" mc:Ignorable="x14ac">',
        )
        payload = rewrite_xlsx_part(
            payload,
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<is><t>1</t></is>",
                b'<is><r><rPr><b val="1"/><i val="1"/></rPr>'
                b"<t>1</t></r></is>",
                1,
            ),
        )
        result = XlsxPackageInspector().inspect(
            payload=payload,
            policy=policy(),
        )
        self.assertIsNotNone(result.matched_schema_id)
        self.assertEqual(result.diagnostics, ())


if __name__ == "__main__":
    unittest.main()
