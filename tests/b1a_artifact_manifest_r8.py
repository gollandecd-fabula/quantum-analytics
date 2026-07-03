from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs/evidence/ARTIFACT_MANIFEST.json"
OVERLAYS = (
    ("ARTIFACT_MANIFEST_OVERLAY.json", "base_manifest_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_B3_RUNTIME.json", "base_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_B3_FINAL.json", "base_runtime_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_OSS_ADMISSION.json", "base_final_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P1.json", "base_oss_admission_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P1_CLOSURE.json", "base_p1_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P13.json", "base_p1_closure_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P13_MERGE_GATE.json", "base_p13_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P13_CLOSURE.json", "base_p13_merge_gate_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P14.json", "base_p13_closure_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P14_CLOSURE.json", "base_p14_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P15.json", "base_p14_closure_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P15_CLOSURE.json", "base_p15_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_RECOVERY_QCP_2026_07_01_R1.json", "base_p15_closure_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_ASSURANCE_PLAN_2026_07_08.json", "base_recovery_qcp_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_REAL_DATA_PILOT_2026_07_08.json", "base_assurance_plan_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION.json", "base_real_data_pilot_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R2.json", "base_p16_real_xlsx_admission_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R3.json", "base_p16_real_xlsx_admission_r2_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R4.json", "base_p16_real_xlsx_admission_r3_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R5.json", "base_p16_real_xlsx_admission_r4_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R6.json", "base_p16_real_xlsx_admission_r5_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R7.json", "base_p16_real_xlsx_admission_r6_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R8.json", "base_p16_real_xlsx_admission_r7_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R9.json", "base_p16_real_xlsx_admission_r8_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R10.json", "base_p16_real_xlsx_admission_r9_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R11.json", "base_p16_real_xlsx_admission_r10_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R12.json", "base_p16_real_xlsx_admission_r11_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_B1B_RESCUE_V4.json", "base_p16_real_xlsx_admission_r12_overlay_git_blob_sha"),
)
CONTROL_PATHS = {
    "docs/evidence/ARTIFACT_MANIFEST.json",
    *(f"docs/evidence/{name}" for name, _ in OVERLAYS),
}
ARTIFACT_FIELDS = ["path", "sha256", "size_bytes"]
B1A_SCHEMAS = {
    "schemas/calculation-profile.schema.json",
    "schemas/configuration-rule.schema.json",
    "schemas/metric-definition.schema.json",
    "schemas/rounding-policy.schema.json",
    "schemas/rule-resolution-result.schema.json",
    "schemas/safe-expression.schema.json",
}


def git_blob_sha(data: bytes) -> str:
    prefix = f"blob {len(data)}".encode("ascii") + bytes((0,))
    return hashlib.sha1(prefix + data).hexdigest()


def tracked_paths() -> list[str]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return sorted(
        path
        for path in output.decode("utf-8").split(chr(0))
        if path and path not in CONTROL_PATHS
    )


def apply_entries(artifacts: dict[str, list], overlay: dict) -> None:
    encoding = overlay.get("hash_encoding", "sha256-hex")
    for path, digest, size in overlay["entries"]:
        if encoding == "sha256-base64":
            digest = base64.b64decode(digest, validate=True).hex()
        elif encoding != "sha256-hex":
            raise AssertionError("ARTIFACT_MANIFEST_HASH_ENCODING_UNSUPPORTED")
        artifacts[path] = [path, digest, size]
    for path in overlay.get("remove_paths", []):
        artifacts.pop(path, None)


def load_effective_manifest() -> dict:
    base_bytes = MANIFEST_PATH.read_bytes()
    current = json.loads(base_bytes.decode("utf-8"))
    artifacts = {row[0]: row for row in current["artifacts"]}
    previous = base_bytes
    for name, base_field in OVERLAYS:
        raw = (ROOT / "docs/evidence" / name).read_bytes()
        overlay = json.loads(raw.decode("utf-8"))
        if overlay[base_field] != git_blob_sha(previous):
            raise AssertionError(
                f"ARTIFACT_MANIFEST_OVERLAY_BASE_MISMATCH:{name}"
            )
        apply_entries(artifacts, overlay)
        previous = raw
    effective = dict(current)
    effective["artifacts"] = [
        artifacts[path] for path in sorted(artifacts)
    ]
    effective["artifact_count"] = len(effective["artifacts"])
    return effective


def expected_manifest(current: dict) -> dict:
    artifacts = []
    for path in tracked_paths():
        data = (ROOT / path).read_bytes()
        artifacts.append(
            [path, hashlib.sha256(data).hexdigest(), len(data)]
        )
    return {
        "project": current["project"],
        "generated_on": "2026-06-27",
        "package_version": "6",
        "source_constitution_file": current["source_constitution_file"],
        "source_constitution_sha256": current[
            "source_constitution_sha256"
        ],
        "artifact_count": len(artifacts),
        "artifact_fields": ARTIFACT_FIELDS,
        "artifacts": artifacts,
    }


class B1aArtifactManifestTests(unittest.TestCase):
    def test_manifest_matches_current_tracked_tree(self) -> None:
        current = load_effective_manifest()
        self.assertEqual(current, expected_manifest(current))

    def test_manifest_contains_all_b1a_schemas(self) -> None:
        current = load_effective_manifest()
        self.assertEqual(current["artifact_fields"], ARTIFACT_FIELDS)
        paths = {entry[0] for entry in current["artifacts"]}
        self.assertTrue(
            B1A_SCHEMAS.issubset(paths),
            B1A_SCHEMAS - paths,
        )
