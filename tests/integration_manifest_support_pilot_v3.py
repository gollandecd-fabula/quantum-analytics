from __future__ import annotations

from tests import integration_manifest_support_m8 as _base

PILOT_V3_RECOVERY_OVERLAY = (
    "ARTIFACT_MANIFEST_OVERLAY_PILOT_V3_0_CANONICAL_RECOVERY.json",
    "base_agent_v3_1_m1_overlay_git_blob_sha",
)
PILOT_V3_P0_EXECUTION_OVERLAY = (
    "ARTIFACT_MANIFEST_OVERLAY_PILOT_V3_0_P0_EXECUTION.json",
    "base_pilot_v3_0_canonical_recovery_overlay_git_blob_sha",
)
PILOT_V3_P0_SIGNATURE_CORRECTIVE_OVERLAY = (
    "ARTIFACT_MANIFEST_OVERLAY_PILOT_V3_0_P0_SIGNATURE_CORRECTIVE.json",
    "base_pilot_v3_0_p0_execution_overlay_git_blob_sha",
)
PILOT_V3_P0_GENERATOR_INVOCATION_CORRECTIVE_OVERLAY = (
    "ARTIFACT_MANIFEST_OVERLAY_PILOT_V3_0_P0_GENERATOR_INVOCATION_CORRECTIVE.json",
    "base_pilot_v3_0_p0_signature_corrective_overlay_git_blob_sha",
)
ALL_OVERLAY_NAMES = (
    *_base.ALL_OVERLAY_NAMES,
    PILOT_V3_RECOVERY_OVERLAY[0],
    PILOT_V3_P0_EXECUTION_OVERLAY[0],
    PILOT_V3_P0_SIGNATURE_CORRECTIVE_OVERLAY[0],
    PILOT_V3_P0_GENERATOR_INVOCATION_CORRECTIVE_OVERLAY[0],
)
CONTROL_PATHS = {
    *_base.CONTROL_PATHS,
    *(f"docs/evidence/{name}" for name in (
        PILOT_V3_RECOVERY_OVERLAY[0],
        PILOT_V3_P0_EXECUTION_OVERLAY[0],
        PILOT_V3_P0_SIGNATURE_CORRECTIVE_OVERLAY[0],
        PILOT_V3_P0_GENERATOR_INVOCATION_CORRECTIVE_OVERLAY[0],
    )),
}
ARTIFACT_FIELDS = _base.ARTIFACT_FIELDS
B1A_SCHEMAS = _base.B1A_SCHEMAS
expected_manifest = _base.expected_manifest


def _apply(
    artifacts: dict[str, list],
    spec: tuple[str, str],
    anchor_raw: bytes,
) -> bytes:
    name, field = spec
    evidence = _base._core.ROOT / "docs/evidence"
    raw = (evidence / name).read_bytes()
    _, overlay = _base._core._read_overlay(name)
    if overlay[field] != _base._core.git_blob_sha(anchor_raw):
        raise AssertionError("ARTIFACT_MANIFEST_OVERLAY_BASE_MISMATCH:" + name)
    _base._core.apply_entries(artifacts, overlay)
    return raw


def load_effective_manifest() -> dict:
    current = _base.load_effective_manifest()
    artifacts = {row[0]: row for row in current["artifacts"]}
    evidence = _base._core.ROOT / "docs/evidence"
    m1_raw = (
        evidence / "ARTIFACT_MANIFEST_OVERLAY_AGENT_V3_1_M1.json"
    ).read_bytes()
    recovery_raw = _apply(artifacts, PILOT_V3_RECOVERY_OVERLAY, m1_raw)
    execution_raw = _apply(
        artifacts,
        PILOT_V3_P0_EXECUTION_OVERLAY,
        recovery_raw,
    )
    signature_corrective_raw = _apply(
        artifacts,
        PILOT_V3_P0_SIGNATURE_CORRECTIVE_OVERLAY,
        execution_raw,
    )
    _apply(
        artifacts,
        PILOT_V3_P0_GENERATOR_INVOCATION_CORRECTIVE_OVERLAY,
        signature_corrective_raw,
    )
    current["artifacts"] = [artifacts[path] for path in sorted(artifacts)]
    current["artifact_count"] = len(current["artifacts"])
    return current
