from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ONE_CLICK = ROOT / "scripts" / "windows" / "one_click_home_local.ps1"
INSTALLER = ROOT / "scripts" / "windows" / "install_home_local.ps1"


class WindowsFirstRunFinanceCenterR74Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = ONE_CLICK.read_text(encoding="ascii")
        cls.installer = INSTALLER.read_text(encoding="ascii")

    def test_first_interactive_run_opens_finance_center_before_import(self) -> None:
        script = self.script
        install = script.index('& $installer -SourceRoot $PackageRoot -TargetRoot $TargetRoot')
        configure = script.index('$Config = Invoke-ConfigurationWizard')
        desktop = script.index('"quantum.application.desktop_center"')
        import_run = script.index('& $importer @importArguments')
        self.assertLess(install, configure)
        self.assertLess(configure, desktop)
        self.assertLess(desktop, import_run)
        self.assertIn(
            'if (-not $NonInteractive -and [string]::IsNullOrWhiteSpace($File)) {',
            script,
        )
        self.assertNotIn(
            'if ($SkipInstall -and -not $NonInteractive -and [string]::IsNullOrWhiteSpace($File)) {',
            script,
        )

    def test_installed_script_self_recovers_if_launcher_loses_skip_install(self) -> None:
        script = self.script
        recovery = script.index('$installedCandidate =')
        branch = script.index('if ($SkipInstall) {', recovery)
        recovery_block = script[recovery:branch]
        self.assertLess(recovery, branch)
        self.assertIn('$installedMarkers = @(', recovery_block)
        self.assertIn('$hasInstalledMarker = $false', recovery_block)
        self.assertIn('$SkipInstall = $true', recovery_block)
        self.assertIn('install_home_local.ps1', recovery_block)
        for marker in (
            'START_QUANTUM.cmd',
            'scripts\\import_source.ps1',
            'scripts\\configure_home_local.ps1',
            'src\\quantum\\pilot\\windows_runner.py',
        ):
            self.assertIn(marker, recovery_block)
        self.assertIn(
            '$hasInstalledMarker -and -not (Test-Path -LiteralPath $packageInstaller',
            recovery_block,
        )

    def test_installed_launcher_always_uses_skip_install(self) -> None:
        installer = self.installer
        self.assertIn(
            'one_click_home_local.ps1" -InstalledRoot "%~dp0" -SkipInstall',
            installer,
        )
        self.assertNotIn(
            'one_click_home_local.ps1" -InstalledRoot "%~dp0"\n',
            installer,
        )

    def test_explicit_file_and_noninteractive_import_paths_remain_available(self) -> None:
        script = self.script
        self.assertIn('if (-not [string]::IsNullOrWhiteSpace($File)) {', script)
        self.assertIn('if ($File) { $importArguments["File"] = $File }', script)
        self.assertIn('if ($NonInteractive)', script)
        self.assertIn('-not $AuthorityAttested -or -not $SchemaReviewed', script)
        self.assertIn('& $importer @importArguments', script)

    def test_install_only_returns_before_desktop_launch(self) -> None:
        script = self.script
        install_only = script.index('if ($InstallOnly) {')
        desktop = script.index('"quantum.application.desktop_center"')
        self.assertLess(install_only, desktop)

    def test_windows_entry_scripts_remain_ascii_safe(self) -> None:
        self.assertTrue(self.script.isascii())
        self.assertTrue(self.installer.isascii())


if __name__ == "__main__":
    unittest.main()
