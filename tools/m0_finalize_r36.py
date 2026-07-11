#!/usr/bin/env python3
"""Create immutable M0 overlay R36 for explicit equivalent-scan runtime evidence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = "9e314d48a840af377e17af1891a6d633d7c5564f"
SELF = "tools/m0_finalize_r36.py"
TEMP_WORKFLOW = ".github/workflows/m0-finalize-r36.yml"
R35 = "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R35.json"
R36 = "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R36.json"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def replace(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig").replace("\r\n", "\n")
    if text.count(old) != 1:
        raise RuntimeError(f"R36 anchor mismatch for {relative}: {old[:100]!r}")
    updated = text.replace(old, new, 1)
    newline = "\r\n" if b"\r\n" in raw else "\n"
    payload = updated.replace("\n", newline).encode("utf-8")
    if bom:
        payload = b"\xef\xbb\xbf" + payload
    path.write_bytes(payload)


def entry(relative: str) -> list[object]:
    payload = (ROOT / relative).read_bytes()
    return [relative, hashlib.sha256(payload).hexdigest(), len(payload)]


def main() -> None:
    if git("branch", "--show-current") != "automation/m0-reconciliation-v4":
        raise SystemExit("REFUSED: unexpected branch")
    subprocess.run(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT, check=True)

    replace(
        "src/quantum/pilot/local_runner.py",
        '''        malware_scan_clean=(
            config.get("malware_scan_outcome") == "CLEAN"
            or (
                config.get("malware_scan_outcome") is None
                and attestations["malware_scan_clean"] is True
            )
        ),''',
        '''        malware_scan_clean=(
            config.get("malware_scan_outcome") == "CLEAN"
            or (
                config.get("malware_scan_outcome")
                in {None, "SKIPPED_BY_EXPLICIT_SWITCH"}
                and attestations["malware_scan_clean"] is True
            )
        ),''',
    )

    replace(
        "tests/test_m0_attestation_redteam.py",
        '''    def run_admission(self, malware_outcome: str) -> dict:
        import hashlib''',
        '''    def run_admission(
        self,
        malware_outcome: str,
        *,
        malware_attested: bool = False,
    ) -> dict:
        import hashlib''',
    )
    replace(
        "tests/test_m0_attestation_redteam.py",
        '''            config["malware_scan_outcome"] = malware_outcome
            return run_local_pilot(file_path=source, config=config, storage_root=temp / "storage")''',
        '''            config["malware_scan_outcome"] = malware_outcome
            config["attestations"]["malware_scan_clean"] = malware_attested
            return run_local_pilot(file_path=source, config=config, storage_root=temp / "storage")''',
    )
    replace(
        "tests/test_m0_attestation_redteam.py",
        '''    def test_defender_unavailable_fallback_cannot_claim_clean_admission(self):
        report = self.run_admission("DEFENDER_UNAVAILABLE_STRUCTURAL_FALLBACK")
        self.assertEqual(report["status"], "ADMISSION_BLOCKED")
        self.assertEqual(report["admission_state"], "VALIDATED")
        self.assertEqual(report["reason"], "DATASET_CONTROLS_INCOMPLETE")
        self.assertIn("CONTROL_EVIDENCE_INCOMPLETE", report["limitations"])
''',
        '''    def test_defender_unavailable_fallback_cannot_claim_clean_admission(self):
        report = self.run_admission(
            "DEFENDER_UNAVAILABLE_STRUCTURAL_FALLBACK",
            malware_attested=True,
        )
        self.assertEqual(report["status"], "ADMISSION_BLOCKED")
        self.assertEqual(report["admission_state"], "VALIDATED")
        self.assertEqual(report["reason"], "DATASET_CONTROLS_INCOMPLETE")
        self.assertIn("CONTROL_EVIDENCE_INCOMPLETE", report["limitations"])

    def test_explicit_equivalent_scan_attestation_can_admit(self):
        report = self.run_admission(
            "SKIPPED_BY_EXPLICIT_SWITCH",
            malware_attested=True,
        )
        self.assertEqual(report["status"], "ADMISSION_COMPLETE")
        self.assertEqual(report["admission_state"], "ADMITTED")

    def test_skipped_scan_without_equivalent_attestation_is_blocked(self):
        report = self.run_admission("SKIPPED_BY_EXPLICIT_SWITCH")
        self.assertEqual(report["status"], "ADMISSION_BLOCKED")
        self.assertEqual(report["admission_state"], "VALIDATED")
''',
    )

    replace(
        "tests/integration_manifest_support.py",
        '''FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{n}.json"
    for n in range(1, 36)
)''',
        '''FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{n}.json"
    for n in range(1, 37)
)''',
    )

    subprocess.run(["git", "rm", "-f", SELF, TEMP_WORKFLOW], cwd=ROOT, check=True)

    expected = {
        "src/quantum/pilot/local_runner.py",
        "tests/integration_manifest_support.py",
        "tests/test_m0_attestation_redteam.py",
    }
    changed = set(
        subprocess.check_output(
            ["git", "diff", "--name-only", BASE, "--"], cwd=ROOT, text=True
        ).splitlines()
    )
    product_changed = {
        path for path in changed
        if not path.startswith("docs/evidence/ARTIFACT_MANIFEST")
    }
    if product_changed != expected:
        raise RuntimeError(
            f"Unexpected R36 scope: missing={sorted(expected-product_changed)}, "
            f"unexpected={sorted(product_changed-expected)}"
        )

    overlay = {
        "base_pilot_integration_r35_overlay_git_blob_sha": git("hash-object", R35),
        "entries": [entry(path) for path in sorted(expected)],
        "hash_encoding": "sha256-hex",
        "overlay_version": 36,
        "reason": (
            "MILESTONE 0 runtime evidence contract: allow an explicitly attested "
            "equivalent malware scan only for SKIPPED_BY_EXPLICIT_SWITCH, while keeping "
            "Defender-unavailable fallback and unattested skips fail-closed"
        ),
        "remove_paths": [],
    }
    (ROOT / R36).write_text(
        json.dumps(overlay, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
    print(json.dumps({"status": "R36_READY", "entries": overlay["entries"]}))


if __name__ == "__main__":
    main()
