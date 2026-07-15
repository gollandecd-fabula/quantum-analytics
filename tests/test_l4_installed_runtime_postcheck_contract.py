from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "l4-installed-runtime.yml"
POSTCHECK = ROOT / "scripts" / "ci" / "l4_installed_runtime_postcheck.ps1"


class L4InstalledRuntimePostcheckContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")
        cls.postcheck = POSTCHECK.read_text(encoding="ascii")

    def test_workflow_executes_postcheck_before_evidence_upload(self) -> None:
        postcheck_step = self.workflow.index(
            "Run independent L4 evidence postcheck"
        )
        upload_step = self.workflow.index("Upload L4 evidence")
        self.assertLess(postcheck_step, upload_step)
        self.assertIn(
            "scripts\\ci\\l4_installed_runtime_postcheck.ps1",
            self.workflow,
        )
        self.assertIn("l4-installed-runtime-postcheck.log", self.workflow)

    def test_postcheck_verifies_main_evidence_identity_and_exact_head(self) -> None:
        self.assertIn("MAIN_L4_EVIDENCE_HASH_MISMATCH", self.postcheck)
        self.assertIn("MAIN_L4_HEAD_MISMATCH", self.postcheck)
        self.assertIn("L4_INSTALLED_RUNTIME_PASS", self.postcheck)
        self.assertIn("L4_INSTALLED_RUNTIME", self.postcheck)

    def test_postcheck_requires_real_installed_gui_window(self) -> None:
        self.assertIn("INSTALLED_RUNTIME_GUI_WINDOW_NOT_FOUND", self.postcheck)
        self.assertIn("INSTALLED_RUNTIME_GUI_TITLE_EMPTY", self.postcheck)
        self.assertIn("INSTALLED_RUNTIME_GUI_TITLE_INVALID", self.postcheck)
        self.assertIn("INSTALLED_RUNTIME_COMMAND_NOT_BOUND_TO_ROOT", self.postcheck)
        self.assertIn("INSTALLED_RUNTIME_COMMAND_NOT_DESKTOP_CENTER", self.postcheck)

    def test_postcheck_tamper_control_fails_for_same_size_hash_change(self) -> None:
        self.assertIn("$bytes[0] = $bytes[0] -bxor 1", self.postcheck)
        self.assertIn("FILE_HASH_MISMATCH", self.postcheck)
        self.assertIn("INDEPENDENT_TAMPER_CONTROL_DID_NOT_FAIL", self.postcheck)
        self.assertIn("tampered_size_unchanged = $true", self.postcheck)
        self.assertIn("rejected = $tamperRejected", self.postcheck)

    def test_postcheck_rebuilds_evidence_manifest_and_never_claims_l5(self) -> None:
        self.assertIn("Write-BundleManifest", self.postcheck)
        self.assertIn("L4_INDEPENDENT_POSTCHECK_PASS", self.postcheck)
        self.assertIn('evidence_level = "L4_INSTALLED_RUNTIME"', self.postcheck)
        self.assertIn('physical_user_path_verified = $false', self.postcheck)
        self.assertIn('marketplace_write_enabled = $false', self.postcheck)
        self.assertNotIn('physical_user_path_verified = $true', self.postcheck)
        self.assertNotIn('marketplace_write_enabled = $true', self.postcheck)


if __name__ == "__main__":
    unittest.main()
