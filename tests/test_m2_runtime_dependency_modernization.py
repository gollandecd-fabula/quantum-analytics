from __future__ import annotations

import base64
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSION = "3.13.14"
PYTHON_INSTALLER = "python-3.13.14-amd64.exe"
PYTHON_SHA256 = "c54d9b9bbb8a36e6489363ddd01139707fd781d72f1f9e90c7ec65d0061368e0"
TZDATA_VERSION = "2026.3"
TZDATA_SHA256 = "dc096730c87af6cab1b171c9d532be840741ff5d459015e7f6947bd7d7e54931"

WINDOWS_RUNTIME_FILES = (
    "requirements/windows-home-local.txt",
    "scripts/windows/build_local_production.ps1",
    "scripts/windows/build_two_installer_bundles.ps1",
    "scripts/windows/import_source.ps1",
    "scripts/windows/one_click_home_local.ps1",
    "src/quantum/pilot/import_xlsx_source.ps1",
    "scripts/ci/native_one_button_r37.ps1",
    "tools/m7_security_performance_one_click.py",
    "tests/test_m7_security_performance_one_click.py",
    ".github/workflows/build-one-button-redteam-r3.yml",
    ".github/workflows/build-two-installer-bundles-r2.yml",
    ".github/workflows/l4-installed-runtime.yml",
    ".github/workflows/m7-security-performance-one-click.yml",
    ".github/workflows/m8-clean-environment-reproduction.yml",
    ".github/workflows/windows-local-production.yml",
    ".github/workflows/windows-release-gate.yml",
    ".github/workflows/windows-source-package-launchers-r1.yml",
    ".github/workflows/windows-universal-any-file-corpus-r4.yml",
    "docs/architecture/ONE_CLICK_HOME_LOCAL_R1.md",
)

LINUX_SOURCE_FILES = (
    ".github/workflows/foundation-ci.yml",
    ".github/workflows/oss-admission-ci.yml",
)


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def decoded_base64_strings(text: str) -> list[str]:
    result: list[str] = []
    for value in re.findall(r"[\"']([A-Za-z0-9+/]{16,}={0,2})[\"']", text):
        try:
            result.append(base64.b64decode(value, validate=True).decode("utf-8"))
        except Exception:
            continue
    return result


class M2RuntimeDependencyModernizationTests(unittest.TestCase):
    def test_windows_runtime_and_tzdata_are_exactly_pinned(self) -> None:
        builder = read("scripts/windows/build_two_installer_bundles.ps1")
        requirements = read("requirements/windows-home-local.txt")
        project = read("pyproject.toml")
        workflow = read(".github/workflows/build-two-installer-bundles-r2.yml")
        self.assertIn(f'$pythonVersion = "{PYTHON_VERSION}"', builder)
        self.assertIn(PYTHON_SHA256, builder)
        self.assertIn(PYTHON_INSTALLER, workflow)
        self.assertIn(PYTHON_SHA256, workflow)
        self.assertIn(f"tzdata=={TZDATA_VERSION}", requirements)
        self.assertIn(TZDATA_SHA256, requirements)
        self.assertIn('requires-python = ">=3.12"', project)
        self.assertIn(f'"tzdata=={TZDATA_VERSION}; platform_system == \'Windows\'"', project)

    def test_windows_runtime_paths_have_no_stale_312_contract(self) -> None:
        stale = (
            "3.12.10", "Python312", "Test-Python312", "-3.12",
            "(3,12)", "(3, 12)", "Python 3.12", "tzdata==2026.2",
            "bbe9af844f658da81a5f95019480da3a89415801f6cc966806612cc7169bffe7",
        )
        for relative in WINDOWS_RUNTIME_FILES:
            text = read(relative)
            decoded = "\n".join(decoded_base64_strings(text))
            for marker in stale:
                self.assertNotIn(marker, text, f"stale marker in {relative}: {marker}")
                self.assertNotIn(marker, decoded, f"stale encoded marker in {relative}: {marker}")

    def test_linux_source_gates_accept_python_312_plus(self) -> None:
        for relative in LINUX_SOURCE_FILES:
            text = read(relative)
            self.assertIn("sys.version_info < (3, 12)", text, relative)
            self.assertNotIn("sys.version_info < (3, 13)", text, relative)
            self.assertNotIn("setup-python", text, relative)

    def test_runtime_resolvers_target_python_313(self) -> None:
        resolver_files = WINDOWS_RUNTIME_FILES[1:7]
        for relative in resolver_files:
            text = read(relative)
            self.assertIn("3,13", text.replace(" ", ""), relative)
            self.assertTrue("-3.13" in text or "Python313" in text, relative)

    def test_current_windows_workflows_use_python_31314(self) -> None:
        workflow_files = tuple(
            relative for relative in WINDOWS_RUNTIME_FILES
            if relative.startswith(".github/workflows/")
        )
        for relative in workflow_files:
            text = read(relative)
            self.assertNotIn('python-version: "3.12"', text, relative)
            if "setup-python" in text:
                self.assertIn('python-version: "3.13.14"', text, relative)

    def test_build_workflow_verifies_new_bundle_and_hash(self) -> None:
        workflow = read(".github/workflows/build-two-installer-bundles-r2.yml")
        self.assertIn(PYTHON_INSTALLER, workflow)
        self.assertIn(PYTHON_SHA256, workflow)
        self.assertIn("Python Software Foundation", workflow)
        self.assertIn('"pyproject.toml"', workflow)
        self.assertIn('"tests/test_m2_runtime_dependency_modernization.py"', workflow)

    def test_runtime_hash_tamper_is_fail_closed(self) -> None:
        builder = read("scripts/windows/build_two_installer_bundles.ps1")
        workflow = read(".github/workflows/build-two-installer-bundles-r2.yml")
        self.assertIn("if ($pythonActualSha256 -ne $pythonExpectedSha256)", builder)
        self.assertIn("if ($pythonActualHash -ne $pythonExpectedHash)", builder)
        self.assertIn("Get-AuthenticodeSignature", workflow)

    def test_atomic_json_closes_temp_file_before_replace(self) -> None:
        source = read("src/quantum/application/_finance_profile_groups.py")
        with_position = source.index("with tempfile.NamedTemporaryFile(")
        replace_position = source.index("os.replace(temporary, path)")
        block_end = source.index("    except Exception:", with_position)
        self.assertGreater(replace_position, with_position)
        self.assertLess(replace_position, block_end)
        replace_line = next(
            line for line in source.splitlines()
            if "os.replace(temporary, path)" in line
        )
        self.assertEqual(replace_line, "        os.replace(temporary, path)")

    def test_m7_installs_authoritative_hash_locked_dependency(self) -> None:
        workflow = read(".github/workflows/m7-security-performance-one-click.yml")
        self.assertIn("--require-hashes -r requirements/windows-home-local.txt", workflow)
        self.assertNotIn("tzdata==2026.2", workflow)


if __name__ == "__main__":
    unittest.main()
