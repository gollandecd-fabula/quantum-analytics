from __future__ import annotations

import base64
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILDER = (ROOT / "scripts" / "windows" / "build_local_production.ps1").read_text(encoding="utf-8")
README = "\n".join(
    base64.b64decode(value, validate=True).decode("utf-8")
    for value in re.findall(r'FromBase64String\("([A-Za-z0-9+/=]{16,})"\)', BUILDER)
)


class WindowsSourcePackageLaunchersR1Tests(unittest.TestCase):
    def test_source_start_launcher_never_attests_for_operator(self):
        self.assertIn('-PackageRoot "%~dp0"', BUILDER)
        self.assertNotIn(
            '-PackageRoot "%~dp0" -AuthorityAttested -SchemaReviewed',
            BUILDER,
        )

    def test_source_import_launcher_never_attests_for_operator(self):
        self.assertNotIn(
            'import_source.ps1" -AuthorityAttested -SchemaReviewed',
            BUILDER,
        )

    def test_source_readme_matches_fail_closed_one_click_behavior(self):
        self.assertNotIn(
            'No AUTHORIZE or REVIEWED console input is required',
            BUILDER,
        )
        self.assertIn('Введите AUTHORIZE', README)
        self.assertIn('введите REVIEWED', README)
        self.assertIn('Программы запуска никогда не подтверждают AUTHORIZE или REVIEWED за пользователя', README)
        self.assertIn('Microsoft Defender остаётся включённым', README)
        self.assertIn('Запись на маркетплейс', README)


if __name__ == "__main__":
    unittest.main()
