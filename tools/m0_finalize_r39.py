#!/usr/bin/env python3
"""Create immutable M0 overlay R39 for pwsh-native Windows wrappers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
R38_BASE = "2a7760841cecceafec327b5d8d122fa9d3f21037"
SELF = "tools/m0_finalize_r39.py"
TEMP_WORKFLOW = ".github/workflows/m0-finalize-r39.yml"
R38 = "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R38.json"
R39 = "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R39.json"
SUPPORT = "tests/integration_manifest_support.py"
PRODUCTION_WORKFLOW = ".github/workflows/windows-local-production.yml"
NATIVE_WORKFLOW = ".github/workflows/build-one-button-redteam-r3.yml"
EXPECTED = {PRODUCTION_WORKFLOW, NATIVE_WORKFLOW, SUPPORT}


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
    for n in range(1, 39)
)'''
    new = '''FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{n}.json"
    for n in range(1, 40)
)'''
    if text.count(old) != 1:
        raise RuntimeError("R39 manifest-support anchor mismatch")
    updated = text.replace(old, new, 1)
    newline = "\r\n" if b"\r\n" in raw else "\n"
    payload = updated.replace("\n", newline).encode("utf-8")
    if bom:
        payload = b"\xef\xbb\xbf" + payload
    path.write_bytes(payload)


def assert_wrappers() -> None:
    production = (ROOT / PRODUCTION_WORKFLOW).read_text(encoding="utf-8")
    native = (ROOT / NATIVE_WORKFLOW).read_text(encoding="utf-8")
    for label, content, script, transcript in (
        (
            "production",
            production,
            "& .\\scripts\\ci\\windows_local_production_r37.ps1",
            "windows-production-r37.log",
        ),
        (
            "native",
            native,
            "& .\\scripts\\ci\\native_one_button_r37.ps1",
            "native-one-button-r37.log",
        ),
    ):
        if script not in content:
            raise RuntimeError(f"{label} wrapper is not pwsh-native")
        if transcript not in content:
            raise RuntimeError(f"{label} wrapper lacks complete transcript")
        if "powershell.exe -NoProfile -ExecutionPolicy Bypass" in content:
            raise RuntimeError(f"{label} wrapper still crosses into Windows PowerShell 5.1")
        if "TARGET_SHA:" not in content:
            raise RuntimeError(f"{label} wrapper lost exact-head binding")


def main() -> None:
    if git("branch", "--show-current") != "automation/m0-reconciliation-v4":
        raise SystemExit("REFUSED: unexpected branch")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", R38_BASE, "HEAD"],
        cwd=ROOT,
        check=True,
    )
    assert_wrappers()
    update_manifest_support()
    subprocess.run(["git", "rm", "-f", SELF, TEMP_WORKFLOW], cwd=ROOT, check=True)

    changed = set(
        subprocess.check_output(
            ["git", "diff", "--name-only", R38_BASE, "--"],
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
            "Unexpected R39 scope: "
            f"missing={sorted(EXPECTED-product_changed)}, "
            f"unexpected={sorted(product_changed-EXPECTED)}"
        )

    overlay = {
        "base_pilot_integration_r38_overlay_git_blob_sha": git("hash-object", R38),
        "entries": [entry(path) for path in sorted(EXPECTED)],
        "hash_encoding": "sha256-hex",
        "overlay_version": 39,
        "reason": (
            "MILESTONE 0 Windows runner correction: execute versioned production and native "
            "Red Team scripts directly in pwsh, matching the original workflow runtime, while "
            "retaining complete failure transcripts and exact-head binding"
        ),
        "remove_paths": [],
    }
    (ROOT / R39).write_text(
        json.dumps(overlay, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
    print(json.dumps({"status": "R39_READY", "entries": overlay["entries"]}))


if __name__ == "__main__":
    main()
