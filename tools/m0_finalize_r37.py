#!/usr/bin/env python3
"""Create immutable M0 overlay R37 for versioned Windows CI wrappers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
R36_BASE = "5cc1f51c3e33fb4c17af41d168895930dfb02867"
SELF = "tools/m0_finalize_r37.py"
TEMP_WORKFLOW = ".github/workflows/m0-finalize-r37.yml"
R36 = "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R36.json"
R37 = "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R37.json"
SUPPORT = "tests/integration_manifest_support.py"

EXPECTED = {
    ".github/workflows/build-one-button-redteam-r3.yml",
    ".github/workflows/windows-local-production.yml",
    "scripts/ci/native_one_button_r37.ps1",
    "scripts/ci/windows_local_production_r37.ps1",
    SUPPORT,
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def entry(relative: str) -> list[object]:
    payload = (ROOT / relative).read_bytes()
    return [relative, hashlib.sha256(payload).hexdigest(), len(payload)]


def update_manifest_support() -> None:
    path = ROOT / SUPPORT
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    old = '''FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{n}.json"
    for n in range(1, 37)
)'''
    new = '''FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{n}.json"
    for n in range(1, 38)
)'''
    if text.count(old) != 1:
        raise RuntimeError("R37 manifest-support anchor mismatch")
    updated = text.replace(old, new, 1)
    newline = "\r\n" if b"\r\n" in raw else "\n"
    payload = updated.replace("\n", newline).encode("utf-8")
    if bom:
        payload = b"\xef\xbb\xbf" + payload
    path.write_bytes(payload)


def assert_wrapper_contracts() -> None:
    production = (ROOT / ".github/workflows/windows-local-production.yml").read_text(encoding="utf-8")
    native = (ROOT / ".github/workflows/build-one-button-redteam-r3.yml").read_text(encoding="utf-8")
    production_script = (ROOT / "scripts/ci/windows_local_production_r37.ps1").read_text(encoding="utf-8")
    native_script = (ROOT / "scripts/ci/native_one_button_r37.ps1").read_text(encoding="utf-8")

    required = {
        "production wrapper": (
            production,
            [
                "name: Windows Local Production Repair",
                "scripts\\ci\\windows_local_production_r37.ps1",
                "TARGET_SHA:",
                "QuantumLocalProduction_HOME_LOCAL.zip",
            ],
        ),
        "native wrapper": (
            native,
            [
                "name: Quantum One Button R3 Native Red Team",
                "scripts\\ci\\native_one_button_r37.ps1",
                "TARGET_SHA:",
                "QUANTUM_ONE_BUTTON_REDTEAM_R3.zip",
            ],
        ),
        "production script": (
            production_script,
            [
                "$configured.attestations.malware_scan_clean = $true",
                "-Config $configPath `",
                "ADMISSION_COMPLETE",
                "Tampered package was accepted",
            ],
        ),
        "native script": (
            native_script,
            [
                "Quantum requires explicit AUTHORIZE and REVIEWED",
                "malware_scan_clean=$true",
                "Installed START_QUANTUM.cmd attested for the operator",
                'operator_attestation_boundary="PASS"',
            ],
        ),
    }
    for label, (content, markers) in required.items():
        for marker in markers:
            if marker not in content:
                raise RuntimeError(f"{label} missing marker: {marker}")
    if "No dates, AUTHORIZE or REVIEWED input is required" in native_script:
        raise RuntimeError("Native CI script retained automatic-attestation claim")


def main() -> None:
    if git("branch", "--show-current") != "automation/m0-reconciliation-v4":
        raise SystemExit("REFUSED: unexpected branch")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", R36_BASE, "HEAD"],
        cwd=ROOT,
        check=True,
    )
    assert_wrapper_contracts()
    update_manifest_support()
    subprocess.run(["git", "rm", "-f", SELF, TEMP_WORKFLOW], cwd=ROOT, check=True)

    changed = set(
        subprocess.check_output(
            ["git", "diff", "--name-only", R36_BASE, "--"],
            cwd=ROOT,
            text=True,
        ).splitlines()
    )
    product_changed = {
        path
        for path in changed
        if not path.startswith("docs/evidence/ARTIFACT_MANIFEST")
    }
    if product_changed != EXPECTED:
        raise RuntimeError(
            "Unexpected R37 scope: "
            f"missing={sorted(EXPECTED-product_changed)}, "
            f"unexpected={sorted(product_changed-EXPECTED)}"
        )

    overlay = {
        "base_pilot_integration_r36_overlay_git_blob_sha": git("hash-object", R36),
        "entries": [entry(path) for path in sorted(EXPECTED)],
        "hash_encoding": "sha256-hex",
        "overlay_version": 37,
        "reason": (
            "MILESTONE 0 Windows CI reconciliation: route production and native Red Team "
            "workflows through immutable versioned PowerShell scripts, preserve complete E2E "
            "coverage, require explicit operator confirmations in normal use, and permit CI "
            "scan skipping only with a separate equivalent-scan attestation"
        ),
        "remove_paths": [],
    }
    (ROOT / R37).write_text(
        json.dumps(overlay, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
    print(json.dumps({"status": "R37_READY", "entries": overlay["entries"]}))


if __name__ == "__main__":
    main()
