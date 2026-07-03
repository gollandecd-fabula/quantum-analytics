from __future__ import annotations

from tests import integration_manifest_support_v5 as _previous

_base = _previous._base
FINAL_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{n}.json"
    for n in range(1, 29)
)
_base.FINAL_NAMES = FINAL_NAMES
_base.FINAL_OVERLAY_R1 = FINAL_NAMES[0]
_base.FINAL_OVERLAYS = _base._linear(FINAL_NAMES, "unused")[1:]
_base.ALL_OVERLAY_NAMES = tuple(
    name
    for name, _ in _base.COMMON_OVERLAYS + _base.B1B_OVERLAYS + _base.P16_OVERLAYS
) + (_base.LOCAL_OVERLAY[0], *FINAL_NAMES)
_base.CONTROL_PATHS = {
    "docs/evidence/ARTIFACT_MANIFEST.json",
    *(f"docs/evidence/{name}" for name in _base.ALL_OVERLAY_NAMES),
}

ARTIFACT_FIELDS = _base.ARTIFACT_FIELDS
B1A_SCHEMAS = _base.B1A_SCHEMAS
expected_manifest = _base.expected_manifest
load_effective_manifest = _base.load_effective_manifest

__all__ = [
    "ARTIFACT_FIELDS",
    "B1A_SCHEMAS",
    "expected_manifest",
    "load_effective_manifest",
]
