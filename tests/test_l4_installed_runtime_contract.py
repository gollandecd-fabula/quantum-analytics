from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "l4-installed-runtime.yml"
RUNNER = ROOT / "scripts" / "ci" / "l4_installed_runtime.ps1"

CHECKOUT_SHA = "34e114876b0b11c390a56381ad16ebd13914f8d5"
SETUP_PYTHON_SHA = "a26af69be951a213d495a4c3e4e4022e16d87065"
UPLOAD_ARTIFACT_SHA = "ea165f8d65b6e75b540449e92b4886f43607fa02"


class L4InstalledRuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.runner = RUNNER.read_text(encoding="ascii")

    def test_workflow_is_exact_head_windows_and_always_uploads_evidence(self) -> None:
        self.assertIn("runs-on: windows-latest", self.workflow)
        self.assertIn("github.event.pull_request.head.sha || github.sha", self.workflow)
        self.assertIn("TARGET_SHA:", self.workflow)
        self.assertIn("scripts\\ci\\l4_installed_runtime.ps1", self.workflow)
        self.assertIn("if: always()", self.workflow)
        self.assertIn("quantum-l4-installed-runtime-evidence", self.workflow)
        self.assertIn("src/quantum/application/**", self.workflow)

    def test_workflow_actions_are_pinned_to_full_commit_shas(self) -> None:
        self.assertIn(f"actions/checkout@{CHECKOUT_SHA}", self.workflow)
        self.assertIn(f"actions/setup-python@{SETUP_PYTHON_SHA}", self.workflow)
        self.assertIn(f"actions/upload-artifact@{UPLOAD_ARTIFACT_SHA}", self.workflow)
        action_refs = re.findall(r"uses:\s+[^\s@]+@([^\s]+)", self.workflow)
        self.assertGreaterEqual(len(action_refs), 3)
        for ref in action_refs:
            self.assertRegex(ref, r"^[0-9a-f]{40}$")

    def test_runner_is_ascii_and_has_no_unsafe_variable_scope_interpolation(self) -> None:
        RUNNER.read_bytes().decode("ascii")
        unsafe = re.findall(r"\$[A-Za-z_][A-Za-z0-9_]*:(?![A-Za-z_])", self.runner)
        self.assertEqual(unsafe, [])
        self.assertEqual(self.runner.count("("), self.runner.count(")"))
        self.assertEqual(self.runner.count("{"), self.runner.count("}"))

    def test_runner_requires_exact_head_and_pinned_dependencies(self) -> None:
        self.assertIn('^[0-9a-f]{40}$', self.runner)
        self.assertIn("git -C $RepoRoot rev-parse HEAD", self.runner)
        self.assertIn("--require-hashes", self.runner)
        self.assertIn("requirements/windows-home-local.txt", self.runner)
        self.assertIn("PACKAGE_HEAD_MISMATCH", self.runner)
        self.assertIn("PACKAGE_MARKETPLACE_WRITES_ENABLED", self.runner)

    def test_runner_installs_twice_and_preserves_user_sentinels(self) -> None:
        self.assertIn('$Step = "FIRST_INSTALL"', self.runner)
        self.assertIn('$Step = "SECOND_INSTALL"', self.runner)
        self.assertGreaterEqual(self.runner.count("-File $installer"), 2)
        self.assertIn("New-UserSentinels", self.runner)
        self.assertGreaterEqual(self.runner.count("Assert-UserSentinels"), 3)
        self.assertIn("SECOND_INSTALL_BACKUP_NOT_FOUND", self.runner)
        self.assertIn("STALE_INSTALL_TRANSACTION_FOUND", self.runner)

    def test_runner_binds_source_package_to_installed_managed_tree(self) -> None:
        self.assertIn("Get-ExpectedManagedFiles", self.runner)
        self.assertIn("Get-ActualManagedFiles", self.runner)
        self.assertGreaterEqual(self.runner.count("Assert-ManagedFiles"), 4)
        self.assertIn("MANAGED_FILE_COUNT_MISMATCH", self.runner)
        self.assertIn("MANAGED_HASH_MISMATCH", self.runner)
        self.assertIn("INSTALLED_MANIFEST.json", self.runner)

    def test_runner_locks_installed_launcher_semantics(self) -> None:
        self.assertIn("Assert-LauncherContracts", self.runner)
        self.assertIn('-InstalledRoot `"%~dp0`" -SkipInstall', self.runner)
        self.assertIn("INSTALLED_LAUNCHER_CONTENT", self.runner)
        self.assertIn("START_QUANTUM.cmd", self.runner)
        self.assertIn("IMPORT_XLSX.cmd", self.runner)
        self.assertIn("CONFIGURE_HOME_LOCAL.cmd", self.runner)

    def test_runner_executes_installed_self_test_tax_probe_and_runtime(self) -> None:
        self.assertIn("Invoke-InstalledSelfTest", self.runner)
        self.assertIn("DESKTOP_CENTER_SELF_TEST_PASS", self.runner)
        self.assertIn("FINANCE_CENTER_SELF_TEST_PASS", self.runner)
        self.assertIn("INSTALLED_TAX_BASE_IMPORT_PASS", self.runner)
        self.assertIn("Invoke-RuntimeProbe", self.runner)
        self.assertIn("alive_after_seconds = 8", self.runner)
        self.assertIn("INSTALLED_RUNTIME_EXITED", self.runner)
        self.assertIn("Get-Sha256WithRetry", self.runner)
        self.assertIn("$process.Dispose()", self.runner)

    def test_runner_has_tamper_negative_control_and_never_claims_l5(self) -> None:
        self.assertIn("Invoke-TamperNegativeControl", self.runner)
        self.assertIn("TAMPER_NEGATIVE_CONTROL_DID_NOT_FAIL", self.runner)
        self.assertIn('evidence_level = "L4_INSTALLED_RUNTIME"', self.runner)
        self.assertIn('physical_user_path_verified = $false', self.runner)
        self.assertIn('marketplace_write_enabled = $false', self.runner)
        self.assertNotIn('physical_user_path_verified = $true', self.runner)
        self.assertNotIn('marketplace_write_enabled = $true', self.runner)


if __name__ == "__main__":
    unittest.main()
