import unittest

from tests.p16_fixtures import *  # noqa: F403


class P16R13RelationshipWhitespaceTests(unittest.TestCase):
    def test_whitespace_obfuscated_target_mode_is_rejected(self):
        payload = rewrite_xlsx_part(
            build_xlsx(),
            "_rels/.rels",
            lambda value: value.replace(
                b'Target="xl/workbook.xml"',
                b'Target="xl/workbook.xml" TargetMode=" External "',
                1,
            ),
        )
        with self.assertRaises(XlsxInspectionError) as error:
            XlsxPackageInspector().inspect(payload=payload, policy=policy())
        self.assertIn(
            error.exception.code,
            {
                "XLSX_ROOT_RELATIONSHIP_INVALID",
                "XLSX_EXTERNAL_RELATIONSHIP_FORBIDDEN",
            },
        )


if __name__ == "__main__":
    unittest.main()
