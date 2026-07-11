#!/usr/bin/env python3
"""Create immutable M0 overlay R35 for the corrected launcher workflow."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = "c399d60a8236ca30f3e395aad23b2e3af184c5b4"
SELF = "tools/m0_finalize_r35.py"
WORKFLOW = ".github/workflows/m0-finalize-r35.yml"
R34 = "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R34.json"
R35 = "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R35.json"
SUPPORT = "tests/integration_manifest_support.py"
LAUNCHER_WORKFLOW = ".github/workflows/windows-source-package-launchers-r1.yml"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def entry(relative: str) -> list[object]:
    payload = (ROOT / relative).read_bytes()
    return [relative, hashlib.sha256(payload).hexdigest(), len(payload)]


def main() -> None:
    if git("branch", "--show-current") != "automation/m0-reconciliation-v4":
        raise SystemExit("REFUSED: unexpected branch")
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)

    support_path = ROOT / SUPPORT
    raw = support_path.read_bytes()
    text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    old = '''FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{n}.json"
    for n in range(1, 35)
)'''
    new = '''FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{n}.json"
    for n in range(1, 36)
)'''
    if text.count(old) != 1:
        raise RuntimeError("R35 manifest-support anchor mismatch")
    updated = text.replace(old, new, 1)
    newline = "\r\n" if b"\r\n" in raw else "\n"
    payload = updated.replace("\n", newline).encode("utf-8")
    if raw.startswith(b"\xef\xbb\xbf"):
        payload = b"\xef\xbb\xbf" + payload
    support_path.write_bytes(payload)

    subprocess.run(["git", "rm", "-f", SELF, WORKFLOW], cwd=ROOT, check=True)

    changed = set(
        subprocess.check_output(
            ["git", "diff", "--name-only", BASE, "--"], cwd=ROOT, text=True
        ).splitlines()
    )
    expected = {LAUNCHER_WORKFLOW, SUPPORT}
    product_changed = {
        path for path in changed
        if not path.startswith("docs/evidence/ARTIFACT_MANIFEST")
    }
    if product_changed != expected:
        raise RuntimeError(
            f"Unexpected R35 scope: missing={sorted(expected-product_changed)}, "
            f"unexpected={sorted(product_changed-expected)}"
        )

    overlay = {
        "base_pilot_integration_r34_overlay_git_blob_sha": git("hash-object", R34),
        "entries": [entry(path) for path in sorted(expected)],
        "hash_encoding": "sha256-hex",
        "overlay_version": 35,
        "reason": (
            "MILESTONE 0 CI contract correction: verify fail-closed source launchers "
            "that require explicit AUTHORIZE and REVIEWED confirmations and never "
            "attest for the operator"
        ),
        "remove_paths": [],
    }
    (ROOT / R35).write_text(
        json.dumps(overlay, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
    print(json.dumps({"status": "R35_READY", "entries": overlay["entries"]}))


if __name__ == "__main__":
    main()
