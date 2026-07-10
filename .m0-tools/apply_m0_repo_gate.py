#!/usr/bin/env python3
"""Prepare the M0 fail-closed attestation patch in an exact Quantum checkout.

This script intentionally refuses to run unless HEAD descends from the audited canonical commit.
It modifies the working tree only. It does not commit, push, merge, or reset anything.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

EXPECTED_HEAD = "1edf62167253e56c1e7f81fd2d6911d4b599720a"
ROOT = Path.cwd()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def replace(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    newline = "\r\n" if b"\r\n" in raw else "\n"
    normalized = text.replace("\r\n", "\n")
    if old not in normalized:
        raise RuntimeError(f"expected patch anchor missing: {relative}: {old[:100]!r}")
    updated = normalized.replace(old, new)
    payload = updated.replace("\n", newline).encode("utf-8")
    if bom:
        payload = b"\xef\xbb\xbf" + payload
    path.write_bytes(payload)


def main() -> None:
    root = Path(git("rev-parse", "--show-toplevel"))
    global ROOT
    ROOT = root
    head = git("rev-parse", "HEAD")
    subprocess.check_call(["git", "merge-base", "--is-ancestor", EXPECTED_HEAD, head], cwd=ROOT)

    replace(
        "scripts/windows/build_local_production.ps1",
        '-PackageRoot "%~dp0" -AuthorityAttested -SchemaReviewed',
        '-PackageRoot "%~dp0"',
    )
    replace(
        "scripts/windows/build_local_production.ps1",
        'import_source.ps1" -AuthorityAttested -SchemaReviewed',
        'import_source.ps1"',
    )
    replace(
        "scripts/windows/build_local_production.ps1",
        "4. No AUTHORIZE or REVIEWED console input is required in the one-click launch path.",
        "4. Type AUTHORIZE to confirm lawful authority, then review the displayed schema and type REVIEWED.",
    )
    replace(
        "scripts/windows/build_local_production.ps1",
        "- The one-click launchers carry explicit local authority and schema-review attestations. Use them only for reports you are lawfully authorized to process and have selected for review.",
        "- Launchers never attest on your behalf. Processing continues only after explicit AUTHORIZE and REVIEWED confirmations.",
    )
    replace(
        "scripts/windows/build_local_production.ps1",
        "- IMPORT_XLSX.cmd - authorized import only; no AUTHORIZE or REVIEWED console input is required.",
        "- IMPORT_XLSX.cmd - import with explicit AUTHORIZE and REVIEWED confirmations.",
    )
    replace(
        "scripts/windows/install_home_local.ps1",
        'import_source.ps1" -AuthorityAttested -SchemaReviewed',
        'import_source.ps1"',
    )
    replace(
        "scripts/windows/install_home_local.ps1",
        '-InstalledRoot "%~dp0" -SkipInstall -AuthorityAttested -SchemaReviewed',
        '-InstalledRoot "%~dp0" -SkipInstall',
    )
    replace(
        "scripts/windows/one_click_home_local.ps1",
        '''if ($NonInteractive -or ($AuthorityAttested -and $SchemaReviewed)) {
    $importArguments["NonInteractive"] = $true
}''',
        '''if ($NonInteractive) {
    if (-not $AuthorityAttested -or -not $SchemaReviewed) {
        throw "Non-interactive mode requires explicit AuthorityAttested and SchemaReviewed switches."
    }
    $importArguments["NonInteractive"] = $true
}''',
    )
    replace(
        "scripts/windows/one_click_home_local.ps1",
        '''if ($AuthorityAttested -and $SchemaReviewed) {
    Write-Host "One-click authorization is active. No AUTHORIZE or REVIEWED console input is required." -ForegroundColor Green
}
else {
    Write-Host "Manual authorization confirmations are enabled for this advanced launch mode." -ForegroundColor Yellow
}''',
        '''if ($NonInteractive) {
    Write-Host "Explicit non-interactive attestations were supplied by the invoking operator." -ForegroundColor Green
}
else {
    Write-Host "Quantum will require AUTHORIZE and REVIEWED confirmations; launchers never attest on your behalf." -ForegroundColor Yellow
}''',
    )
    replace(
        "src/quantum/application/local_app.py",
        '''        "-Output",
        str(output_path),
        "-NonInteractive",
        "-AuthorityAttested",
        "-SchemaReviewed",
    ]''',
        '''        "-Output",
        str(output_path),
    ]''',
    )
    replace(
        "src/quantum/application/local_app.py",
        '''    completed = subprocess.run(
        command,
        cwd=str(root),
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    row.stdout = completed.stdout or ""
    row.stderr = completed.stderr or ""''',
        '''    completed = subprocess.run(
        command,
        cwd=str(root),
        text=True,
        capture_output=False,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )
    row.stdout = "Interactive authorization and schema review were executed in the Quantum console."
    row.stderr = ""''',
    )

    path = ROOT / "config/home-local.template.json"
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    for key in payload["attestations"]:
        payload["attestations"][key] = False
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    replace(
        "scripts/windows/configure_home_local.ps1",
        '''        source_authority_verified = $true
        report_period_verified = $true
        control_totals_verified = $true
        direct_identifiers_absent_or_approved = $true
        malware_scan_clean = $true''',
        '''        source_authority_verified = $false
        report_period_verified = $false
        control_totals_verified = $false
        direct_identifiers_absent_or_approved = $false
        malware_scan_clean = $false''',
    )
    replace(
        "src/quantum/pilot/import_xlsx_source.ps1",
        '''        [Parameter(Mandatory = $true)][string]$MalwareEvidenceSha256
    )
    $raw = Get-Content -LiteralPath $SourceConfig -Raw -Encoding UTF8 | ConvertFrom-Json
    $raw.malware_scan_evidence_sha256 = $MalwareEvidenceSha256
    return $raw''',
        '''        [Parameter(Mandatory = $true)][string]$MalwareEvidenceSha256,
        [Parameter(Mandatory = $true)][string]$MalwareScanOutcome
    )
    $raw = Get-Content -LiteralPath $SourceConfig -Raw -Encoding UTF8 | ConvertFrom-Json
    $raw.malware_scan_evidence_sha256 = $MalwareEvidenceSha256
    $raw | Add-Member -NotePropertyName malware_scan_outcome -NotePropertyValue $MalwareScanOutcome -Force
    return $raw''',
    )
    replace(
        "src/quantum/pilot/import_xlsx_source.ps1",
        "    $runtimeConfigObject = New-RuntimeConfig -SourceConfig $Config -MalwareEvidenceSha256 ([string]$scanReceipt.evidence_sha256)",
        '''    $runtimeConfigObject = New-RuntimeConfig `
        -SourceConfig $Config `
        -MalwareEvidenceSha256 ([string]$scanReceipt.evidence_sha256) `
        -MalwareScanOutcome ([string]$scanReceipt.receipt.outcome)''',
    )
    replace(
        "src/quantum/pilot/import_xlsx_source.ps1",
        '''    Write-Host "Headers: $(@($schema.headers) -join ' | ')"
    Write-Host "File SHA-256: $reviewedFileHash"
    Confirm-Literal -Expected "REVIEWED" -Prompt "Review the displayed schema and type REVIEWED to continue" -AlreadyAttested ([bool]$SchemaReviewed)''',
        '''    Write-Host "Headers: $(@($schema.headers) -join ' | ')"
    Write-Host "Configured reporting period: $($runtimeConfigObject.reporting_period_start) through $($runtimeConfigObject.reporting_period_end)"
    Write-Host "File SHA-256: $reviewedFileHash"
    Confirm-Literal -Expected "REVIEWED" -Prompt "Review the displayed schema and reporting period, then type REVIEWED to continue" -AlreadyAttested ([bool]$SchemaReviewed)''',
    )
    replace(
        "src/quantum/pilot/windows_runner.py",
        "            config = apply_discovered_schema(config, candidate)\n        else:",
        "            config = apply_discovered_schema(config, candidate)\n            config[\"schema_reviewed\"] = True\n        else:",
    )
    replace(
        "src/quantum/pilot/local_runner.py",
        "    DatasetAdmissionState,\n    DatasetControlEvidence,",
        "    AdmissionError,\n    DatasetAdmissionState,\n    DatasetControlEvidence,",
    )
    replace(
        "src/quantum/pilot/local_runner.py",
        '''    if set(attestations) != _REQUIRED_ATTESTATIONS or any(
        attestations[name] is not True for name in _REQUIRED_ATTESTATIONS
    ):
        raise LocalPilotError("LOCAL_PILOT_ATTESTATIONS_INCOMPLETE")''',
        '''    if set(attestations) != _REQUIRED_ATTESTATIONS or any(
        not isinstance(attestations[name], bool) for name in _REQUIRED_ATTESTATIONS
    ):
        raise LocalPilotError("LOCAL_PILOT_ATTESTATIONS_INVALID")''',
    )
    replace(
        "src/quantum/pilot/local_runner.py",
        '''        source_authority_verified=True,
        report_period_verified=True,
        control_totals_verified=True,
        direct_identifiers_absent_or_approved=True,
        malware_scan_clean=True,''',
        '''        source_authority_verified=(config.get("lawful_authority_attested") is True),
        report_period_verified=(config.get("schema_reviewed") is True),
        control_totals_verified=(
            declaration.control_totals_sha256 is None
            and config.get("execution_mode", "FULL") == "ADMISSION_ONLY"
        ) or (
            declaration.control_totals_sha256 is not None
            and attestations["control_totals_verified"] is True
        ),
        direct_identifiers_absent_or_approved=(inspection.prohibited_header_count == 0),
        malware_scan_clean=(config.get("malware_scan_outcome") == "CLEAN"),''',
    )
    replace(
        "src/quantum/pilot/local_runner.py",
        '''    record = registry.admit(
        tenant=tenant,
        dataset_id=dataset_id,
        dataset_control_evidence=dataset_evidence,
        storage_evidence=storage_evidence,
        admitted_at=now + timedelta(seconds=3),
    )
    if record.state is not DatasetAdmissionState.ADMITTED:''',
        '''    try:
        record = registry.admit(
            tenant=tenant,
            dataset_id=dataset_id,
            dataset_control_evidence=dataset_evidence,
            storage_evidence=storage_evidence,
            admitted_at=now + timedelta(seconds=3),
        )
    except AdmissionError as exc:
        report = _base_report(
            dataset_id=dataset_id, receipt=receipt, record=record,
            policy=policy, zone_state="QUARANTINED",
        )
        report["status"] = "ADMISSION_BLOCKED"
        report["reason"] = str(exc)
        report["limitations"] = ["CALCULATION_NOT_EXECUTED", "CONTROL_EVIDENCE_INCOMPLETE"]
        return report
    if record.state is not DatasetAdmissionState.ADMITTED:''',
    )
    replace(
        "src/quantum/pilot/local_runner.py",
        '''            "FINANCE_CONFIGURATION_REQUIRED",
            "DURABLE_AUTHENTICATION_NOT_INCLUDED",''',
        '''            "FINANCE_CONFIGURATION_REQUIRED",
            *(["CONTROL_TOTALS_NOT_PROVIDED"] if declaration.control_totals_sha256 is None else []),
            "DURABLE_AUTHENTICATION_NOT_INCLUDED",''',
    )

    replace(
        "tests/test_windows_one_click_installer_r1.py",
        '''        self.assertIn(
            'if ($NonInteractive -or ($AuthorityAttested -and $SchemaReviewed))',
            script,
        )
        self.assertIn('if ($AuthorityAttested) { $importArguments["AuthorityAttested"] = $true }', script)
        self.assertIn('if ($SchemaReviewed) { $importArguments["SchemaReviewed"] = $true }', script)
        self.assertIn('if ($SkipDefenderScan) { $importArguments["SkipDefenderScan"] = $true }', script)
        self.assertIn('No AUTHORIZE or REVIEWED console input is required.', script)''',
        '''        self.assertIn('if ($NonInteractive)', script)
        self.assertIn('-not $AuthorityAttested -or -not $SchemaReviewed', script)
        self.assertIn('if ($AuthorityAttested) { $importArguments["AuthorityAttested"] = $true }', script)
        self.assertIn('if ($SchemaReviewed) { $importArguments["SchemaReviewed"] = $true }', script)
        self.assertIn('if ($SkipDefenderScan) { $importArguments["SkipDefenderScan"] = $true }', script)
        self.assertIn('Quantum will require AUTHORIZE and REVIEWED confirmations', script)''',
    )
    replace(
        "tests/test_windows_one_click_installer_r1.py",
        '''        self.assertIn('-InstalledRoot "%~dp0" -SkipInstall -AuthorityAttested -SchemaReviewed', script)
        self.assertIn('import_source.ps1" -AuthorityAttested -SchemaReviewed', script)''',
        '''        self.assertNotIn('-InstalledRoot "%~dp0" -SkipInstall -AuthorityAttested -SchemaReviewed', script)
        self.assertNotIn('import_source.ps1" -AuthorityAttested -SchemaReviewed', script)''',
    )
    replace(
        "tests/test_windows_source_package_launchers_r1.py",
        '''        self.assertIn(
            '-PackageRoot "%~dp0" -AuthorityAttested -SchemaReviewed',
            BUILDER,
        )''',
        '''        self.assertNotIn(
            '-PackageRoot "%~dp0" -AuthorityAttested -SchemaReviewed',
            BUILDER,
        )
        self.assertIn('Type AUTHORIZE', BUILDER)''',
    )
    replace(
        "tests/test_windows_source_package_launchers_r1.py",
        '''        self.assertIn(
            'import_source.ps1" -AuthorityAttested -SchemaReviewed',
            BUILDER,
        )''',
        '''        self.assertNotIn(
            'import_source.ps1" -AuthorityAttested -SchemaReviewed',
            BUILDER,
        )
        self.assertIn('type REVIEWED', BUILDER)''',
    )
    replace(
        "tests/test_windows_source_package_launchers_r1.py",
        '''        self.assertIn(
            'No AUTHORIZE or REVIEWED console input is required',
            BUILDER,
        )
        self.assertNotIn('Type AUTHORIZE only', BUILDER)
        self.assertNotIn('Type REVIEWED only', BUILDER)''',
        '''        self.assertNotIn(
            'No AUTHORIZE or REVIEWED console input is required',
            BUILDER,
        )
        self.assertIn('Type AUTHORIZE', BUILDER)
        self.assertIn('type REVIEWED', BUILDER)
        self.assertIn('Launchers never attest on your behalf', BUILDER)''',
    )

    print("M0 transparent patch prepared in working tree.")


if __name__ == "__main__":
    main()
