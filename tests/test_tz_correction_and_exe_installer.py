from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TzCorrectionAndExeInstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.defaults = (
            ROOT / "src/quantum/adapters/defaults.py"
        ).read_text(encoding="utf-8")
        cls.adapter_api = (
            ROOT / "src/quantum/adapters/__init__.py"
        ).read_text(encoding="utf-8")
        cls.bridge = (
            ROOT / "src/quantum/pilot/windows_source_bridge.py"
        ).read_text(encoding="utf-8")
        cls.configurator = (
            ROOT / "scripts/windows/configure_home_local.ps1"
        ).read_text(encoding="utf-8")
        cls.exe_builder = (
            ROOT / "scripts/windows/build_exe_installer.ps1"
        ).read_text(encoding="utf-8")
        cls.workflow = (
            ROOT / ".github/workflows/build-two-installer-bundles-r2.yml"
        ).read_text(encoding="utf-8")

    def test_shared_adapter_core_remains_marketplace_neutral(self) -> None:
        self.assertIn("from .ozon.adapter import OzonSourceAdapter", self.defaults)
        self.assertIn("adapters.append(OzonSourceAdapter())", self.defaults)
        self.assertIn("registry.register_many", self.defaults)
        for forbidden in (
            "LOCAL_RELEASE_SCOPE",
            "LOCAL_RELEASE_MARKETPLACES",
            "DEFERRED_MARKETPLACES",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.adapter_api)

    def test_wb_only_policy_lives_in_home_local_release_layer(self) -> None:
        self.assertIn('release_scope = "WB_ONLY"', self.configurator)
        self.assertIn('deferred_marketplaces = @("OZON")', self.configurator)
        self.assertIn(
            'This HOME_LOCAL release supports only WILDBERRIES. Ozon is deferred.',
            self.configurator,
        )
        self.assertIn('"WB_ONLY": frozenset({"WILDBERRIES"})', self.bridge)
        self.assertIn("MARKETPLACE_OUTSIDE_RELEASE_SCOPE", self.bridge)

    def test_exe_builder_is_offline_hash_bound_and_exact_head_bound(self) -> None:
        self.assertIn("System32\\iexpress.exe", self.exe_builder)
        self.assertIn("2_QUANTUM_FULL_OFFLINE_INSTALLER.zip", self.exe_builder)
        self.assertIn("Embedded Quantum offline bundle SHA-256 mismatch.", self.exe_builder)
        self.assertIn("Embedded installer source commit mismatch.", self.exe_builder)
        self.assertIn("QUANTUM_EXE_TEST_ONLY", self.exe_builder)
        self.assertIn("QuantumExeNativeTest_{0}.request", self.exe_builder)
        self.assertIn("payload_sha256 = $bundleHash", self.exe_builder)
        self.assertIn("source_commit = $sourceCommit", self.exe_builder)
        self.assertIn("result_path = $nativeTestResultPath", self.exe_builder)
        self.assertIn("native_test_request_consumed", self.exe_builder)
        self.assertIn('release_scope = "WB_ONLY"', self.exe_builder)
        self.assertIn("marketplace_write_enabled = $false", self.exe_builder)
        self.assertIn("production_release_authorized = $false", self.exe_builder)
        self.assertNotIn("Invoke-WebRequest", self.exe_builder)
        self.assertNotIn("Start-BitsTransfer", self.exe_builder)

    def test_exe_workflow_requires_exact_head_and_native_test_mode(self) -> None:
        self.assertIn("github.event.pull_request.head.sha || github.sha", self.workflow)
        self.assertIn("build_exe_installer.ps1", self.workflow)
        self.assertIn("QUANTUM_EXE_TEST_ONLY", self.workflow)
        self.assertIn("Quantum_WB_Offline_Setup.exe", self.workflow)
        self.assertIn("exe-installer-result.json", self.workflow)
        self.assertIn("quantum-exe-native-test.json", self.workflow)
        self.assertIn("Quantum-WB-Offline-Setup-EXE", self.workflow)
        self.assertNotIn("marketplace_write_enabled: true", self.workflow.lower())


if __name__ == "__main__":
    unittest.main()
