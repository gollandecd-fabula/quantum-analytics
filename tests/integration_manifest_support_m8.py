from __future__ import annotations

from tests import integration_manifest_support_m7 as _base


_core = _base._base._base
FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{number}.json"
    for number in range(1, 100)
)
FINAL_OVERLAY_R1 = FINAL_NAMES[0]
FINAL_OVERLAYS = _core._linear(FINAL_NAMES, "unused")[1:]
GOVERNANCE_OVERLAY = (
    "ARTIFACT_MANIFEST_OVERLAY_WB_RELEASE_R2_GOV_R1.json",
    "base_pilot_integration_r99_overlay_git_blob_sha",
)
ALL_OVERLAY_NAMES = tuple(
    name
    for name, _ in (
        _core.COMMON_OVERLAYS + _core.B1B_OVERLAYS + _core.P16_OVERLAYS
    )
) + (
    _core.LOCAL_OVERLAY[0],
    *FINAL_NAMES,
    GOVERNANCE_OVERLAY[0],
)
CONTROL_PATHS = {
    "docs/evidence/ARTIFACT_MANIFEST.json",
    *(f"docs/evidence/{name}" for name in ALL_OVERLAY_NAMES),
}

# Extend the byte-verified M7 loader through R99 and a separate governance
# branch. R100 remains available for the WBR2-M5 product candidate.
_core.FINAL_NAMES = FINAL_NAMES
_core.FINAL_OVERLAY_R1 = FINAL_OVERLAY_R1
_core.FINAL_OVERLAYS = FINAL_OVERLAYS
_core.ALL_OVERLAY_NAMES = ALL_OVERLAY_NAMES
_core.CONTROL_PATHS = CONTROL_PATHS

ARTIFACT_FIELDS = _base.ARTIFACT_FIELDS
B1A_SCHEMAS = _base.B1A_SCHEMAS
expected_manifest = _base.expected_manifest


def load_effective_manifest() -> dict:
    current = _base.load_effective_manifest()
    artifacts = {row[0]: row for row in current["artifacts"]}

    anchor_raw = (
        _core.ROOT
        / "docs/evidence"
        / "ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R99.json"
    ).read_bytes()
    _, governance = _core._read_overlay(GOVERNANCE_OVERLAY[0])
    if governance[GOVERNANCE_OVERLAY[1]] != _core.git_blob_sha(anchor_raw):
        raise AssertionError(
            "ARTIFACT_MANIFEST_OVERLAY_BASE_MISMATCH:"
            + GOVERNANCE_OVERLAY[0]
        )
    _core.apply_entries(artifacts, governance)

    current["artifacts"] = [artifacts[path] for path in sorted(artifacts)]
    current["artifact_count"] = len(current["artifacts"])
    return current
