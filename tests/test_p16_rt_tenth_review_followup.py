import unittest
from io import BytesIO
from zipfile import ZipFile, ZipInfo

from tests.p16_fixtures import *  # noqa: F403


_HIDDEN_COMMENT = b"hidden-commercial-text"


def _with_member_comment(payload: bytes, member_name: str) -> bytes:
    output = BytesIO()
    found = False
    with ZipFile(BytesIO(payload)) as current, ZipFile(output, "w") as rewritten:
        for info in current.infolist():
            data = current.read(info)
            copied = ZipInfo(info.filename, date_time=info.date_time)
            copied.compress_type = info.compress_type
            copied.create_system = info.create_system
            copied.external_attr = info.external_attr
            copied.internal_attr = info.internal_attr
            copied.extra = info.extra
            if info.filename == member_name:
                copied.comment = _HIDDEN_COMMENT
                found = True
            rewritten.writestr(copied, data)
    if not found:
        raise AssertionError(f"fixture member not found: {member_name}")
    return output.getvalue()


def _add_workbook_relationship(payload: bytes, relation: bytes) -> bytes:
    return rewrite_xlsx_part(
        payload,
        "xl/_rels/workbook.xml.rels",
        lambda value: value.replace(
            b"</Relationships>",
            relation + b"</Relationships>",
            1,
        ),
    )


class P16TenthReviewFollowupTests(unittest.TestCase):
    def test_direct_xlsx_member_comment_is_rejected(self):
        payload = _with_member_comment(
            build_xlsx(),
            "[Content_Types].xml",
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_ARCHIVE_POLYGLOT_FORBIDDEN",
        )

    def test_wrapped_outer_member_comment_is_rejected(self):
        payload = _with_member_comment(
            wrap_xlsx(build_xlsx()),
            "weekly-report.xlsx",
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_ARCHIVE_POLYGLOT_FORBIDDEN",
        )

    def test_wrapped_inner_member_comment_is_rejected(self):
        workbook = _with_member_comment(
            build_xlsx(),
            "xl/workbook.xml",
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

    def test_unreferenced_worksheet_relationship_is_rejected(self):
        workbook = build_xlsx(
            extra_entries={
                "xl/worksheets/hidden.xml": (
                    b'<?xml version="1.0" encoding="UTF-8"?>'
                    b'<worksheet xmlns="http://schemas.openxmlformats.org/'
                    b'spreadsheetml/2006/main"><sheetData/></worksheet>'
                ),
            }
        )
        payload = _add_workbook_relationship(
            workbook,
            b'<Relationship Id="rHidden" '
            b'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            b'relationships/worksheet" Target="worksheets/hidden.xml"/>',
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_WORKBOOK_RELATIONSHIP_UNREFERENCED",
        )

    def test_standard_styles_relationship_is_modeled(self):
        workbook = build_xlsx(
            extra_entries={
                "xl/styles.xml": (
                    b'<?xml version="1.0" encoding="UTF-8"?>'
                    b'<styleSheet xmlns="http://schemas.openxmlformats.org/'
                    b'spreadsheetml/2006/main"/>'
                ),
            }
        )
        payload = _add_workbook_relationship(
            workbook,
            b'<Relationship Id="rStyles" '
            b'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            b'relationships/styles" Target="styles.xml"/>',
        )
        result = XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertIsNotNone(result.matched_schema_id)
        self.assertEqual(result.diagnostics, ())

    def test_unknown_worksheet_structural_attribute_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<sheetData>",
                b'<sheetViews secret="hidden"><sheetView workbookViewId="0"/>'
                b"</sheetViews><sheetData>",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_WORKSHEET_ATTRIBUTE_UNMODELED",
        )

    def test_unknown_content_types_attribute_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "[Content_Types].xml",
            lambda value: value.replace(
                b'<Default Extension="xml" ContentType="application/xml"/>',
                b'<Default Extension="xml" ContentType="application/xml" '
                b'secret="hidden"/>',
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_CONTENT_TYPES_INVALID")

    def test_content_types_metadata_changes_structural_fingerprint(self):
        first = build_xlsx()
        second = rewrite_xlsx_part(
            build_xlsx(),
            "[Content_Types].xml",
            lambda value: value.replace(
                b'ContentType="application/xml"',
                b'ContentType="application/custom+xml"',
                1,
            ),
        )
        first_result = XlsxPackageInspector().inspect(
            payload=first,
            policy=policy(),
        )
        second_result = XlsxPackageInspector().inspect(
            payload=second,
            policy=policy(),
        )
        self.assertIsNotNone(first_result.matched_schema_id)
        self.assertIsNotNone(second_result.matched_schema_id)
        self.assertNotEqual(
            first_result.structural_fingerprint_sha256,
            second_result.structural_fingerprint_sha256,
        )


if __name__ == "__main__":
    unittest.main()
