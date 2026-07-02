from __future__ import annotations

import base64
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs/evidence/ARTIFACT_MANIFEST.json"

COMMON_OVERLAYS = (
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
B1B_OVERLAYS = (
    ("ARTIFACT_MANIFEST_OVERLAY_B1B_RESCUE.json", "base_real_data_pilot_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_B1B_RESCUE_V2.json", "base_b1b_rescue_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_B1B_NEXT.json", "base_b1b_rescue_v2_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_B1B_CONTROL.json", "base_b1b_next_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_B1B_FINAL.json", "base_b1b_control_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_B1B_R6.json", "base_b1b_final_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_B1B_R7.json", "base_b1b_r6_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_B1B_R8.json", "base_b1b_r7_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_B1B_R9.json", "base_b1b_r8_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_B1B_R10.json", "base_b1b_r9_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_B1B_R11.json", "base_b1b_r10_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_B1B_R12.json", "base_b1b_r11_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_B1B_R13.json", "base_b1b_r12_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_B1B_R14.json", "base_b1b_r13_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_B1B_R15.json", "base_b1b_r14_overlay_git_blob_sha"),
)
P16_OVERLAYS = (
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION.json", "base_real_data_pilot_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R2.json", "base_p16_real_xlsx_admission_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R3.json", "base_p16_real_xlsx_admission_r2_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R4.json", "base_p16_real_xlsx_admission_r3_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R5.json", "base_p16_real_xlsx_admission_r4_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R6.json", "base_p16_real_xlsx_admission_r5_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R7.json", "base_p16_real_xlsx_admission_r6_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R8.json", "base_p16_real_xlsx_admission_r7_overlay_git_blob_sha"),
    ("ARTIFACT_MANIFEST_OVERLAY_P16_REAL_XLSX_ADMISSION_R9.json", "base_p16_real_xlsx_admission_r8_overlay_git_blob_sha"),
)
LOCAL_OVERLAY = (
    "ARTIFACT_MANIFEST_OVERLAY_LOCAL_STORAGE_POLICY_2026_07_02.json",
    "base_real_data_pilot_overlay_git_blob_sha",
)
FINAL_OVERLAY_R1 = "ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R1.json"
FINAL_OVERLAY_R2 = "ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R2.json"

ALL_OVERLAY_NAMES = tuple(
    name for name, _ in COMMON_OVERLAYS + B1B_OVERLAYS + P16_OVERLAYS
) + (
    LOCAL_OVERLAY[0],
    FINAL_OVERLAY_R1,
    FINAL_OVERLAY_R2,
)
CONTROL_PATHS = {
    "docs/evidence/ARTIFACT_MANIFEST.json",
    *(f"docs/evidence/{name}" for name in ALL_OVERLAY_NAMES),
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
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def tracked_paths() -> list[str]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8")
    return sorted(path for path in output.split("\0") if path and path not in CONTROL_PATHS)


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


def _read_overlay(name: str) -> tuple[bytes, dict]:
    raw = (ROOT / "docs/evidence" / name).read_bytes()
    return raw, json.loads(raw.decode("utf-8"))


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

    real_data_anchor = _validate_branch(COMMON_OVERLAYS, base, artifacts)
    b1b_tip = _validate_branch(B1B_OVERLAYS, real_data_anchor, artifacts)
    p16_tip = _validate_branch(P16_OVERLAYS, real_data_anchor, artifacts)

    local_raw, local_overlay = _read_overlay(LOCAL_OVERLAY[0])
    if local_overlay[LOCAL_OVERLAY[1]] != git_blob_sha(real_data_anchor):
        raise AssertionError("ARTIFACT_MANIFEST_OVERLAY_BASE_MISMATCH:" + LOCAL_OVERLAY[0])
    apply_entries(artifacts, local_overlay)

    final_r1_raw, final_r1 = _read_overlay(FINAL_OVERLAY_R1)
    anchors = {
        "base_b1b_r15_overlay_git_blob_sha": git_blob_sha(b1b_tip),
        "base_p16_r9_overlay_git_blob_sha": git_blob_sha(p16_tip),
        "base_local_storage_overlay_git_blob_sha": git_blob_sha(local_raw),
    }
    for field, expected in anchors.items():
        if final_r1[field] != expected:
            raise AssertionError(f"ARTIFACT_MANIFEST_INTEGRATION_ANCHOR_MISMATCH:{field}")
    apply_entries(artifacts, final_r1)

    _, final_r2 = _read_overlay(FINAL_OVERLAY_R2)
    if final_r2["base_pilot_integration_r1_overlay_git_blob_sha"] != git_blob_sha(final_r1_raw):
        raise AssertionError("ARTIFACT_MANIFEST_INTEGRATION_R2_BASE_MISMATCH")
    apply_entries(artifacts, final_r2)

    current["artifacts"] = [artifacts[path] for path in sorted(artifacts)]
    current["artifact_count"] = len(current["artifacts"])
    return current


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
