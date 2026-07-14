from __future__ import annotations

from tests import integration_manifest_support_m7 as _base


_core = _base._base._base
FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{number}.json"
    for number in range(1, 85)
)
FINAL_OVERLAY_R1 = FINAL_NAMES[0]
FINAL_OVERLAYS = _core._linear(FINAL_NAMES, "unused")[1:]
ALL_OVERLAY_NAMES = tuple(
    name
    for name, _ in (
        _core.COMMON_OVERLAYS + _core.B1B_OVERLAYS + _core.P16_OVERLAYS
    )
) + (
    _core.LOCAL_OVERLAY[0],
    *FINAL_NAMES,
)
CONTROL_PATHS = {
    "docs/evidence/ARTIFACT_MANIFEST.json",
    *(f"docs/evidence/{name}" for name in ALL_OVERLAY_NAMES),
}

# Extend the byte-verified M7 loader through the append-only R84 overlay.
_core.FINAL_NAMES = FINAL_NAMES
_core.FINAL_OVERLAY_R1 = FINAL_OVERLAY_R1
_core.FINAL_OVERLAYS = FINAL_OVERLAYS
_core.ALL_OVERLAY_NAMES = ALL_OVERLAY_NAMES
_core.CONTROL_PATHS = CONTROL_PATHS

ARTIFACT_FIELDS = _base.ARTIFACT_FIELDS
B1A_SCHEMAS = _base.B1A_SCHEMAS
expected_manifest = _base.expected_manifest
load_effective_manifest = _base.load_effective_manifest
