from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs/evidence/ARTIFACT_MANIFEST.json"
ARTIFACT_FIELDS = ["path", "sha256", "size_bytes"]
B1A_SCHEMAS = {
    "schemas/calculation-profile.schema.json",
    "schemas/configuration-rule.schema.json",
    "schemas/metric-definition.schema.json",
    "schemas/rounding-policy.schema.json",
    "schemas/rule-resolution-result.schema.json",
    "schemas/safe-expression.schema.json",
}


def _stem(name: str) -> str:
    return name.removeprefix("ARTIFACT_MANIFEST_OVERLAY_").removesuffix(
        ".json"
    ).lower()


def _linear(
    names: tuple[str, ...],
    first_field: str,
) -> tuple[tuple[str, str], ...]:
    return ((names[0], first_field),) + tuple(
        (name, f"base_{_stem(previous)}_overlay_git_blob_sha")
        for previous, name in zip(names, names[1:])
    )


_COMMON = (
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
)
_B1B_NAMES = (
    "ARTIFACT_MANIFEST_OVERLAY_B1B_RESCUE.json",
    "ARTIFACT_MANIFEST_OVERLAY_B1B_RESCUE_V2.json",
    "ARTIFACT_MANIFEST_OVERLAY_B1B_NEXT.json",
    "ARTIFACT_MANIFEST_OVERLAY_B1B_CONTROL.json",
    "ARTIFACT_MANIFEST_OVERLAY_B1B_FINAL.json",
    *(f"ARTIFACT_MANIFEST_OVERLAY_B1B_R{n}.json" for n in range(6, 16)),
)
_B1B = _linear(_B1B_NAMES, "base_real_data_pilot_overlay_git_blob_sha")
_P16_NAMES = (
    "ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION.json",
    *(f"ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R{n}.json" for n in range(2, 10)),
)
_P16 = _linear(_P16_NAMES, "base_real_data_pilot_overlay_git_blob_sha")
_LOCAL = (
    "ARTIFACT_MANIFEST_OVERLAY_LOCAL_STORAGE_POLICY_2026_07_02.json",
    "base_real_data_pilot_overlay_git_blob_sha",
)
_FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{n}.json"
    for n in range(1, 24)
)
_FINAL = _linear(_FINAL_NAMES, "unused")
_ALL_NAMES = tuple(name for name, _ in _COMMON + _B1B + _P16) + (
    _LOCAL[0],
    *_FINAL_NAMES,
)
_CONTROL_PATHS = {
    "docs/evidence/ARTIFACT_MANIFEST.json",
    *(f"docs/evidence/{name}" for name in _ALL_NAMES),
}

COMMON_OVERLAYS = _COMMON
B1B_OVERLAYS = _B1B
P16_OVERLAYS = _P16
LOCAL_OVERLAY = _LOCAL
FINAL_OVERLAY_R1 = _FINAL_NAMES[0]
FINAL_OVERLAYS = _FINAL[1:]
ALL_OVERLAY_NAMES = _ALL_NAMES
CONTROL_PATHS = _CONTROL_PATHS


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def _read_overlay(name: str) -> tuple[bytes, dict]:
    raw = (ROOT / "docs/evidence" / name).read_bytes()
    return raw, json.loads(raw.decode("utf-8"))


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


def _validate_branch(
    overlays: tuple[tuple[str, str], ...],
    anchor: bytes,
    artifacts: dict[str, list],
) -> bytes:
    previous = anchor
    for name, field in overlays:
        raw, overlay = _read_overlay(name)
        if overlay[field] != git_blob_sha(previous):
            raise AssertionError(f"ARTIFACT_MANIFEST_OVERLAY_BASE_MISMATCH:{name}")
        apply_entries(artifacts, overlay)
        previous = raw
    return previous


def load_effective_manifest() -> dict:
    base = MANIFEST_PATH.read_bytes()
    current = json.loads(base.decode("utf-8"))
    artifacts = {row[0]: row for row in current["artifacts"]}
    real_data = _validate_branch(_COMMON, base, artifacts)
    b1b_tip = _validate_branch(_B1B, real_data, artifacts)
    p16_tip = _validate_branch(_P16, real_data, artifacts)
    local_raw, local = _read_overlay(_LOCAL[0])
    if local[_LOCAL[1]] != git_blob_sha(real_data):
        raise AssertionError("ARTIFACT_MANIFEST_OVERLAY_BASE_MISMATCH:" + _LOCAL[0])
    apply_entries(artifacts, local)
    final_raw, final = _read_overlay(_FINAL_NAMES[0])
    anchors = {
        "base_b1b_r15_overlay_git_blob_sha": git_blob_sha(b1b_tip),
        "base_p16_r9_overlay_git_blob_sha": git_blob_sha(p16_tip),
        "base_local_storage_overlay_git_blob_sha": git_blob_sha(local_raw),
    }
    for field, expected in anchors.items():
        if final[field] != expected:
            raise AssertionError(f"ARTIFACT_MANIFEST_INTEGRATION_ANCHOR_MISMATCH:{field}")
    apply_entries(artifacts, final)
    _validate_branch(_FINAL[1:], final_raw, artifacts)
    current["artifacts"] = [artifacts[path] for path in sorted(artifacts)]
    current["artifact_count"] = len(current["artifacts"])
    return current


def tracked_paths() -> list[str]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return sorted(
        path
        for path in output.decode("utf-8").split("\0")
        if path and path not in _CONTROL_PATHS
    )


def expected_manifest(current: dict) -> dict:
    artifacts = []
    for path in tracked_paths():
        data = (ROOT / path).read_bytes()
        artifacts.append([path, hashlib.sha256(data).hexdigest(), len(data)])
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
