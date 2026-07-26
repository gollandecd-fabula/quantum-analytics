from __future__ import annotations

from pathlib import Path
import base64
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ROOT / "scripts" / "windows"


def _decoded_user_text(script: str) -> str:
    values: list[str] = []
    for token in re.findall(r'"([A-Za-z0-9+/]{16,}={0,2})"', script):
        try:
            decoded = base64.b64decode(token, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        values.append(decoded)
    return "\n".join(values)


class ShortcutLaunchRepairR1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.one_click = (WINDOWS / "one_click_home_local.ps1").read_text(
            encoding="utf-8"
        )
        cls.installer = (WINDOWS / "install_home_local.ps1").read_text(
            encoding="utf-8"
        )
        cls.builder = (WINDOWS / "build_local_production.ps1").read_text(
            encoding="utf-8"
        )
        cls.one_click_ru = _decoded_user_text(cls.one_click)

    def test_direct_installed_script_never_requires_package_installer(self) -> None:
        self.assertIn("function Test-InstallationPackageLayout", self.one_click)
        self.assertIn("function Assert-InstalledRuntimeLayout", self.one_click)
        self.assertIn("$PackageRoot = $selfRoot", self.one_click)
        self.assertIn("$InstalledRoot = $selfRoot", self.one_click)
        package_branch = self.one_click.index(
            "if (Test-InstallationPackageLayout -Root $selfRoot)"
        )
        installed_branch = self.one_click.index(
            "$missingInstalledComponents = @("
        )
        self.assertLess(package_branch, installed_branch)

    def test_incomplete_install_has_explicit_repair_diagnostic(self) -> None:
        self.assertIn("HOME_LOCAL_INSTALLATION_INCOMPLETE:", self.one_click)
        self.assertIn(
            "Установка Quantum повреждена или не завершена.",
            self.one_click_ru,
        )
        for required in (
            "START_QUANTUM.cmd",
            "scripts\\one_click_home_local.ps1",
            "scripts\\import_source.ps1",
            "scripts\\configure_home_local.ps1",
            "src\\quantum\\pilot\\windows_runner.py",
            "src\\quantum\\application\\desktop_center.py",
        ):
            self.assertIn(required, self.one_click)

    def test_start_command_uses_canonical_root_and_forwards_arguments(self) -> None:
        self.assertIn(
            'for %%I in ("%~dp0.") do set "QUANTUM_ROOT=%%~fI"',
            self.installer,
        )
        self.assertIn(
            '-InstalledRoot "%QUANTUM_ROOT%" -SkipInstall %*',
            self.installer,
        )
        self.assertNotIn('-InstalledRoot "%~dp0" -SkipInstall', self.installer)

    def test_shortcut_target_is_verified_and_stale_common_link_removed(self) -> None:
        for token in (
            "[Environment+SpecialFolder]::DesktopDirectory",
            "[Environment+SpecialFolder]::CommonDesktopDirectory",
            "$verified.TargetPath",
            "$verified.WorkingDirectory",
            "SHORTCUT_VERIFICATION_FAILED",
            "STALE_COMMON_DESKTOP_SHORTCUT_NOT_REMOVED",
        ):
            self.assertIn(token, self.installer)
        self.assertIn("New-QuantumShortcut -Launcher $startCommandTarget", self.installer)

    def test_package_still_contains_installer_and_runtime_launcher(self) -> None:
        self.assertIn(
            'scripts\\windows\\install_home_local.ps1',
            self.builder,
        )
        self.assertIn(
            'scripts\\windows\\one_click_home_local.ps1',
            self.builder,
        )

    def test_entry_scripts_remain_ascii_for_windows_powershell_51(self) -> None:
        for name, script in (
            ("one_click_home_local.ps1", self.one_click),
            ("install_home_local.ps1", self.installer),
        ):
            self.assertFalse(any(ord(character) > 127 for character in script), name)


if __name__ == "__main__":
    unittest.main()
