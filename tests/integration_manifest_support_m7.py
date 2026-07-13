from __future__ import annotations

from tests import integration_manifest_support_m6 as _base


FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{number}.json"
    for number in range(1, 58)
)
FINAL_OVERLAY_R1 = FINAL_NAMES[0]
FINAL_OVERLAYS = _base._base._linear(FINAL_NAMES, "unused")[1:]
ALL_OVERLAY_NAMES = tuple(
    name
    for name, _ in (
        _base._base.COMMON_OVERLAYS
        + _base._base.B1B_OVERLAYS
        + _base._base.P16_OVERLAYS
    )
) + (
    _base._base.LOCAL_OVERLAY[0],
    *FINAL_NAMES,
)
CONTROL_PATHS = {
    "docs/evidence/ARTIFACT_MANIFEST.json",
    *(f"docs/evidence/{name}" for name in ALL_OVERLAY_NAMES),
}

# Extend the byte-verified M6 bootstrap without rewriting historical loaders.
_base._base.FINAL_NAMES = FINAL_NAMES
_base._base.FINAL_OVERLAY_R1 = FINAL_OVERLAY_R1
_base._base.FINAL_OVERLAYS = FINAL_OVERLAYS
_base._base.ALL_OVERLAY_NAMES = ALL_OVERLAY_NAMES
_base._base.CONTROL_PATHS = CONTROL_PATHS

ARTIFACT_FIELDS = _base.ARTIFACT_FIELDS
B1A_SCHEMAS = _base.B1A_SCHEMAS
expected_manifest = _base.expected_manifest
load_effective_manifest = _base.load_effective_manifest
