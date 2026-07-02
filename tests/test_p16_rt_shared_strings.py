import unittest

from tests.p16_fixtures import *  # noqa: F403


class P16RedTeamSharedStringTests(unittest.TestCase):
    def _shared_payload(self, values):
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + "".join(f"<si><t>{value}</t></si>" for value in values)
            + "</sst>"
        ).encode("utf-8")

    def test_negative_shared_string_index_is_rejected(self):
        values = (
            "operation_id",
            "operation_type",
            "amount",
            "1",
            "SALE",
            "100.00",
        )
        replacements = (
            ("A1", "operation_id", -6),
            ("B1", "operation_type", -5),
            ("C1", "amount", -4),
            ("A2", "1", -3),
            ("B2", "SALE", -2),
            ("C2", "100.00", -1),
        )

        def use_negative_shared_indexes(payload: bytes) -> bytes:
            text = payload.decode("utf-8")
            for reference, value, index in replacements:
                text = text.replace(
                    f'<c r="{reference}" t="inlineStr"><is><t>{value}</t></is></c>',
                    f'<c r="{reference}" t="s"><v>{index}</v></c>',
                )
            return text.encode("utf-8")

        payload = rewrite_xlsx_part(
            build_xlsx(
                extra_entries={"xl/sharedStrings.xml": self._shared_payload(values)},
            ),
            "xl/worksheets/sheet1.xml",
            use_negative_shared_indexes,
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_SHARED_STRING_REFERENCE_INVALID",
        )

    def test_unreferenced_shared_string_is_rejected(self):
        payload = build_xlsx(
            extra_entries={
                "xl/sharedStrings.xml": self._shared_payload(("hidden-text",)),
            }
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(error.exception.code, "XLSX_SHARED_STRING_UNUSED")

    def test_fully_referenced_shared_string_table_is_allowed(self):
        values = (
            "operation_id",
            "operation_type",
            "amount",
            "1",
            "SALE",
            "100.00",
        )
        replacements = tuple(
            zip(
                ("A1", "B1", "C1", "A2", "B2", "C2"),
                values,
                range(len(values)),
            )
        )

        def use_shared_indexes(payload: bytes) -> bytes:
            text = payload.decode("utf-8")
            for reference, value, index in replacements:
                text = text.replace(
                    f'<c r="{reference}" t="inlineStr"><is><t>{value}</t></is></c>',
                    f'<c r="{reference}" t="s"><v>{index}</v></c>',
                )
            return text.encode("utf-8")

        payload = rewrite_xlsx_part(
            build_xlsx(
                extra_entries={"xl/sharedStrings.xml": self._shared_payload(values)},
            ),
            "xl/worksheets/sheet1.xml",
            use_shared_indexes,
        )
        result = XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertIsNotNone(result.matched_schema_id)
        self.assertEqual(result.diagnostics, ())


if __name__ == "__main__":
    unittest.main()
