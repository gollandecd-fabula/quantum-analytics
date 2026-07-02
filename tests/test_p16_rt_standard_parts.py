import unittest

from tests.p16_fixtures import *  # noqa: F403


class P16StandardPartCompatibilityTests(unittest.TestCase):
    def test_standard_non_executable_parts_are_admitted(self):
        payload = build_xlsx(
            extra_entries={
                "docProps/core.xml": b"<coreProperties/>",
                "docProps/app.xml": b"<Properties/>",
                "xl/styles.xml": b"<styleSheet/>",
                "xl/theme/theme1.xml": b"<theme/>",
            },
        )
        inspection = XlsxPackageInspector().inspect(
            payload=payload,
            policy=policy(),
        )
        self.assertTrue(inspection.matched)

    def test_standard_root_property_relationships_are_admitted(self):
        payload = build_xlsx(
            extra_entries={
                "docProps/core.xml": b"<coreProperties/>",
                "docProps/app.xml": b"<Properties/>",
            },
        )
        relationships = (
            b'<Relationship Id="rCore" '
            b'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
            b'Target="docProps/core.xml"/>'
            b'<Relationship Id="rApp" '
            b'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
            b'Target="docProps/app.xml"/>'
        )
        payload = rewrite_xlsx_part(
            payload,
            "_rels/.rels",
            lambda value: value.replace(
                b"</Relationships>",
                relationships + b"</Relationships>",
                1,
            ),
        )
        inspection = XlsxPackageInspector().inspect(
            payload=payload,
            policy=policy(),
        )
        self.assertTrue(inspection.matched)


if __name__ == "__main__":
    unittest.main()
