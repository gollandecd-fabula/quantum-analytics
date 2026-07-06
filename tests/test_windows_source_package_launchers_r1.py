from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILDER = (ROOT / "scripts" / "windows" / "build_local_production.ps1").read_text(encoding="utf-8")


class WindowsSourcePackageLaunchersR1Tests(unittest.TestCase):
    def test_source_start_launcher_propagates_attestations(self):
        self.assertIn(
            '-PackageRoot "%~dp0" -AuthorityAttested -SchemaReviewed',
            BUILDER,
        )

    def test_source_import_launcher_propagates_attestations(self):
        self.assertIn(
            'import_source.ps1" -AuthorityAttested -SchemaReviewed',
            BUILDER,
        )

    def test_source_readme_matches_one_click_behavior(self):
        self.assertIn(
            'No AUTHORIZE or REVIEWED console input is required',
            BUILDER,
        )
        self.assertNotIn('Type AUTHORIZE only', BUILDER)
        self.assertNotIn('Type REVIEWED only', BUILDER)
        self.assertIn('Microsoft Defender scanning remains enabled', BUILDER)
        self.assertIn('Marketplace writes', BUILDER)


if __name__ == "__main__":
    unittest.main()
