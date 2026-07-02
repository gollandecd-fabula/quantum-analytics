import unittest

from tests.p16_fixtures import *  # noqa: F403


class P16RedTeamPackagePartTests(unittest.TestCase):
    def test_unmodeled_package_parts_are_rejected(self):
        candidates = (
            "customXml/item1.xml",
            "xl/comments1.xml",
            "docProps/custom.xml",
        )
        for part_name in candidates:
            with self.subTest(part_name=part_name):
                payload = build_xlsx(
                    extra_entries={part_name: b"<hidden>secret</hidden>"},
                )
                with self.assertRaises(XlsxInspectionError) as error:
                    XlsxPackageInspector().inspect(
                        payload=payload,
                        policy=policy(),
                    )
                self.assertEqual(
                    error.exception.code,
                    "XLSX_PACKAGE_PART_UNMODELED",
                )


if __name__ == "__main__":
    unittest.main()
