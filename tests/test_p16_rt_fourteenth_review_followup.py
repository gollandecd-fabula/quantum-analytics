import unittest

from tests.p16_fixtures import *  # noqa: F403


_AUXILIARY_FAILURES = {
    "XLSX_AUXILIARY_CONTENT_UNMODELED",
    "XLSX_XML_NAMESPACE_UNMODELED",
}


def _add_workbook_relationship(payload: bytes, relation: bytes) -> bytes:
    return rewrite_xlsx_part(
        payload,
        "xl/_rels/workbook.xml.rels",
        lambda value: value.replace(
            b"</Relationships>", relation + b"</Relationships>", 1
        ),
    )


def _add_root_relationship(payload: bytes, relation: bytes) -> bytes:
    return rewrite_xlsx_part(
        payload,
        "_rels/.rels",
        lambda value: value.replace(
            b"</Relationships>", relation + b"</Relationships>", 1
        ),
    )


class P16FourteenthReviewFollowupTests(unittest.TestCase):
    def test_styles_attribute_hidden_channel_is_rejected(self) -> None:
        payload = build_xlsx(
            extra_entries={
                "xl/styles.xml": (
                    b'<?xml version="1.0" encoding="UTF-8"?>'
                    b'<styleSheet xmlns="http://schemas.openxmlformats.org/'
                    b'spreadsheetml/2006/main" '
                    b'secret="customer_email_alice@example.com"/>'
                )
            }
        )
        payload = _add_workbook_relationship(
            payload,
            b'<Relationship Id="rStyles" '
            b'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            b'relationships/styles" Target="styles.xml"/>',
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertIn(error.exception.code, _AUXILIARY_FAILURES)

    def test_core_properties_text_hidden_channel_is_rejected(self) -> None:
        payload = build_xlsx(
            extra_entries={
                "docProps/core.xml": (
                    b'<?xml version="1.0" encoding="UTF-8"?>'
                    b'<coreProperties xmlns="http://schemas.openxmlformats.org/'
                    b'package/2006/metadata/core-properties">'
                    b'customer_email_alice@example.com</coreProperties>'
                )
            }
        )
        payload = _add_root_relationship(
            payload,
            b'<Relationship Id="rCore" '
            b'Type="http://schemas.openxmlformats.org/package/2006/'
            b'relationships/metadata/core-properties" '
            b'Target="docProps/core.xml"/>',
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertIn(error.exception.code, _AUXILIARY_FAILURES)

    def test_extended_properties_child_hidden_channel_is_rejected(self) -> None:
        payload = build_xlsx(
            extra_entries={
                "docProps/app.xml": (
                    b'<?xml version="1.0" encoding="UTF-8"?>'
                    b'<Properties xmlns="http://schemas.openxmlformats.org/'
                    b'officeDocument/2006/extended-properties">'
                    b'<Company>customer_email_alice@example.com</Company>'
                    b'</Properties>'
                )
            }
        )
        payload = _add_root_relationship(
            payload,
            b'<Relationship Id="rApp" '
            b'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            b'relationships/extended-properties" '
            b'Target="docProps/app.xml"/>',
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertIn(error.exception.code, _AUXILIARY_FAILURES)

    def test_theme_attribute_hidden_channel_is_rejected(self) -> None:
        payload = build_xlsx(
            extra_entries={
                "xl/theme/theme1.xml": (
                    b'<?xml version="1.0" encoding="UTF-8"?>'
                    b'<theme xmlns="http://schemas.openxmlformats.org/'
                    b'drawingml/2006/main" '
                    b'name="customer_email_alice@example.com"/>'
                )
            }
        )
        payload = _add_workbook_relationship(
            payload,
            b'<Relationship Id="rTheme" '
            b'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            b'relationships/theme" Target="theme/theme1.xml"/>',
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertIn(error.exception.code, _AUXILIARY_FAILURES)

    def test_empty_modeled_styles_root_remains_allowed(self) -> None:
        payload = build_xlsx(
            extra_entries={
                "xl/styles.xml": (
                    b'<?xml version="1.0" encoding="UTF-8"?>'
                    b'<styleSheet xmlns="http://schemas.openxmlformats.org/'
                    b'spreadsheetml/2006/main"/>'
                )
            }
        )
        payload = _add_workbook_relationship(
            payload,
            b'<Relationship Id="rStyles" '
            b'Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            b'relationships/styles" Target="styles.xml"/>',
        )
        result = XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertIsNotNone(result.matched_schema_id)
        self.assertEqual(result.diagnostics, ())

    def test_sheet_code_name_hidden_channel_is_rejected(self) -> None:
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<sheetData>",
                b'<sheetPr codeName="customer_email_alice@example.com"/>'
                b"<sheetData>",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_WORKSHEET_ATTRIBUTE_UNMODELED",
        )

    def test_page_margin_value_hidden_channel_is_rejected(self) -> None:
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<sheetData>",
                b'<pageMargins left="0.7" right="0.7" top="0.75" '
                b'bottom="0.75" header="customer_email_alice@example.com" '
                b'footer="0.3"/><sheetData>',
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_WORKSHEET_ATTRIBUTE_VALUE_INVALID",
        )

    def test_sheet_protection_hash_hidden_channel_is_rejected(self) -> None:
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<sheetData>",
                b'<sheetProtection sheet="1" '
                b'hashValue="customer_email_alice@example.com"/>'
                b"<sheetData>",
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_WORKSHEET_ATTRIBUTE_UNMODELED",
        )

    def test_row_attribute_value_hidden_channel_is_rejected(self) -> None:
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b'<row r="1">',
                b'<row r="1" spans="customer_email_alice@example.com">',
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_ROW_ATTRIBUTE_UNMODELED")

    def test_cell_type_value_hidden_channel_is_rejected(self) -> None:
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b't="inlineStr"',
                b't="customer_email_alice@example.com"',
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_CELL_ATTRIBUTE_UNMODELED")

    def test_standard_structural_attribute_values_remain_allowed(self) -> None:
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<sheetData>",
                b'<sheetViews><sheetView workbookViewId="0" '
                b'view="normal"><selection activeCell="A1" '
                b'sqref="A1:C3"/></sheetView></sheetViews>'
                b'<pageMargins left="0.7" right="0.7" top="0.75" '
                b'bottom="0.75" header="0.3" footer="0.3"/>'
                b"<sheetData>",
                1,
            ),
        )
        result = XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertIsNotNone(result.matched_schema_id)
        self.assertEqual(result.diagnostics, ())


if __name__ == "__main__":
    unittest.main()
