from __future__ import annotations

from pathlib import Path
import base64
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _decoded_user_text(script: str) -> str:
    decoded: list[str] = []
    for token in re.findall(r'"([A-Za-z0-9+/]{16,}={0,2})"', script):
        try:
            value = base64.b64decode(token, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        decoded.append(value)
    return "\n".join(decoded)


def _decode_csharp_unicode(script: str) -> str:
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match.group(1), 16)), script)


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
        self.assertIn('Эта версия HOME_LOCAL поддерживает только WILDBERRIES.', _decoded_user_text(self.configurator))
        self.assertIn('"WB_ONLY": frozenset({"WILDBERRIES"})', self.bridge)
        self.assertIn("MARKETPLACE_OUTSIDE_RELEASE_SCOPE", self.bridge)

    def test_exe_builder_is_offline_hash_bound_and_exact_head_bound(self) -> None:
        self.assertIn("Microsoft.NET\\Framework64\\v4.0.30319\\csc.exe", self.exe_builder)
        self.assertIn("QuantumOfflineBundle.zip", self.exe_builder)
        self.assertIn("ExpectedBundleSha256", self.exe_builder)
        self.assertIn("ExpectedSourceCommit", self.exe_builder)
        decoded_exe = _decode_csharp_unicode(self.exe_builder)
        self.assertIn("SHA-256 встроенного автономного пакета Quantum", decoded_exe)
        self.assertIn("Commit исходного кода встроенного установщика", decoded_exe)
        self.assertNotIn("Embedded Quantum offline bundle SHA-256 mismatch.", self.exe_builder)
        self.assertIn('String.Equals(args[0], "--self-test"', self.exe_builder)
        self.assertIn('result["native_self_test"] = true', self.exe_builder)
        self.assertIn('release_scope = "WB_ONLY"', self.exe_builder)
        self.assertIn("marketplace_write_enabled = $false", self.exe_builder)
        self.assertIn("production_release_authorized = $false", self.exe_builder)
        self.assertIn('builder = "WINDOWS_DOTNET_FRAMEWORK_CSC"', self.exe_builder)
        self.assertNotIn("iexpress.exe", self.exe_builder.lower())
        self.assertNotIn("Invoke-WebRequest", self.exe_builder)
        self.assertNotIn("Start-BitsTransfer", self.exe_builder)

    def test_exe_workflow_requires_exact_head_and_direct_native_self_test(self) -> None:
        self.assertIn("github.event.pull_request.head.sha || github.sha", self.workflow)
        self.assertIn("build_exe_installer.ps1", self.workflow)
        self.assertIn("& $exe --self-test $testResultPath", self.workflow)
        self.assertIn("WINDOWS_DOTNET_FRAMEWORK_CSC", self.workflow)
        self.assertIn("native_self_test", self.workflow)
        self.assertIn("Quantum_WB_Offline_Setup.exe", self.workflow)
        self.assertIn("exe-installer-result.json", self.workflow)
        self.assertIn("quantum-exe-native-test.json", self.workflow)
        self.assertIn("Quantum-WB-Offline-Setup-EXE", self.workflow)
        self.assertNotIn("QUANTUM_EXE_TEST_ONLY", self.workflow)
        self.assertNotIn("iexpress", self.workflow.lower())
        self.assertNotIn("marketplace_write_enabled: true", self.workflow.lower())


if __name__ == "__main__":
    unittest.main()
