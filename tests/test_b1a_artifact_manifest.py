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
CONTROL_PATHS = {
    "docs/evidence/ARTIFACT_MANIFEST.json",
    "docs/evidence/ARTIFACT_MANIFEST_OVERLAY.json",
    "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_B3_RUNTIME.json",
    "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_B3_FINAL.json",
    "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_OSS_ADMISSION.json",
    "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_P1.json",
    "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_P1_CLOSURE.json",
    "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_P13.json",
    "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_P13_MERGE_GATE.json",
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
    overlay_bytes = OVERLAY_PATH.read_bytes()
    overlay = json.loads(overlay_bytes.decode("utf-8"))
    runtime_bytes = RUNTIME_OVERLAY_PATH.read_bytes()
    runtime_overlay = json.loads(runtime_bytes.decode("utf-8"))
    final_bytes = FINAL_OVERLAY_PATH.read_bytes()
    final_overlay = json.loads(final_bytes.decode("utf-8"))
    oss_admission_bytes = OSS_ADMISSION_OVERLAY_PATH.read_bytes()
    oss_admission_overlay = json.loads(oss_admission_bytes.decode("utf-8"))
    p1_bytes = P1_OVERLAY_PATH.read_bytes()
    p1_overlay = json.loads(p1_bytes.decode("utf-8"))
    p1_closure_bytes = P1_CLOSURE_OVERLAY_PATH.read_bytes()
    p1_closure_overlay = json.loads(p1_closure_bytes.decode("utf-8"))
    p13_bytes = P13_OVERLAY_PATH.read_bytes()
    p13_overlay = json.loads(p13_bytes.decode("utf-8"))
    p13_merge_gate_overlay = json.loads(
        P13_MERGE_GATE_OVERLAY_PATH.read_text(encoding="utf-8")
    )

    if overlay["base_manifest_git_blob_sha"] != git_blob_sha(base_bytes):
        raise AssertionError("ARTIFACT_MANIFEST_OVERLAY_BASE_MISMATCH")
    if runtime_overlay["base_overlay_git_blob_sha"] != git_blob_sha(overlay_bytes):
        raise AssertionError("ARTIFACT_MANIFEST_RUNTIME_OVERLAY_BASE_MISMATCH")
    if final_overlay["base_runtime_overlay_git_blob_sha"] != git_blob_sha(runtime_bytes):
        raise AssertionError("ARTIFACT_MANIFEST_FINAL_OVERLAY_BASE_MISMATCH")
    if oss_admission_overlay["base_final_overlay_git_blob_sha"] != git_blob_sha(final_bytes):
        raise AssertionError("ARTIFACT_MANIFEST_OSS_ADMISSION_OVERLAY_BASE_MISMATCH")
    if p1_overlay["base_oss_admission_overlay_git_blob_sha"] != git_blob_sha(
        oss_admission_bytes
    ):
        raise AssertionError("ARTIFACT_MANIFEST_P1_OVERLAY_BASE_MISMATCH")
    if p1_closure_overlay["base_p1_overlay_git_blob_sha"] != git_blob_sha(
        p1_bytes
    ):
        raise AssertionError("ARTIFACT_MANIFEST_P1_CLOSURE_OVERLAY_BASE_MISMATCH")
    if p13_overlay["base_p1_closure_overlay_git_blob_sha"] != git_blob_sha(
        p1_closure_bytes
    ):
        raise AssertionError("ARTIFACT_MANIFEST_P13_OVERLAY_BASE_MISMATCH")
    if p13_merge_gate_overlay["base_p13_overlay_git_blob_sha"] != git_blob_sha(
        p13_bytes
    ):
        raise AssertionError("ARTIFACT_MANIFEST_P13_MERGE_GATE_OVERLAY_BASE_MISMATCH")

    artifacts = {row[0]: row for row in current["artifacts"]}
    apply_entries(artifacts, overlay)
    apply_entries(artifacts, runtime_overlay)
    apply_entries(artifacts, final_overlay)
    apply_entries(artifacts, oss_admission_overlay)
    apply_entries(artifacts, p1_overlay)
    apply_entries(artifacts, p1_closure_overlay)
    apply_entries(artifacts, p13_overlay)
    apply_entries(artifacts, p13_merge_gate_overlay)

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
