from __future__ import annotations

from tests import integration_manifest_support_m8 as _base

PILOT_V3_RECOVERY_OVERLAY = (
    "ARTIFACT_MANIFEST_OVERLAY_PILOT_V3_0_CANONICAL_RECOVERY.json",
    "base_agent_v3_1_m1_overlay_git_blob_sha",
)
ALL_OVERLAY_NAMES = (*_base.ALL_OVERLAY_NAMES, PILOT_V3_RECOVERY_OVERLAY[0])
CONTROL_PATHS = {
    *_base.CONTROL_PATHS,
    f"docs/evidence/{PILOT_V3_RECOVERY_OVERLAY[0]}",
}
ARTIFACT_FIELDS = _base.ARTIFACT_FIELDS
B1A_SCHEMAS = _base.B1A_SCHEMAS
expected_manifest = _base.expected_manifest

def load_effective_manifest() -> dict:
    current = _base.load_effective_manifest()
    artifacts = {row[0]: row for row in current["artifacts"]}
    evidence = _base._core.ROOT / "docs/evidence"
    m1_raw = (evidence / "ARTIFACT_MANIFEST_OVERLAY_AGENT_V3_1_M1.json").read_bytes()
    name, field = PILOT_V3_RECOVERY_OVERLAY
    _, overlay = _base._core._read_overlay(name)
    if overlay[field] != _base._core.git_blob_sha(m1_raw):
        raise AssertionError("ARTIFACT_MANIFEST_OVERLAY_BASE_MISMATCH:" + name)
    _base._core.apply_entries(artifacts, overlay)
    current["artifacts"] = [artifacts[path] for path in sorted(artifacts)]
    current["artifact_count"] = len(current["artifacts"])
    return current
