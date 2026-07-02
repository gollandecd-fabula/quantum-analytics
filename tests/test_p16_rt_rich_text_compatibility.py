import unittest

from tests.p16_fixtures import *  # noqa: F403


def _rich_shared_payload(values: tuple[str, ...]) -> bytes:
    entries = "".join(
        "<si><r><rPr><i val=\"1\"/></rPr>"
        f"<t>{value}</t></r></si>"
        for value in values
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + entries
        + "</sst>"
    ).encode("utf-8")


def _use_shared_indexes(payload: bytes, values: tuple[str, ...]) -> bytes:
    text = payload.decode("utf-8")
    for reference, value, index in zip(
        ("A1", "B1", "C1", "A2", "B2", "C2"),
        values,
        range(len(values)),
    ):
        text = text.replace(
            f'<c r="{reference}" t="inlineStr"><is><t>{value}</t></is></c>',
            f'<c r="{reference}" t="s"><v>{index}</v></c>',
        )
    return text.encode("utf-8")


class P16RichTextCompatibilityTests(unittest.TestCase):
    def test_rich_inline_string_is_modeled(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<is><t>1</t></is>",
                b'<is><r><rPr><b val="1"/></rPr>'
                b'<t xml:space="preserve">1</t></r></is>',
                1,
            ),
        )
        result = XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertIsNotNone(result.matched_schema_id)
        self.assertEqual(result.diagnostics, ())

    def test_fully_referenced_rich_shared_strings_are_modeled(self):
        values = (
            "operation_id",
            "operation_type",
            "amount",
            "1",
            "SALE",
            "100.00",
        )
        payload = rewrite_xlsx_part(
            build_xlsx(
                extra_entries={
                    "xl/sharedStrings.xml": _rich_shared_payload(values),
                }
            ),
            "xl/worksheets/sheet1.xml",
            lambda value: _use_shared_indexes(value, values),
        )
        result = XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertIsNotNone(result.matched_schema_id)
        self.assertEqual(result.diagnostics, ())

    def test_standard_formula_attributes_are_modeled(self):
        payload = rewrite_xlsx_part(
            build_xlsx(formula=True),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<f>1+1</f>",
                b'<f ca="1">1+1</f>',
                1,
            ),
        )
        result = XlsxPackageInspector().inspect(
            payload=payload,
            policy=policy(formulas=1),
        )
        self.assertIsNotNone(result.matched_schema_id)
        self.assertEqual(result.formula_count, 1)
        self.assertEqual(result.diagnostics, ())


if __name__ == "__main__":
    unittest.main()
