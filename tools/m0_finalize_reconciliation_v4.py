#!/usr/bin/env python3
"""Finalize the M0 fail-closed patch inside the isolated candidate branch.

The script uses exact textual anchors, removes itself and its temporary workflow,
creates immutable manifest overlay R34 from the resulting working tree, and
never updates refs or merges branches.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = "1edf62167253e56c1e7f81fd2d6911d4b599720a"
WORKFLOW = ".github/workflows/m0-finalize-reconciliation-v4.yml"
SELF = "tools/m0_finalize_reconciliation_v4.py"
R33 = "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R33.json"
R34 = "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R34.json"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def replace(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"M0 anchor mismatch for {relative}: expected exactly one occurrence, got {count}: {old[:120]!r}"
        )
    updated = text.replace(old, new, 1)
    newline = "\r\n" if b"\r\n" in raw else "\n"
    payload = updated.replace("\n", newline).encode("utf-8")
    if bom:
        payload = b"\xef\xbb\xbf" + payload
    path.write_bytes(payload)


def sha256_entry(relative: str) -> list[object]:
    payload = (ROOT / relative).read_bytes()
    return [relative, hashlib.sha256(payload).hexdigest(), len(payload)]


def main() -> None:
    if git("rev-parse", "--show-toplevel") != str(ROOT):
        raise SystemExit("REFUSED: unexpected repository root")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", CANONICAL, "HEAD"],
        cwd=ROOT,
        check=True,
    )
    branch = git("branch", "--show-current")
    if branch != "automation/m0-reconciliation-v4":
        raise SystemExit(f"REFUSED: unexpected branch {branch}")

    replace(
        "src/quantum/pilot/windows_runner.py",
        '            config = apply_discovered_schema(config, candidate)\n        else:',
        '            config = apply_discovered_schema(config, candidate)\n            config["schema_reviewed"] = True\n        else:',
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
        report_period_verified=(
            config.get("schema_reviewed") is True
            or attestations["report_period_verified"] is True
        ),
        control_totals_verified=(
            declaration.control_totals_sha256 is None
            or attestations["control_totals_verified"] is True
        ),
        direct_identifiers_absent_or_approved=(inspection.prohibited_header_count == 0),
        malware_scan_clean=(
            config.get("malware_scan_outcome") == "CLEAN"
            or (
                config.get("malware_scan_outcome") is None
                and attestations["malware_scan_clean"] is True
            )
        ),''',
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
        '''    def test_one_click_attestations_are_explicit_and_defender_remains_enabled(self):
        script = self.one_click
        self.assertIn(
            'if ($NonInteractive -or ($AuthorityAttested -and $SchemaReviewed))',
            script,
        )
        self.assertIn('if ($AuthorityAttested) { $importArguments["AuthorityAttested"] = $true }', script)
        self.assertIn('if ($SchemaReviewed) { $importArguments["SchemaReviewed"] = $true }', script)
        self.assertIn('if ($SkipDefenderScan) { $importArguments["SkipDefenderScan"] = $true }', script)
        self.assertIn('No AUTHORIZE or REVIEWED console input is required.', script)
        self.assertNotIn('SkipDefenderScan = $true', script)
        self.assertNotIn('finance_request =', script)''',
        '''    def test_one_click_attestations_are_explicit_and_defender_remains_enabled(self):
        script = self.one_click
        self.assertNotIn(
            'if ($NonInteractive -or ($AuthorityAttested -and $SchemaReviewed))',
            script,
        )
        self.assertIn('if ($NonInteractive)', script)
        self.assertIn('-not $AuthorityAttested -or -not $SchemaReviewed', script)
        self.assertIn('if ($AuthorityAttested) { $importArguments["AuthorityAttested"] = $true }', script)
        self.assertIn('if ($SchemaReviewed) { $importArguments["SchemaReviewed"] = $true }', script)
        self.assertIn('if ($SkipDefenderScan) { $importArguments["SkipDefenderScan"] = $true }', script)
        self.assertIn('launchers never attest on your behalf', script)
        self.assertNotIn('SkipDefenderScan = $true', script)
        self.assertNotIn('finance_request =', script)''',
    )
    replace(
        "tests/test_windows_one_click_installer_r1.py",
        '''        self.assertIn('-InstalledRoot "%~dp0" -SkipInstall -AuthorityAttested -SchemaReviewed', script)
        self.assertIn('import_source.ps1" -AuthorityAttested -SchemaReviewed', script)''',
        '''        self.assertIn('-InstalledRoot "%~dp0" -SkipInstall', script)
        self.assertNotIn('-InstalledRoot "%~dp0" -SkipInstall -AuthorityAttested', script)
        self.assertNotIn('import_source.ps1" -AuthorityAttested', script)''',
    )
    replace(
        "tests/test_windows_source_package_launchers_r1.py",
        '''    def test_source_start_launcher_propagates_attestations(self):
        self.assertIn(
            '-PackageRoot "%~dp0" -AuthorityAttested -SchemaReviewed',
            BUILDER,
        )

    def test_source_import_launcher_propagates_attestations(self):
        self.assertIn(
            'import_source.ps1" -AuthorityAttested -SchemaReviewed',
            BUILDER,
        )

    def test_source_readme_matches_one_click_behavior(self):
        self.assertIn(
            'No AUTHORIZE or REVIEWED console input is required',
            BUILDER,
        )
        self.assertNotIn('Type AUTHORIZE only', BUILDER)
        self.assertNotIn('Type REVIEWED only', BUILDER)
        self.assertIn('Microsoft Defender scanning remains enabled', BUILDER)
        self.assertIn('Marketplace writes', BUILDER)''',
        '''    def test_source_start_launcher_never_attests_for_operator(self):
        self.assertIn('-PackageRoot "%~dp0"', BUILDER)
        self.assertNotIn(
            '-PackageRoot "%~dp0" -AuthorityAttested -SchemaReviewed',
            BUILDER,
        )

    def test_source_import_launcher_never_attests_for_operator(self):
        self.assertNotIn(
            'import_source.ps1" -AuthorityAttested -SchemaReviewed',
            BUILDER,
        )

    def test_source_readme_matches_fail_closed_one_click_behavior(self):
        self.assertNotIn(
            'No AUTHORIZE or REVIEWED console input is required',
            BUILDER,
        )
        self.assertIn('Type AUTHORIZE', BUILDER)
        self.assertIn('type REVIEWED', BUILDER)
        self.assertIn('Launchers never attest on your behalf', BUILDER)
        self.assertIn('Microsoft Defender scanning remains enabled', BUILDER)
        self.assertIn('Marketplace writes', BUILDER)''',
    )

    replace(
        "tests/integration_manifest_support.py",
        '''FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{n}.json"
    for n in range(1, 34)
)''',
        '''FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{n}.json"
    for n in range(1, 35)
)''',
    )

    subprocess.run(["git", "rm", "-f", SELF, WORKFLOW], cwd=ROOT, check=True)

    changed = subprocess.check_output(
        ["git", "diff", "--name-only", CANONICAL, "--"],
        cwd=ROOT,
        text=True,
    ).splitlines()
    control_prefix = "docs/evidence/ARTIFACT_MANIFEST"
    entries: list[list[object]] = []
    remove_paths: list[str] = []
    for relative in sorted(set(changed)):
        if relative.startswith(control_prefix):
            continue
        path = ROOT / relative
        if path.is_file():
            entries.append(sha256_entry(relative))
        elif not path.exists():
            remove_paths.append(relative)

    expected = {
        "config/home-local.template.json",
        "scripts/windows/build_local_production.ps1",
        "scripts/windows/configure_home_local.ps1",
        "scripts/windows/install_home_local.ps1",
        "scripts/windows/one_click_home_local.ps1",
        "src/quantum/application/local_app.py",
        "src/quantum/pilot/import_xlsx_source.ps1",
        "src/quantum/pilot/local_runner.py",
        "src/quantum/pilot/windows_runner.py",
        "tests/integration_manifest_support.py",
        "tests/test_m0_attestation_redteam.py",
        "tests/test_windows_one_click_installer_r1.py",
        "tests/test_windows_source_package_launchers_r1.py",
    }
    actual = {str(row[0]) for row in entries}
    if actual != expected:
        raise RuntimeError(
            "M0 changed-path set mismatch: "
            f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
        )
    if remove_paths:
        raise RuntimeError(f"Unexpected product removals: {remove_paths}")

    base_blob = git("hash-object", R33)
    overlay = {
        "base_pilot_integration_r33_overlay_git_blob_sha": base_blob,
        "entries": entries,
        "hash_encoding": "sha256-hex",
        "overlay_version": 34,
        "reason": (
            "MILESTONE 0 reconciliation: remove automatic operator attestations, "
            "derive dataset control evidence from observed facts or explicit legacy "
            "attestations only when no scan outcome exists, bind malware outcome and "
            "reviewed reporting period, and preserve fail-closed HOME_LOCAL admission"
        ),
        "remove_paths": [],
    }
    (ROOT / R34).write_text(
        json.dumps(overlay, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
    print(json.dumps({"status": "M0_FINALIZED", "entries": entries}, ensure_ascii=False))


if __name__ == "__main__":
    main()
