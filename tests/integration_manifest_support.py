from __future__ import annotations

from tests import integration_manifest_support_v5 as _previous

_base = _previous._base
_LINEAR_FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{n}.json"
    for n in range(1, 27)
)
_INVALID_AUDIT_OVERLAYS = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{n}.json"
    for n in range(27, 31)
)
_RECOVERY_OVERLAY = "ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R31.json"

_base.FINAL_NAMES = _LINEAR_FINAL_NAMES
_base.FINAL_OVERLAY_R1 = _LINEAR_FINAL_NAMES[0]
_base.FINAL_OVERLAYS = _base._linear(_LINEAR_FINAL_NAMES, "unused")[1:]
_base.ALL_OVERLAY_NAMES = tuple(
    name
    for name, _ in _base.COMMON_OVERLAYS + _base.B1B_OVERLAYS + _base.P16_OVERLAYS
) + (
    _base.LOCAL_OVERLAY[0],
    *_LINEAR_FINAL_NAMES,
    *_INVALID_AUDIT_OVERLAYS,
    _RECOVERY_OVERLAY,
)
_base.CONTROL_PATHS = {
    "docs/evidence/ARTIFACT_MANIFEST.json",
    *(f"docs/evidence/{name}" for name in _base.ALL_OVERLAY_NAMES),
}

ARTIFACT_FIELDS = _base.ARTIFACT_FIELDS
B1A_SCHEMAS = _base.B1A_SCHEMAS
expected_manifest = _base.expected_manifest


def load_effective_manifest() -> dict:
    current = _base.load_effective_manifest()
    artifacts = {row[0]: row for row in current["artifacts"]}
    r26_raw = (
        _base.ROOT / "docs/evidence" / _LINEAR_FINAL_NAMES[-1]
    ).read_bytes()
    _, recovery = _base._read_overlay(_RECOVERY_OVERLAY)
    if recovery["base_pilot_integration_r26_overlay_git_blob_sha"] != _base.git_blob_sha(
        r26_raw
    ):
        raise AssertionError("ARTIFACT_MANIFEST_RECOVERY_R31_BASE_MISMATCH")
    _base.apply_entries(artifacts, recovery)
    current["artifacts"] = [artifacts[path] for path in sorted(artifacts)]
    current["artifact_count"] = len(current["artifacts"])
    return current


__all__ = [
    "ARTIFACT_FIELDS",
    "B1A_SCHEMAS",
    "expected_manifest",
    "load_effective_manifest",
]
