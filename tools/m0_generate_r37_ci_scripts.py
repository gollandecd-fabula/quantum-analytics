#!/usr/bin/env python3
"""Generate corrected R37 PowerShell CI scripts from the exact current workflows."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SELF = "tools/m0_generate_r37_ci_scripts.py"
TEMP_WORKFLOW = ".github/workflows/m0-generate-r37-ci-scripts.yml"
EXPORT_WORKFLOW = ".github/workflows/m0-export-current-workflows.yml"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def extract_pwsh_runs(text: str, expected_count: int) -> str:
    lines = text.splitlines()
    blocks: list[tuple[str, str]] = []
    current_name = "unnamed"
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.match(r"^      - name: (.+)$", line)
        if match:
            current_name = match.group(1)
        if line == "        run: |":
            index += 1
            content: list[str] = []
            while index < len(lines):
                candidate = lines[index]
                if candidate and len(candidate) - len(candidate.lstrip(" ")) <= 8:
                    break
                if candidate.startswith("          "):
                    content.append(candidate[10:])
                elif not candidate:
                    content.append("")
                else:
                    raise RuntimeError(f"Unexpected run-block indentation: {candidate!r}")
                index += 1
            block = "\n".join(content).rstrip()
            block = block.replace(
                "${{ github.event.pull_request.head.sha || github.sha }}",
                "$env:TARGET_SHA",
            )
            blocks.append((current_name, block))
            continue
        index += 1
    if len(blocks) != expected_count:
        raise RuntimeError(f"Expected {expected_count} PowerShell blocks, got {len(blocks)}")
    header = (
        "[CmdletBinding()]\nparam()\n"
        "Set-StrictMode -Version Latest\n"
        "$ErrorActionPreference = \"Stop\"\n\n"
    )
    return header + "\n\n".join(
        f"# === {name} ===\n{block}" for name, block in blocks
    ) + "\n"


def production_script() -> str:
    path = ROOT / ".github/workflows/windows-local-production.yml"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''          if ([string]$configured.execution_mode -ne "ADMISSION_ONLY") {
            throw "Configurator did not create ADMISSION_ONLY config."
          }

          $syntheticXlsx''',
        '''          if ([string]$configured.execution_mode -ne "ADMISSION_ONLY") {
            throw "Configurator did not create ADMISSION_ONLY config."
          }
          $configured.attestations.malware_scan_clean = $true
          $configuredJson = $configured | ConvertTo-Json -Depth 16
          [IO.File]::WriteAllText(
            $configPath,
            $configuredJson,
            ([Text.UTF8Encoding]::new($false))
          )

          $syntheticXlsx''',
        "production equivalent-scan attestation",
    )
    text = replace_once(
        text,
        '''            -PackageRoot $extractRoot `
            -TargetRoot $oneClickInstall `
            -File $syntheticXlsx `''',
        '''            -PackageRoot $extractRoot `
            -TargetRoot $oneClickInstall `
            -Config $configPath `
            -File $syntheticXlsx `''',
        "production one-click config binding",
    )
    script = extract_pwsh_runs(text, expected_count=8)
    for marker in (
        "$configured.attestations.malware_scan_clean = $true",
        "-Config $configPath `",
        "ADMISSION_COMPLETE",
        "Tampered package was accepted",
    ):
        if marker not in script:
            raise RuntimeError(f"Production script marker missing: {marker}")
    return script


def native_script() -> str:
    path = ROOT / ".github/workflows/build-one-button-redteam-r3.yml"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''            Write-Host "No dates, AUTHORIZE or REVIEWED input is required." -ForegroundColor Green;if(-not$InstallOnly-and-not$File){Write-Host "Select only the XLSX file when Windows asks." -ForegroundColor Cyan};Write-Host "Microsoft Defender scanning remains enabled." -ForegroundColor Green
            $a=@{PackageRoot=$package;TargetRoot=$TargetRoot;ReportingPeriodStart="2022-01-01";ReportingPeriodEnd="2035-12-31";RetentionDeadline="2036-12-31";SourceInternalId="wb-auto-local";AuthorityAttested=$true;SchemaReviewed=$true}
            if($File){$a.File=$File;$a.NonInteractive=$true};if($InstallOnly){$a.InstallOnly=$true};if($NoOpenResult){$a.NoOpenResult=$true};if($SkipDefenderScanForCi){$a.SkipDefenderScan=$true};& $launch @a''',
        '''            Write-Host "Quantum requires explicit AUTHORIZE and REVIEWED confirmations during normal use." -ForegroundColor Yellow;if(-not$InstallOnly-and-not$File){Write-Host "Select the authorized XLSX file when Windows asks." -ForegroundColor Cyan};Write-Host "Microsoft Defender scanning remains enabled unless an explicitly attested CI-equivalent scan is supplied." -ForegroundColor Green
            if($InstallOnly){& $launch -PackageRoot $package -TargetRoot $TargetRoot -InstallOnly}
            elseif($File-and$SkipDefenderScanForCi){
              & $launch -PackageRoot $package -TargetRoot $TargetRoot -InstallOnly
              $cfg=Join-Path $TargetRoot "config\\default-home-local.json";$configure=Join-Path $TargetRoot "scripts\\configure_home_local.ps1"
              & $configure -ConfigPath $cfg -ReportingPeriodStart "2022-01-01" -ReportingPeriodEnd "2035-12-31" -RetentionDeadline "2036-12-31" -SourceInternalId "wb-ci-explicit-scan" -NonInteractive
              $c=Get-Content $cfg -Raw -Encoding UTF8|ConvertFrom-Json;$c.attestations.malware_scan_clean=$true;[IO.File]::WriteAllText($cfg,($c|ConvertTo-Json -Depth 16),[Text.UTF8Encoding]::new($false))
              $installed=Join-Path $TargetRoot "scripts\\one_click_home_local.ps1";$a=@{InstalledRoot=$TargetRoot;SkipInstall=$true;Config=$cfg;File=$File;NonInteractive=$true;AuthorityAttested=$true;SchemaReviewed=$true;SkipDefenderScan=$true};if($NoOpenResult){$a.NoOpenResult=$true};& $installed @a
            }
            else{$a=@{PackageRoot=$package;TargetRoot=$TargetRoot;ReportingPeriodStart="2022-01-01";ReportingPeriodEnd="2035-12-31";RetentionDeadline="2036-12-31";SourceInternalId="wb-interactive-local"};if($File){$a.File=$File};if($NoOpenResult){$a.NoOpenResult=$true};& $launch @a}''',
        "native operator-attestation boundary",
    )
    text = text.replace(
        '"Extract ZIP, double-click START_QUANTUM.cmd, then select the XLSX file. Defender remains enabled. Marketplace writes remain disabled."',
        '"Extract ZIP and double-click START_QUANTUM.cmd. Select the authorized XLSX file, then type AUTHORIZE and REVIEWED when prompted. Defender remains enabled unless an explicitly attested equivalent scan is supplied. Marketplace writes remain disabled."',
    )
    text = replace_once(
        text,
        '''          $cfg=Get-Content "$full\\config\\default-home-local.json" -Raw|ConvertFrom-Json;if($cfg.reporting_period_start-ne"2022-01-01"-or$cfg.reporting_period_end-ne"2035-12-31"-or$cfg.retention_deadline-ne"2036-12-31T00:00:00Z"){throw "Automatic config mismatch."}''',
        '''          $cfg=Get-Content "$full\\config\\default-home-local.json" -Raw|ConvertFrom-Json;if($cfg.reporting_period_start-ne"2022-01-01"-or$cfg.reporting_period_end-ne"2035-12-31"-or$cfg.retention_deadline-ne"2036-12-31T00:00:00Z"){throw "CI config mismatch."};if($cfg.attestations.malware_scan_clean-ne$true){throw "Explicit equivalent-scan attestation missing."}''',
        "native CI config evidence",
    )
    text = replace_once(
        text,
        '''          if($startText-notmatch'-AuthorityAttested\\s+-SchemaReviewed'){throw "Installed START_QUANTUM.cmd did not propagate attestations."}
          if($importText-notmatch'-AuthorityAttested\\s+-SchemaReviewed'){throw "Installed IMPORT_XLSX.cmd did not propagate attestations."}''',
        '''          if($startText-match'-AuthorityAttested|-SchemaReviewed'){throw "Installed START_QUANTUM.cmd attested for the operator."}
          if($importText-match'-AuthorityAttested|-SchemaReviewed'){throw "Installed IMPORT_XLSX.cmd attested for the operator."}''',
        "native installed launcher boundary",
    )
    text = replace_once(
        text,
        '''          powershell.exe -NonInteractive -NoProfile -ExecutionPolicy Bypass -File "$full\\scripts\\one_click_home_local.ps1" -InstalledRoot $full -SkipInstall -File $xlsx -AuthorityAttested -SchemaReviewed -NoOpenResult -SkipDefenderScan 2>&1|Tee-Object native-gui-path.log''',
        '''          powershell.exe -NonInteractive -NoProfile -ExecutionPolicy Bypass -File "$full\\scripts\\one_click_home_local.ps1" -InstalledRoot $full -SkipInstall -Config "$full\\config\\default-home-local.json" -File $xlsx -NonInteractive -AuthorityAttested -SchemaReviewed -NoOpenResult -SkipDefenderScan 2>&1|Tee-Object native-gui-path.log''',
        "native explicit CI invocation",
    )
    text = text.replace(
        'automatic_dates_and_attestations="PASS"',
        'operator_attestation_boundary="PASS";explicit_ci_equivalent_scan="PASS"',
    )
    script = extract_pwsh_runs(text, expected_count=5)
    for marker in (
        "Quantum requires explicit AUTHORIZE and REVIEWED",
        "malware_scan_clean=$true",
        "Installed START_QUANTUM.cmd attested for the operator",
        'operator_attestation_boundary="PASS"',
    ):
        if marker not in script:
            raise RuntimeError(f"Native script marker missing: {marker}")
    if "No dates, AUTHORIZE or REVIEWED input is required" in script:
        raise RuntimeError("Native script retained automatic-attestation claim")
    return script


def main() -> None:
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    if branch != "automation/m0-reconciliation-v4":
        raise SystemExit(f"REFUSED: unexpected branch {branch}")
    output = ROOT / "scripts/ci"
    output.mkdir(parents=True, exist_ok=True)
    (output / "windows_local_production_r37.ps1").write_text(
        production_script(), encoding="utf-8"
    )
    (output / "native_one_button_r37.ps1").write_text(
        native_script(), encoding="utf-8"
    )
    subprocess.run(
        ["git", "rm", "-f", SELF, TEMP_WORKFLOW, EXPORT_WORKFLOW],
        cwd=ROOT,
        check=True,
    )
    print("M0_R37_CI_SCRIPTS_READY")


if __name__ == "__main__":
    main()
