#!/usr/bin/env python3
"""Create immutable M0 overlay R40 for reliable wrapper failure semantics."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
R39_BASE = "7224fc28a0cfc59f36e02931ce33e696d961ee02"
SELF = "tools/m0_finalize_r40.py"
TEMP_WORKFLOW = ".github/workflows/m0-finalize-r40.yml"
R39 = "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R39.json"
R40 = "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R40.json"
SUPPORT = "tests/integration_manifest_support.py"
PRODUCTION = ".github/workflows/windows-local-production.yml"
NATIVE = ".github/workflows/build-one-button-redteam-r3.yml"
EXPECTED = {PRODUCTION, NATIVE, SUPPORT}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def entry(relative: str) -> list[object]:
    payload = (ROOT / relative).read_bytes()
    return [relative, hashlib.sha256(payload).hexdigest(), len(payload)]


def update_support() -> None:
    path = ROOT / SUPPORT
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    old = '''FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{n}.json"
    for n in range(1, 40)
)'''
    new = '''FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{n}.json"
    for n in range(1, 41)
)'''
    if text.count(old) != 1:
        raise RuntimeError("R40 manifest-support anchor mismatch")
    updated = text.replace(old, new, 1)
    newline = "\r\n" if b"\r\n" in raw else "\n"
    payload = updated.replace("\n", newline).encode("utf-8")
    if bom:
        payload = b"\xef\xbb\xbf" + payload
    path.write_bytes(payload)


def assert_wrappers() -> None:
    for label, relative, transcript in (
        ("production", PRODUCTION, "windows-production-r37.log"),
        ("native", NATIVE, "native-one-button-r37.log"),
    ):
        content = (ROOT / relative).read_text(encoding="utf-8")
        if "try {" not in content or "catch {" not in content or "throw" not in content:
            raise RuntimeError(f"{label} wrapper lacks terminating-error propagation")
        if "$LASTEXITCODE" in content:
            raise RuntimeError(f"{label} wrapper still trusts stale LASTEXITCODE")
        if transcript not in content:
            raise RuntimeError(f"{label} wrapper lost transcript")
        if "TARGET_SHA:" not in content:
            raise RuntimeError(f"{label} wrapper lost exact-head binding")


def main() -> None:
    if git("branch", "--show-current") != "automation/m0-reconciliation-v4":
        raise SystemExit("REFUSED: unexpected branch")
    subprocess.run(["git", "merge-base", "--is-ancestor", R39_BASE, "HEAD"], cwd=ROOT, check=True)
    assert_wrappers()
    update_support()
    subprocess.run(["git", "rm", "-f", SELF, TEMP_WORKFLOW], cwd=ROOT, check=True)

    changed = set(
        subprocess.check_output(["git", "diff", "--name-only", R39_BASE, "--"], cwd=ROOT, text=True).splitlines()
    )
    product_changed = {p for p in changed if not p.startswith("docs/evidence/ARTIFACT_MANIFEST")}
    if product_changed != EXPECTED:
        raise RuntimeError(
            f"Unexpected R40 scope: missing={sorted(EXPECTED-product_changed)}, "
            f"unexpected={sorted(product_changed-EXPECTED)}"
        )

    overlay = {
        "base_pilot_integration_r39_overlay_git_blob_sha": git("hash-object", R39),
        "entries": [entry(path) for path in sorted(EXPECTED)],
        "hash_encoding": "sha256-hex",
        "overlay_version": 40,
        "reason": (
            "MILESTONE 0 Windows wrapper reliability: propagate only terminating script "
            "failures, not stale native exit codes left by expected negative Red Team checks, "
            "while preserving exact-head binding and complete transcripts"
        ),
        "remove_paths": [],
    }
    (ROOT / R40).write_text(json.dumps(overlay, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
    print(json.dumps({"status": "R40_READY", "entries": overlay["entries"]}))


if __name__ == "__main__":
    main()
