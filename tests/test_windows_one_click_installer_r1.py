from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ROOT / "scripts" / "windows"


class WindowsOneClickInstallerR1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.one_click = (WINDOWS / "one_click_home_local.ps1").read_text(encoding="utf-8")
        cls.importer = (WINDOWS / "import_source.ps1").read_text(encoding="utf-8")
        cls.installer = (WINDOWS / "install_home_local.ps1").read_text(encoding="utf-8")
        cls.builder = (WINDOWS / "build_local_production.ps1").read_text(encoding="utf-8")

    def test_package_exposes_one_primary_start_command(self):
        self.assertIn('START_QUANTUM.cmd', self.builder)
        self.assertIn('scripts\\one_click_home_local.ps1', self.builder)
        self.assertIn('-PackageRoot "%~dp0"', self.builder)
        self.assertIn('Double-click START_QUANTUM.cmd', self.builder)
        self.assertIn('package_version = "R3_ONE_CLICK"', self.builder)

    def test_one_click_sequence_installs_configures_and_imports(self):
        script = self.one_click
        install = script.index('& $installer -SourceRoot $PackageRoot -TargetRoot $TargetRoot')
        configure = script.index('$Config = Invoke-ConfigurationWizard')
        import_run = script.index('& $importer @importArguments')
        self.assertLess(install, configure)
        self.assertLess(configure, import_run)
        self.assertIn('Find-ReadyConfig', script)
        self.assertIn('ADMISSION_ONLY', script)
        self.assertIn('Open-PilotResult', script)
        self.assertIn('START_QUANTUM.cmd', script)

    def test_one_click_attestations_are_explicit_and_defender_remains_enabled(self):
        script = self.one_click
        self.assertIn(
            'if ($NonInteractive -or ($AuthorityAttested -and $SchemaReviewed))',
            script,
        )
        self.assertIn('if ($AuthorityAttested) { $importArguments["AuthorityAttested"] = $true }', script)
        self.assertIn('if ($SchemaReviewed) { $importArguments["SchemaReviewed"] = $true }', script)
        self.assertIn('if ($SkipDefenderScan) { $importArguments["SkipDefenderScan"] = $true }', script)
        self.assertIn('No AUTHORIZE or REVIEWED console input is required.', script)
        self.assertNotIn('SkipDefenderScan = $true', script)
        self.assertNotIn('finance_request =', script)

    def test_importer_honors_explicit_attestations_but_fails_closed_without_them(self):
        script = self.importer
        attested = script.index('if ($AlreadyAttested)')
        noninteractive = script.index('if ($NonInteractive)', attested)
        read_host = script.index('$answer = Read-Host $Prompt', noninteractive)
        self.assertLess(attested, noninteractive)
        self.assertLess(noninteractive, read_host)
        self.assertIn('Non-interactive mode requires explicit $Expected attestation switch.', script)
        self.assertIn('from quantum.pilot.windows_runner import main; raise SystemExit(main())', script)
        self.assertNotIn('"-m", "quantum.pilot.windows_runner"', script)

    def test_cloud_sync_paths_and_unmanaged_outputs_are_blocked(self):
        script = self.one_click
        self.assertIn('Assert-LocalPathSafety -Path $PackageRoot', script)
        self.assertIn('Assert-LocalPathSafety -Path $TargetRoot', script)
        self.assertIn('$env:OneDrive', script)
        self.assertIn('\\Dropbox\\', script)
        self.assertIn('Test-PathWithin -Child $directory -Parent $Root', script)
        self.assertIn('will not be opened automatically', script)

    def test_installer_preserves_data_and_installs_reusable_launcher(self):
        script = self.installer
        self.assertIn('foreach ($name in @("config", "data", "output", "scripts"))', script)
        self.assertIn('scripts/one_click_home_local.ps1', script)
        self.assertIn('START_QUANTUM.cmd', script)
        self.assertIn('$sourceOneClick', script)
        self.assertIn('$oneClickTarget', script)
        self.assertIn('-InstalledRoot "%~dp0" -SkipInstall -AuthorityAttested -SchemaReviewed', script)
        self.assertIn('import_source.ps1" -AuthorityAttested -SchemaReviewed', script)
        self.assertIn('New-QuantumShortcut', script)
        self.assertIn('Existing config, data and output directories were preserved.', script)

    def test_package_manifest_is_verified_before_target_mutation(self):
        script = self.installer
        verify = script.index('$packageManifest = Assert-PackageManifest -Root $SourceRoot')
        mutation = script.index('New-Item -ItemType Directory -Path $TargetRoot')
        self.assertLess(verify, mutation)
        for required in (
            'scripts/one_click_home_local.ps1',
            'START_QUANTUM.cmd',
            'scripts/import_source.ps1',
            'scripts/configure_home_local.ps1',
        ):
            self.assertIn(required, script)

    def test_noninteractive_mode_requires_explicit_file_and_attestations(self):
        script = self.one_click
        self.assertIn('File is required in non-interactive mode.', script)
        self.assertRegex(script, re.compile(r'if \(\$AuthorityAttested\).*AuthorityAttested', re.DOTALL))
        self.assertRegex(script, re.compile(r'if \(\$SchemaReviewed\).*SchemaReviewed', re.DOTALL))

    def test_windows_entry_scripts_are_ascii_for_powershell_51(self):
        for name, script in (
            ("one_click_home_local.ps1", self.one_click),
            ("import_source.ps1", self.importer),
            ("install_home_local.ps1", self.installer),
            ("build_local_production.ps1", self.builder),
        ):
            non_ascii = sorted({character for character in script if ord(character) > 127})
            self.assertEqual(non_ascii, [], name)


if __name__ == "__main__":
    unittest.main()
