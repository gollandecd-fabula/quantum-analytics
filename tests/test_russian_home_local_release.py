from __future__ import annotations

import base64
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_POWERSHELL = (
    ROOT / "scripts/windows/one_click_home_local.ps1",
    ROOT / "scripts/windows/configure_home_local.ps1",
    ROOT / "scripts/windows/import_source.ps1",
    ROOT / "scripts/windows/install_home_local.ps1",
    ROOT / "src/quantum/pilot/import_xlsx_source.ps1",
)
ASCII_SAFE_BUILDERS = (
    ROOT / "scripts/windows/build_local_production.ps1",
    ROOT / "scripts/windows/build_two_installer_bundles.ps1",
    ROOT / "scripts/windows/build_exe_installer.ps1",
)
USER_SURFACES = (
    ROOT / "src/quantum/application/local_app.py",
    ROOT / "src/quantum/outputs/dashboard.py",
    ROOT / "src/quantum/outputs/dashboard_shell.py",
    ROOT / "src/quantum/outputs/dashboard_script_core.py",
    ROOT / "src/quantum/outputs/dashboard_script_data.py",
    ROOT / "src/quantum/outputs/dashboard_script_controls.py",
    ROOT / "docs/pilot/WINDOWS_HOME_LOCAL_PACKAGE.md",
)


_BASE64_RE = re.compile(r'-Encoded\s+["\']([A-Za-z0-9+/=]{16,})["\']')


def _decoded_runtime_messages(text: str) -> list[str]:
    messages: list[str] = []
    for encoded in _BASE64_RE.findall(text):
        messages.append(base64.b64decode(encoded, validate=True).decode("utf-8"))
    return messages


class RussianHomeLocalReleaseTests(unittest.TestCase):
    def test_windows_entry_scripts_remain_ascii_safe_for_powershell_51(self) -> None:
        for path in (*RUNTIME_POWERSHELL, *ASCII_SAFE_BUILDERS):
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                path.read_bytes().decode("ascii")

    def test_runtime_messages_are_utf8_decodable_and_russian(self) -> None:
        for path in RUNTIME_POWERSHELL:
            text = path.read_text(encoding="ascii")
            messages = _decoded_runtime_messages(text)
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertIn("function Get-QuantumRussianText", text)
                self.assertGreater(len(messages), 5)
                self.assertTrue(
                    all(any("А" <= char <= "я" or char in "Ёё" for char in message) for message in messages),
                    "Каждое пользовательское сообщение должно содержать русский текст",
                )

    def test_primary_user_surfaces_are_russian(self) -> None:
        combined = "\n".join(path.read_text(encoding="utf-8") for path in USER_SURFACES)
        for required in (
            "Центр решений Quantum",
            "ТОЛЬКО ЧТЕНИЕ",
            "Запись на маркетплейс: отключена",
            "Добавить отчёты",
            "установка или восстановление",
        ):
            with self.subTest(required=required):
                self.assertIn(required, combined)

    def test_old_english_user_facing_phrases_do_not_return(self) -> None:
        combined = "\n".join(path.read_text(encoding="utf-8") for path in USER_SURFACES)
        for forbidden in (
            "Marketplace writes: disabled",
            "READ ONLY",
            "Decision Center",
            "CSV protected from spreadsheet-formula injection",
            "Quantum HOME_LOCAL WINDOWS PACKAGE - ONE-CLICK LOCAL PILOT",
            "PRIMARY ACTION",
            "RECOVERY TOOLS",
            "DEFAULT INSTALLATION",
            "import_source.ps1 not found under",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)

    def test_security_tokens_remain_exact_and_are_not_auto_confirmed(self) -> None:
        combined = "\n".join(path.read_text(encoding="ascii") for path in RUNTIME_POWERSHELL)
        self.assertIn("AUTHORIZE", combined)
        self.assertIn("REVIEWED", combined)
        self.assertIn("AuthorityAttested", combined)
        self.assertIn("SchemaReviewed", combined)
        self.assertNotIn('$AuthorityAttested = $true', combined)
        self.assertNotIn('$SchemaReviewed = $true', combined)

    def test_release_boundary_remains_wb_only_and_read_only(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (
                ROOT / "src/quantum/outputs/dashboard_script_core.py",
                ROOT / "scripts/windows/configure_home_local.ps1",
                ROOT / "scripts/windows/build_local_production.ps1",
            )
        )
        self.assertIn("WB_ONLY", combined)
        self.assertIn("WILDBERRIES", combined)
        self.assertIn("OZON", combined)
        self.assertIn("marketplace_write_enabled", combined)
        self.assertNotIn("marketplace_write_enabled = $true", combined)


if __name__ == "__main__":
    unittest.main()
