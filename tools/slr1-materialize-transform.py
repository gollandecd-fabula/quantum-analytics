from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re

ROOT = Path.cwd()


def replace_method(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, flags=re.S)
    if count != 1:
        raise SystemExit(f"METHOD_REPLACEMENT_COUNT:{path}:{count}")
    path.write_text(updated, encoding="utf-8")


replace_method(
    ROOT / "tests/test_windows_first_run_finance_center_r74.py",
    r"    def test_installed_script_self_recovers_if_launcher_loses_skip_install\(self\) -> None:\n.*?(?=    def test_installed_launcher_always_uses_skip_install)",
    '''    def test_installed_script_self_recovers_if_launcher_loses_skip_install(self) -> None:\n        script = self.script\n        recovery = script.index('$selfRoot =')\n        branch = script.index('if ($SkipInstall) {', recovery)\n        recovery_block = script[recovery:branch]\n        self.assertLess(recovery, branch)\n        self.assertIn('Test-InstallationPackageLayout -Root $selfRoot', recovery_block)\n        self.assertIn('Get-InstalledRuntimeMissingComponents -Root $selfRoot', recovery_block)\n        self.assertIn('$SkipInstall = $true', recovery_block)\n        self.assertIn('$InstalledRoot = $selfRoot', recovery_block)\n        self.assertIn('Assert-InstalledRuntimeLayout -Root $selfRoot', recovery_block)\n        self.assertNotIn('$hasInstalledMarker', recovery_block)\n\n''',
)
replace_method(
    ROOT / "tests/test_windows_first_run_finance_center_r74.py",
    r"    def test_installed_launcher_always_uses_skip_install\(self\) -> None:\n.*?(?=    def test_explicit_file_and_noninteractive_import_paths_remain_available)",
    '''    def test_installed_launcher_always_uses_skip_install(self) -> None:\n        installer = self.installer\n        self.assertIn(\n            'for %%I in ("%~dp0.") do set "QUANTUM_ROOT=%%~fI"',\n            installer,\n        )\n        self.assertIn(\n            'one_click_home_local.ps1" -InstalledRoot "%QUANTUM_ROOT%" -SkipInstall %*',\n            installer,\n        )\n        self.assertNotIn('-InstalledRoot "%~dp0" -SkipInstall', installer)\n\n''',
)
replace_method(
    ROOT / "tests/test_plateau_m7_release_integration.py",
    r"    def test_installed_copy_detection_is_resilient\(self\) -> None:\n.*?(?=    def test_release_gate_targets_desktop_not_legacy_http)",
    '''    def test_installed_copy_detection_is_resilient(self) -> None:\n        text = (\n            ROOT / "scripts/windows/one_click_home_local.ps1"\n        ).read_text(encoding="ascii")\n        self.assertIn("function Test-InstallationPackageLayout", text)\n        self.assertIn("function Get-InstalledRuntimeMissingComponents", text)\n        self.assertIn("function Assert-InstalledRuntimeLayout", text)\n        self.assertIn("Test-InstallationPackageLayout -Root $selfRoot", text)\n        self.assertIn("Get-InstalledRuntimeMissingComponents -Root $selfRoot", text)\n        self.assertIn("$SkipInstall = $true", text)\n        self.assertIn("$InstalledRoot = $selfRoot", text)\n        self.assertNotIn("$hasInstalledMarker", text)\n\n''',
)

workflow = ROOT / ".github/workflows/shortcut-launch-repair-r1.yml"
text = workflow.read_text(encoding="utf-8")
for marker in (
    '      - "tests/test_windows_first_run_finance_center_r74.py"\n',
    '      - "tests/test_plateau_m7_release_integration.py"\n',
):
    if marker not in text:
        text = text.replace(
            '      - "tests/test_shortcut_launch_repair_r1.py"\n',
            '      - "tests/test_shortcut_launch_repair_r1.py"\n' + marker,
        )
for marker in (
    '          tests/test_windows_first_run_finance_center_r74.py\n',
    '          tests/test_plateau_m7_release_integration.py\n',
):
    if marker not in text:
        text = text.replace(
            '          tests/test_shortcut_launch_repair_r1.py\n',
            '          tests/test_shortcut_launch_repair_r1.py\n' + marker,
        )
if "tests.test_windows_first_run_finance_center_r74" not in text:
    text = text.replace(
        "            tests.test_shortcut_launch_repair_r1 \\\n",
        "            tests.test_shortcut_launch_repair_r1 \\\n"
        "            tests.test_windows_first_run_finance_center_r74 \\\n"
        "            tests.test_plateau_m7_release_integration \\\n",
    )
    text = text.replace(
        "            tests.test_shortcut_launch_repair_r1 `\n",
        "            tests.test_shortcut_launch_repair_r1 `\n"
        "            tests.test_windows_first_run_finance_center_r74 `\n"
        "            tests.test_plateau_m7_release_integration `\n",
    )
workflow.write_text(text, encoding="utf-8")

overlay_path = ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_SHORTCUT_LAUNCH_REPAIR_R1.json"
overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
manifest_paths = [
    ".github/workflows/shortcut-launch-repair-r1.yml",
    "docs/evidence/SHORTCUT_LAUNCH_REPAIR_R1_DEFECT_REGISTER.json",
    "docs/evidence/SHORTCUT_LAUNCH_REPAIR_R1_RTM.json",
    "scripts/windows/install_home_local.ps1",
    "scripts/windows/one_click_home_local.ps1",
    "tests/integration_manifest_support_m8.py",
    "tests/test_plateau_m7_release_integration.py",
    "tests/test_shortcut_launch_repair_r1.py",
    "tests/test_windows_first_run_finance_center_r74.py",
    "tests/test_windows_one_click_installer_r1.py",
    "tests/test_wbr2_m5_closure.py",
    "tests/test_wbr2_m5_closure_corrective_r2.py",
]
overlay["entries"] = []
for relative in manifest_paths:
    payload = (ROOT / relative).read_bytes()
    overlay["entries"].append(
        [relative, hashlib.sha256(payload).hexdigest(), len(payload)]
    )
overlay_path.write_text(
    json.dumps(overlay, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
