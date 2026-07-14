from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PlateauM7ReleaseIntegrationTests(unittest.TestCase):
    def test_installed_copy_detection_is_resilient(self) -> None:
        text = (
            ROOT / "scripts/windows/one_click_home_local.ps1"
        ).read_text(encoding="ascii")
        self.assertIn("$installedMarkers = @(", text)
        self.assertIn("$hasInstalledMarker = $false", text)
        for marker in (
            "START_QUANTUM.cmd",
            "scripts\\import_source.ps1",
            "scripts\\configure_home_local.ps1",
            "src\\quantum\\pilot\\windows_runner.py",
        ):
            self.assertIn(marker, text)
        self.assertIn(
            "$hasInstalledMarker -and -not (Test-Path -LiteralPath $packageInstaller",
            text,
        )
        self.assertNotIn(
            "(Test-Path -LiteralPath $installedRuntime -PathType Leaf) -and",
            text,
        )

    def test_release_gate_targets_desktop_not_legacy_http(self) -> None:
        text = (
            ROOT / ".github/workflows/windows-release-gate.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("name: Windows Desktop Release Gate", text)
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("localhost:8000", text)
        self.assertNotIn("api/local-pilot/health", text)
        self.assertIn("quantum.application.desktop_center", text)
        self.assertIn("DESKTOP_CENTER_SELF_TEST_PASS", text)
        self.assertIn("FINANCE_CENTER_SELF_TEST_PASS", text)
        self.assertIn("windows_local_production_r37.ps1", text)
        self.assertIn("build_two_installer_bundles.ps1", text)
        self.assertIn("build_exe_installer.ps1", text)
        self.assertIn("Quantum_WB_Offline_Setup.exe", text)

    def test_release_gate_freezes_and_verifies_exact_head(self) -> None:
        text = (
            ROOT / ".github/workflows/windows-release-gate.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("exact_sha", text)
        self.assertIn("TARGET_SHA", text)
        self.assertIn("source_commit", text)
        self.assertIn("Get-FileHash", text)
        self.assertIn("--self-test", text)
        self.assertIn("marketplace_write_enabled", text)
        self.assertIn("WB_ONLY", text)
        self.assertIn("-InstalledRoot", text)
        self.assertIn("-SkipInstall", text)

    def test_release_gate_uploads_a_single_user_installer(self) -> None:
        text = (
            ROOT / ".github/workflows/windows-release-gate.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("Quantum-WB-Desktop-Plateau-Installer", text)
        self.assertIn("FINAL_RELEASE_INSPECTION.txt", text)
        self.assertIn("exe-installer-result.json", text)
        self.assertIn("exe-native-test-result.json", text)
        self.assertIn("installed-desktop-self-test.json", text)


if __name__ == "__main__":
    unittest.main()
