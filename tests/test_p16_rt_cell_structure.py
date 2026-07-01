import unittest

from tests.p16_fixtures import *  # noqa: F403


class P16RedTeamCellStructureTests(unittest.TestCase):
    def _assert_structure_rejected(self, payload: bytes) -> None:
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertEqual(
            error.exception.code,
            "XLSX_CELL_STRUCTURE_INVALID",
        )

    def test_duplicate_inline_string_nodes_are_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<is><t>operation_id</t></is></c>",
                b"<is><t>operation_id</t></is>"
                b"<is><t>customer phone</t></is></c>",
                1,
            ),
        )
        self._assert_structure_rejected(payload)

    def test_duplicate_value_nodes_are_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b'<c r="A2" t="inlineStr"><is><t>1</t></is></c>',
                b'<c r="A2"><v>1</v><v>2</v></c>',
                1,
            ),
        )
        self._assert_structure_rejected(payload)

    def test_duplicate_formula_nodes_are_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(formula=True),
            "xl/worksheets/sheet1.xml",
            lambda value: value.replace(
                b"<f>1+1</f>",
                b"<f>1+1</f><f>2+2</f>",
                1,
            ),
        )
        self._assert_structure_rejected(payload)


if __name__ == "__main__":
    unittest.main()
