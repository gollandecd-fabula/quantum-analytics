#!/usr/bin/env python3
"""Apply M0 recovery after the M1 baseline invalidated the production gate."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = "tools/m0_recover_after_m1.py"
WORKFLOW = ".github/workflows/m0-recover-after-m1.yml"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if old not in text:
        if new in text:
            return
        raise SystemExit(f"ANCHOR_MISSING:{path}")
    if text.count(old) != 1:
        raise SystemExit(f"ANCHOR_NOT_UNIQUE:{path}:{text.count(old)}")
    write(path, text.replace(old, new, 1))


def append_exit_zero(path: str) -> None:
    text = read(path).rstrip() + "\n"
    marker = "# Explicit script contract: successful completion resets the process exit code.\nexit 0\n"
    if text.endswith(marker):
        return
    write(path, text + "\n" + marker)


def sha256_entry(path: str) -> list[object]:
    data = (ROOT / path).read_bytes()
    return [path, hashlib.sha256(data).hexdigest(), len(data)]


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def main() -> None:
    one_click = "scripts/windows/one_click_home_local.ps1"
    old = '''if (-not [string]::IsNullOrWhiteSpace($Config)) {
    $Config = Resolve-FullPath -Path $Config -MustExist
    if (-not (Test-ReadyConfig -Path $Config)) {
        throw "The supplied configuration is not ready: $Config"
    }
}
else {
    $Config = Find-ReadyConfig -Root $TargetRoot
    if (-not $Config) {
        Write-Host "[3/4] Creating first-run configuration..." -ForegroundColor Cyan
        $Config = Invoke-ConfigurationWizard -Root $TargetRoot -Configurator $configurator
    }
    else {
        Write-Host "[3/4] Ready configuration found: $Config" -ForegroundColor Green
    }
}
'''
    new = '''if (-not [string]::IsNullOrWhiteSpace($Config)) {
    $Config = Resolve-FullPath -Path $Config -MustExist
    if (-not (Test-ReadyConfig -Path $Config)) {
        throw "The supplied configuration is not ready: $Config"
    }

    $managedConfig = Join-Path $TargetRoot "config\\default-home-local.json"
    if (-not (Test-PathWithin -Child $Config -Parent $TargetRoot)) {
        $managedConfigDirectory = Split-Path -Parent $managedConfig
        New-Item -ItemType Directory -Path $managedConfigDirectory -Force | Out-Null
        if (Test-Path -LiteralPath $managedConfig -PathType Leaf) {
            $sourceHash = (Get-FileHash -LiteralPath $Config -Algorithm SHA256).Hash
            $managedHash = (Get-FileHash -LiteralPath $managedConfig -Algorithm SHA256).Hash
            if ($sourceHash -ne $managedHash) {
                throw "The supplied configuration conflicts with the existing managed configuration: $managedConfig"
            }
        }
        else {
            $temporaryConfig = Join-Path $managedConfigDirectory (".default-home-local.{0}.tmp" -f [guid]::NewGuid().ToString("N"))
            try {
                Copy-Item -LiteralPath $Config -Destination $temporaryConfig -Force
                if (-not (Test-ReadyConfig -Path $temporaryConfig)) {
                    throw "The copied configuration is not ready: $temporaryConfig"
                }
                Move-Item -LiteralPath $temporaryConfig -Destination $managedConfig -Force
            }
            finally {
                Remove-Item -LiteralPath $temporaryConfig -Force -ErrorAction SilentlyContinue
            }
        }
        $Config = Resolve-FullPath -Path $managedConfig -MustExist
        Write-Host "[3/4] Supplied configuration persisted inside HOME_LOCAL: $Config" -ForegroundColor Green
    }
}
else {
    $Config = Find-ReadyConfig -Root $TargetRoot
    if (-not $Config) {
        Write-Host "[3/4] Creating first-run configuration..." -ForegroundColor Cyan
        $Config = Invoke-ConfigurationWizard -Root $TargetRoot -Configurator $configurator
    }
    else {
        Write-Host "[3/4] Ready configuration found: $Config" -ForegroundColor Green
    }
}
'''
    replace_once(one_click, old, new)

    append_exit_zero("scripts/ci/windows_local_production_r37.ps1")
    append_exit_zero("scripts/ci/native_one_button_r37.ps1")

    test_path = "tests/test_m0_recovery_after_m1.py"
    test_text = '''from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class M0RecoveryAfterM1Tests(unittest.TestCase):
    def test_external_ready_config_is_persisted_fail_closed(self) -> None:
        text = (ROOT / "scripts/windows/one_click_home_local.ps1").read_text(encoding="utf-8")
        self.assertIn('Join-Path $TargetRoot "config\\\\default-home-local.json"', text)
        self.assertIn("The supplied configuration conflicts with the existing managed configuration", text)
        self.assertIn("Move-Item -LiteralPath $temporaryConfig -Destination $managedConfig -Force", text)
        self.assertIn("Supplied configuration persisted inside HOME_LOCAL", text)

    def test_versioned_gate_scripts_publish_explicit_exit_contract(self) -> None:
        for relative in (
            "scripts/ci/windows_local_production_r37.ps1",
            "scripts/ci/native_one_button_r37.ps1",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8").rstrip()
            self.assertTrue(text.endswith("exit 0"), relative)
            self.assertIn("Explicit script contract", text)

    def test_workflow_wrappers_never_overwrite_gate_status(self) -> None:
        for relative in (
            ".github/workflows/windows-local-production.yml",
            ".github/workflows/build-one-button-redteam-r3.yml",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("$gateExitCode = $LASTEXITCODE", text)
            self.assertIn("if ($gateExitCode -ne 0)", text)
            self.assertNotIn("          exit 0", text)


if __name__ == "__main__":
    unittest.main()
'''
    write(test_path, test_text)

    support_path = "tests/integration_manifest_support.py"
    support = read(support_path)
    old_range = "for n in range(1, 46)"
    new_range = "for n in range(1, 47)"
    if old_range in support:
        write(support_path, support.replace(old_range, new_range, 1))
    elif new_range not in support:
        raise SystemExit("MANIFEST_RANGE_UNEXPECTED")

    r45_path = "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R45.json"
    r46_path = "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R46.json"
    r45 = (ROOT / r45_path).read_bytes()
    changed = [
        ".github/workflows/build-one-button-redteam-r3.yml",
        ".github/workflows/windows-local-production.yml",
        "scripts/ci/native_one_button_r37.ps1",
        "scripts/ci/windows_local_production_r37.ps1",
        "scripts/windows/one_click_home_local.ps1",
        "tests/integration_manifest_support.py",
        test_path,
    ]
    overlay = {
        "base_pilot_integration_r45_overlay_git_blob_sha": git_blob_sha(r45),
        "entries": [sha256_entry(path) for path in changed],
        "hash_encoding": "sha256-hex",
        "overlay_version": 46,
        "reason": "M0 recovery after M1 Red Team: persist externally supplied ready config inside fresh HOME_LOCAL and prevent production/native workflow exit-status masking",
        "remove_paths": [],
    }
    write(r46_path, json.dumps(overlay, indent=2) + "\n")

    for temporary in (SELF, WORKFLOW):
        target = ROOT / temporary
        if target.exists():
            target.unlink()


if __name__ == "__main__":
    main()
