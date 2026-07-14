from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools/m7_security_performance_one_click.py"
SPEC = importlib.util.spec_from_file_location("m7_assurance", TOOL_PATH)
assert SPEC is not None and SPEC.loader is not None
m7 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = m7
SPEC.loader.exec_module(m7)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _fixture(root: Path) -> None:
    _write(root / "pyproject.toml", "marketplace_write_enabled = false\n")
    _write(
        root / "scripts/windows/one_click_home_local.ps1",
        "\n".join(
            (
                "Assert-LocalPathSafety -Path $PackageRoot",
                "Assert-LocalPathSafety -Path $TargetRoot",
                "if (-not $AuthorityAttested -or -not $SchemaReviewed) { throw 'x' }",
                "launchers never attest on your behalf",
                "Test-PathWithin -Child $directory -Parent $Root",
                "& $installer -SourceRoot $PackageRoot -TargetRoot $TargetRoot",
                "$Config = Invoke-ConfigurationWizard",
                "Python 3.12 or newer was not found.",
                "File is required in non-interactive mode.",
                "The supplied configuration is not ready:",
                "Quantum did not create the expected pilot result:",
                "& $importer @importArguments",
            )
        ),
    )
    _write(
        root / "scripts/windows/import_source.ps1",
        "\n".join(
            (
                "Microsoft Defender scan failed or reported a threat.",
                "Non-interactive mode requires explicit $Expected attestation switch.",
                "ExpectedFileSha256",
                "PreScannedEvidenceSha256",
                "Source selection cancelled.",
            )
        ),
    )
    _write(
        root / "scripts/windows/install_home_local.ps1",
        "\n".join(
            (
                'if ($manifest.release_state -ne "RELEASE_BLOCKED") { throw "x" }',
                "if ($manifest.marketplace_write_enabled -ne $false) { throw 'x' }",
                "$packageManifest = Assert-PackageManifest -Root $SourceRoot",
                "Manifest hash mismatch",
                "New-Item -ItemType Directory -Path $TargetRoot",
                'set "quantum_exit=%errorlevel%"',
                "exit /b %quantum_exit%",
                "Existing config, data and output directories were preserved.",
            )
        ),
    )
    _write(
        root / "scripts/windows/build_local_production.ps1",
        'release_state = "RELEASE_BLOCKED"\nmarketplace_write_enabled = $false\n',
    )
    _write(root / "src/quantum/__init__.py", "")


class M7AssuranceUnitTests(unittest.TestCase):
    def test_clean_fixture_passes_security_and_one_click_gates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _fixture(root)
            result = m7.audit_repository(root)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["security_p0_p1_open"], 0)
        self.assertFalse(result["marketplace_write_enabled"])
        self.assertFalse(result["release_authorized"])

    def test_write_enabled_runtime_is_security_p0(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _fixture(root)
            _write(
                root / "src/quantum/unsafe.py",
                "marketplace_write_enabled = True\n",
            )
            findings = m7.audit_security(root)
        self.assertTrue(
            any(finding.finding_id == "M7-S006" and finding.severity == "P0" for finding in findings),
            findings,
        )

    def test_missing_actionable_error_is_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _fixture(root)
            path = root / "scripts/windows/one_click_home_local.ps1"
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "File is required in non-interactive mode.",
                    "",
                ),
                encoding="utf-8",
            )
            findings = m7.audit_one_click(root)
        self.assertTrue(
            any(finding.finding_id == "M7-O004" for finding in findings),
            findings,
        )

    def test_performance_budget_accepts_slack_and_rejects_regression(self) -> None:
        baseline_root = Path("baseline")
        candidate_root = Path("candidate")

        def passing_probe(root: Path, _: int) -> float:
            return 1.0 if root.name == "baseline" else 1.2

        passing = m7.compare_performance(
            baseline_root,
            candidate_root,
            repeats=3,
            max_ratio=1.5,
            absolute_slack_seconds=0.25,
            probe_once=passing_probe,
        )
        self.assertEqual(passing.status, "PASS")

        def failing_probe(root: Path, _: int) -> float:
            return 1.0 if root.name == "baseline" else 2.0

        failing = m7.compare_performance(
            baseline_root,
            candidate_root,
            repeats=3,
            max_ratio=1.5,
            absolute_slack_seconds=0.25,
            probe_once=failing_probe,
        )
        self.assertEqual(failing.status, "FAIL")


class M7RepositoryContractTests(unittest.TestCase):
    def test_repository_security_and_one_click_audit_passes(self) -> None:
        result = m7.audit_repository(ROOT)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["security_p0_p1_open"], 0)

    def test_performance_budget_is_pinned_to_m6_exact_head(self) -> None:
        budget = json.loads(
            (ROOT / "docs/evidence/M7_PERFORMANCE_BUDGET.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(budget["baseline_head"], m7.DEFAULT_BASELINE_SHA)
        self.assertEqual(budget["aggregation"], "median")
        self.assertGreaterEqual(budget["repeats"], 3)
        self.assertFalse(budget["marketplace_write_enabled"])
        self.assertFalse(budget["release_authorized"])

    def test_workflow_uses_exact_head_read_only_permissions_and_baseline_compare(self) -> None:
        workflow = (
            ROOT / ".github/workflows/m7-security-performance-one-click.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("github.event.pull_request.head.sha || github.sha", workflow)
        self.assertIn(m7.DEFAULT_BASELINE_SHA, workflow)
        self.assertIn("m7_security_performance_one_click.py compare", workflow)
        self.assertIn("native_one_button_r37.ps1", workflow)
        self.assertNotIn("marketplace_write_enabled: true", workflow.lower())

    def test_defect_register_has_no_open_security_p0_or_p1(self) -> None:
        register = json.loads(
            (ROOT / "docs/evidence/M7_DEFECT_REGISTER.json").read_text(
                encoding="utf-8"
            )
        )
        open_blocking = [
            defect
            for defect in register["defects"]
            if defect["severity"] in {"P0", "P1"}
            and not defect["status"].startswith("CLOSED")
        ]
        self.assertEqual(open_blocking, [])
        self.assertFalse(register["release_authorized"])
        self.assertFalse(register["marketplace_writes_authorized"])
        self.assertFalse(register["merge_to_main_authorized"])


if __name__ == "__main__":
    unittest.main()
