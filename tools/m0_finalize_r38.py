#!/usr/bin/env python3
"""Create immutable M0 overlay R38 and isolate preserved CI run blocks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
R37_BASE = "6fc468dde169419cdb9b2ec865d4ba390b6fc197"
SELF = "tools/m0_finalize_r38.py"
TEMP_WORKFLOW = ".github/workflows/m0-finalize-r38.yml"
R37 = "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R37.json"
R38 = "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R38.json"
SUPPORT = "tests/integration_manifest_support.py"
PRODUCTION_SCRIPT = "scripts/ci/windows_local_production_r37.ps1"
NATIVE_SCRIPT = "scripts/ci/native_one_button_r37.ps1"
PRODUCTION_WORKFLOW = ".github/workflows/windows-local-production.yml"

EXPECTED = {
    PRODUCTION_WORKFLOW,
    PRODUCTION_SCRIPT,
    NATIVE_SCRIPT,
    SUPPORT,
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def entry(relative: str) -> list[object]:
    payload = (ROOT / relative).read_bytes()
    return [relative, hashlib.sha256(payload).hexdigest(), len(payload)]


def scope_run_blocks(relative: str, expected_sections: int) -> None:
    path = ROOT / relative
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    pattern = re.compile(r"(?m)^# === .+ ===\n")
    matches = list(pattern.finditer(text))
    if len(matches) != expected_sections:
        raise RuntimeError(
            f"{relative}: expected {expected_sections} preserved run blocks, got {len(matches)}"
        )
    prefix = text[: matches[0].start()].rstrip()
    result = [prefix, ""]
    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[body_start:body_end].rstrip()
        if body.startswith("& {\n"):
            raise RuntimeError(f"{relative}: block already scoped unexpectedly")
        result.extend([match.group(0).rstrip(), "& {", body, "}", ""])
    updated = "\n".join(result).rstrip() + "\n"
    if updated.count("\n& {\n") != expected_sections:
        raise RuntimeError(f"{relative}: script-scope count mismatch")
    if relative == PRODUCTION_SCRIPT:
        if "$verificationErrorLog" not in updated:
            raise RuntimeError("Production verification trap was lost")
        if "windows-production-r37.log" in updated:
            raise RuntimeError("Workflow transcript path leaked into versioned script")
    if relative == NATIVE_SCRIPT:
        if "native-test-error.log" not in updated:
            raise RuntimeError("Native Red Team trap was lost")
        if "No dates, AUTHORIZE or REVIEWED input is required" in updated:
            raise RuntimeError("Native script retained automatic-attestation claim")
    payload = updated.encode("utf-8")
    if bom:
        payload = b"\xef\xbb\xbf" + payload
    path.write_bytes(payload)


def update_manifest_support() -> None:
    path = ROOT / SUPPORT
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    old = '''FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{n}.json"
    for n in range(1, 38)
)'''
    new = '''FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{n}.json"
    for n in range(1, 39)
)'''
    if text.count(old) != 1:
        raise RuntimeError("R38 manifest-support anchor mismatch")
    updated = text.replace(old, new, 1)
    newline = "\r\n" if b"\r\n" in raw else "\n"
    payload = updated.replace("\n", newline).encode("utf-8")
    if bom:
        payload = b"\xef\xbb\xbf" + payload
    path.write_bytes(payload)


def assert_workflow_transcript() -> None:
    workflow = (ROOT / PRODUCTION_WORKFLOW).read_text(encoding="utf-8")
    for marker in (
        "Tee-Object -FilePath windows-production-r37.log",
        "windows-production-r37.log",
        "scripts\\ci\\windows_local_production_r37.ps1",
    ):
        if marker not in workflow:
            raise RuntimeError(f"Production workflow missing transcript marker: {marker}")


def main() -> None:
    if git("branch", "--show-current") != "automation/m0-reconciliation-v4":
        raise SystemExit("REFUSED: unexpected branch")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", R37_BASE, "HEAD"],
        cwd=ROOT,
        check=True,
    )
    assert_workflow_transcript()
    scope_run_blocks(PRODUCTION_SCRIPT, expected_sections=8)
    scope_run_blocks(NATIVE_SCRIPT, expected_sections=5)
    update_manifest_support()
    subprocess.run(["git", "rm", "-f", SELF, TEMP_WORKFLOW], cwd=ROOT, check=True)

    changed = set(
        subprocess.check_output(
            ["git", "diff", "--name-only", R37_BASE, "--"],
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
            "Unexpected R38 scope: "
            f"missing={sorted(EXPECTED-product_changed)}, "
            f"unexpected={sorted(product_changed-EXPECTED)}"
        )

    overlay = {
        "base_pilot_integration_r37_overlay_git_blob_sha": git("hash-object", R37),
        "entries": [entry(path) for path in sorted(EXPECTED)],
        "hash_encoding": "sha256-hex",
        "overlay_version": 38,
        "reason": (
            "MILESTONE 0 Windows CI hardening: isolate each preserved workflow run block "
            "in its own PowerShell script scope so late traps cannot intercept earlier "
            "failures, and retain a complete production transcript for independent diagnosis"
        ),
        "remove_paths": [],
    }
    (ROOT / R38).write_text(
        json.dumps(overlay, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
    print(json.dumps({"status": "R38_READY", "entries": overlay["entries"]}))


if __name__ == "__main__":
    main()
