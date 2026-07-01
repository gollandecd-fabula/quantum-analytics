from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs/evidence/ARTIFACT_MANIFEST.json"
OVERLAY_PATH = ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY.json"
RUNTIME_OVERLAY_PATH = ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_B3_RUNTIME.json"
FINAL_OVERLAY_PATH = ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_B3_FINAL.json"
OSS_ADMISSION_OVERLAY_PATH = ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_OSS_ADMISSION.json"
P1_OVERLAY_PATH = ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_P1.json"
P1_CLOSURE_OVERLAY_PATH = ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_P1_CLOSURE.json"
P13_OVERLAY_PATH = ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_P13.json"
P13_MERGE_GATE_OVERLAY_PATH = (
    ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_P13_MERGE_GATE.json"
)
P13_CLOSURE_OVERLAY_PATH = (
    ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_P13_CLOSURE.json"
)
P14_OVERLAY_PATH = ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_P14.json"
P14_CLOSURE_OVERLAY_PATH = (
    ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_P14_CLOSURE.json"
)
P15_OVERLAY_PATH = ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_P15.json"
P15_CLOSURE_OVERLAY_PATH = (
    ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_P15_CLOSURE.json"
)
RECOVERY_QCP_OVERLAY_PATH = (
    ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_RECOVERY_QCP_2026_07_01_R1.json"
)
ASSURANCE_PLAN_OVERLAY_PATH = (
    ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_ASSURANCE_PLAN_2026_07_08.json"
)
REAL_DATA_PILOT_OVERLAY_PATH = (
    ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_REAL_DATA_PILOT_2026_07_08.json"
)
B1B_RESCUE_OVERLAY_PATH = (
    ROOT / "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_B1B_RESCUE_V3.json"
)

OVERLAY_CHAIN = (
    (OVERLAY_PATH, "base_manifest_git_blob_sha", "ARTIFACT_MANIFEST_OVERLAY_BASE_MISMATCH"),
    (
        RUNTIME_OVERLAY_PATH,
        "base_overlay_git_blob_sha",
        "ARTIFACT_MANIFEST_RUNTIME_OVERLAY_BASE_MISMATCH",
    ),
    (
        FINAL_OVERLAY_PATH,
        "base_runtime_overlay_git_blob_sha",
        "ARTIFACT_MANIFEST_FINAL_OVERLAY_BASE_MISMATCH",
    ),
    (
        OSS_ADMISSION_OVERLAY_PATH,
        "base_final_overlay_git_blob_sha",
        "ARTIFACT_MANIFEST_OSS_ADMISSION_OVERLAY_BASE_MISMATCH",
    ),
    (
        P1_OVERLAY_PATH,
        "base_oss_admission_overlay_git_blob_sha",
        "ARTIFACT_MANIFEST_P1_OVERLAY_BASE_MISMATCH",
    ),
    (
        P1_CLOSURE_OVERLAY_PATH,
        "base_p1_overlay_git_blob_sha",
        "ARTIFACT_MANIFEST_P1_CLOSURE_OVERLAY_BASE_MISMATCH",
    ),
    (
        P13_OVERLAY_PATH,
        "base_p1_closure_overlay_git_blob_sha",
        "ARTIFACT_MANIFEST_P13_OVERLAY_BASE_MISMATCH",
    ),
    (
        P13_MERGE_GATE_OVERLAY_PATH,
        "base_p13_overlay_git_blob_sha",
        "ARTIFACT_MANIFEST_P13_MERGE_GATE_OVERLAY_BASE_MISMATCH",
    ),
    (
        P13_CLOSURE_OVERLAY_PATH,
        "base_p13_merge_gate_overlay_git_blob_sha",
        "ARTIFACT_MANIFEST_P13_CLOSURE_OVERLAY_BASE_MISMATCH",
    ),
    (
        P14_OVERLAY_PATH,
        "base_p13_closure_overlay_git_blob_sha",
        "ARTIFACT_MANIFEST_P14_OVERLAY_BASE_MISMATCH",
    ),
    (
        P14_CLOSURE_OVERLAY_PATH,
        "base_p14_overlay_git_blob_sha",
        "ARTIFACT_MANIFEST_P14_CLOSURE_OVERLAY_BASE_MISMATCH",
    ),
    (
        P15_OVERLAY_PATH,
        "base_p14_closure_overlay_git_blob_sha",
        "ARTIFACT_MANIFEST_P15_OVERLAY_BASE_MISMATCH",
    ),
    (
        P15_CLOSURE_OVERLAY_PATH,
        "base_p15_overlay_git_blob_sha",
        "ARTIFACT_MANIFEST_P15_CLOSURE_OVERLAY_BASE_MISMATCH",
    ),
    (
        RECOVERY_QCP_OVERLAY_PATH,
        "base_p15_closure_overlay_git_blob_sha",
        "ARTIFACT_MANIFEST_RECOVERY_QCP_OVERLAY_BASE_MISMATCH",
    ),
    (
        ASSURANCE_PLAN_OVERLAY_PATH,
        "base_recovery_qcp_overlay_git_blob_sha",
        "ARTIFACT_MANIFEST_ASSURANCE_PLAN_OVERLAY_BASE_MISMATCH",
    ),
    (
        REAL_DATA_PILOT_OVERLAY_PATH,
        "base_assurance_plan_overlay_git_blob_sha",
        "ARTIFACT_MANIFEST_REAL_DATA_PILOT_OVERLAY_BASE_MISMATCH",
    ),
    (
        B1B_RESCUE_OVERLAY_PATH,
        "base_real_data_pilot_overlay_git_blob_sha",
        "ARTIFACT_MANIFEST_B1B_RESCUE_OVERLAY_BASE_MISMATCH",
    ),
)

CONTROL_PATHS = {
    "docs/evidence/ARTIFACT_MANIFEST.json",
    *(str(path.relative_to(ROOT)).replace("\\", "/") for path, _, _ in OVERLAY_CHAIN),
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
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def tracked_paths() -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=ROOT
    ).decode("utf-8")
    return sorted(
        path for path in output.split("\0")
        if path and path not in CONTROL_PATHS
    )


def apply_entries(artifacts: dict[str, list], overlay: dict) -> None:
    encoding = overlay.get("hash_encoding", "sha256-hex")
    for row in overlay["entries"]:
        path, digest, size = row
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
    previous_bytes = base_bytes

    for path, base_key, error_code in OVERLAY_CHAIN:
        overlay_bytes = path.read_bytes()
        overlay = json.loads(overlay_bytes.decode("utf-8"))
        if overlay[base_key] != git_blob_sha(previous_bytes):
            raise AssertionError(error_code)
        apply_entries(artifacts, overlay)
        previous_bytes = overlay_bytes

    effective = dict(current)
    effective["artifacts"] = [artifacts[path] for path in sorted(artifacts)]
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
        "source_constitution_sha256": current["source_constitution_sha256"],
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
        self.assertTrue(B1A_SCHEMAS.issubset(paths), B1A_SCHEMAS - paths)


if __name__ == "__main__":
    unittest.main()
