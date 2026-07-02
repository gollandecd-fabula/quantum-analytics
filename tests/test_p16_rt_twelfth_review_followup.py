import unittest

from tests.p16_fixtures import *  # noqa: F403


_RELATIONSHIP_NS = (
    b"http://schemas.openxmlformats.org/package/2006/relationships"
)
_SPREADSHEET_NS = (
    b"http://schemas.openxmlformats.org/spreadsheetml/2006/main"
)
_MC_NS = b"http://schemas.openxmlformats.org/markup-compatibility/2006"
_X14AC_NS = b"http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac"


class P16TwelfthReviewFollowupTests(unittest.TestCase):
    def test_unapproved_namespace_uri_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "_rels/.rels",
            lambda value: value.replace(
                b'<Relationships xmlns="' + _RELATIONSHIP_NS + b'">',
                b'<Relationships xmlns="' + _RELATIONSHIP_NS
                + b'" xmlns:secret="customer@example.com">',
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_XML_NAMESPACE_UNMODELED")

    def test_unapproved_prefix_with_trusted_uri_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "_rels/.rels",
            lambda value: value.replace(
                b'<Relationships xmlns="' + _RELATIONSHIP_NS + b'">',
                b'<Relationships xmlns="' + _RELATIONSHIP_NS
                + b'" xmlns:customer_email="' + _RELATIONSHIP_NS + b'">',
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_XML_NAMESPACE_UNMODELED")

    def test_standard_worksheet_compatibility_namespaces_are_allowed(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b'<worksheet xmlns="' + _SPREADSHEET_NS + b'">',
                b'<worksheet xmlns="' + _SPREADSHEET_NS
                + b'" xmlns:mc="' + _MC_NS
                + b'" xmlns:x14ac="' + _X14AC_NS
                + b'" mc:Ignorable="x14ac">',
                1,
            ),
        )
        result = XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertIsNotNone(result.matched_schema_id)
        self.assertEqual(result.diagnostics, ())

    def test_standard_core_property_namespaces_are_allowed(self):
        core = (
            b'<cp:coreProperties '
            b'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            b'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            b'xmlns:dcterms="http://purl.org/dc/terms/" '
            b'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
            b'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>'
        )
        payload = build_xlsx(extra_entries={"docProps/core.xml": core})
        result = XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertIsNotNone(result.matched_schema_id)
        self.assertEqual(result.diagnostics, ())


if __name__ == "__main__":
    unittest.main()
