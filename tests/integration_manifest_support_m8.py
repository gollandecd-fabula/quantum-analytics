from __future__ import annotations

from tests import integration_manifest_support_m7 as _base


_core = _base._base._base
PRODUCT_BASE_NAMES = tuple(
    f"ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R{number}.json"
    for number in range(1, 100)
)
FINAL_NAMES = PRODUCT_BASE_NAMES
FINAL_OVERLAY_R1 = PRODUCT_BASE_NAMES[0]
PRODUCT_BASE_OVERLAYS = _core._linear(PRODUCT_BASE_NAMES, "unused")[1:]
GOVERNANCE_OVERLAY = (
    "ARTIFACT_MANIFEST_OVERLAY_WB_RELEASE_R2_GOV_R1.json",
    "base_pilot_integration_r99_overlay_git_blob_sha",
)
R100_OVERLAY = (
    "ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R100.json",
    "base_pilot_integration_r99_overlay_git_blob_sha",
)
M5_CLOSURE_OVERLAY = (
    "ARTIFACT_MANIFEST_OVERLAY_WBR2_M5_CLOSURE_R1.json",
    "base_m5_r100_overlay_git_blob_sha",
)
M5_CLOSURE_CORRECTIVE_R2_OVERLAY = (
    "ARTIFACT_MANIFEST_OVERLAY_WBR2_M5_CLOSURE_R2.json",
    "base_m5_closure_r1_overlay_git_blob_sha",
)
FULL_PROJECT_REDTEAM_R1_OVERLAY = (
    "ARTIFACT_MANIFEST_OVERLAY_FULL_PROJECT_REDTEAM_R1.json",
    "base_wbr2_m5_closure_r2_overlay_git_blob_sha",
)
UNIVERSAL_PARTIAL_R1_OVERLAY = (
    "ARTIFACT_MANIFEST_OVERLAY_UNIVERSAL_PARTIAL_R1.json",
    "base_full_project_redteam_r1_overlay_git_blob_sha",
)
XLSX_NAMESPACE_FALLBACK_R1_OVERLAY = (
    "ARTIFACT_MANIFEST_OVERLAY_XLSX_NAMESPACE_FALLBACK_R1.json",
    "base_universal_partial_r1_overlay_git_blob_sha",
)
ALL_OVERLAY_NAMES = tuple(
    name
    for name, _ in (
        _core.COMMON_OVERLAYS + _core.B1B_OVERLAYS + _core.P16_OVERLAYS
    )
) + (
    _core.LOCAL_OVERLAY[0],
    *PRODUCT_BASE_NAMES,
    GOVERNANCE_OVERLAY[0],
    R100_OVERLAY[0],
    M5_CLOSURE_OVERLAY[0],
    M5_CLOSURE_CORRECTIVE_R2_OVERLAY[0],
    FULL_PROJECT_REDTEAM_R1_OVERLAY[0],
    UNIVERSAL_PARTIAL_R1_OVERLAY[0],
    XLSX_NAMESPACE_FALLBACK_R1_OVERLAY[0],
)
CONTROL_PATHS = {
    "docs/evidence/ARTIFACT_MANIFEST.json",
    *(f"docs/evidence/{name}" for name in ALL_OVERLAY_NAMES),
}

# Historical product evidence remains linear through R99. GOV-R1 and R100 are
# parallel branches from immutable R99. M5 closure R1, corrective R2 and this
# full-project Red Team and Universal Partial R1 overlays form an append-only
# governance/product-audit chain. Neither overlay changes marketplace boundaries.
_core.FINAL_NAMES = PRODUCT_BASE_NAMES
_core.FINAL_OVERLAY_R1 = FINAL_OVERLAY_R1
_core.FINAL_OVERLAYS = PRODUCT_BASE_OVERLAYS
_core.ALL_OVERLAY_NAMES = ALL_OVERLAY_NAMES
_core.CONTROL_PATHS = CONTROL_PATHS

ARTIFACT_FIELDS = _base.ARTIFACT_FIELDS
B1A_SCHEMAS = _base.B1A_SCHEMAS
expected_manifest = _base.expected_manifest


def _apply_parallel_overlay(
    artifacts: dict[str, list],
    overlay_spec: tuple[str, str],
    anchor_raw: bytes,
) -> None:
    name, field = overlay_spec
    _, overlay = _core._read_overlay(name)
    if overlay[field] != _core.git_blob_sha(anchor_raw):
        raise AssertionError(
            "ARTIFACT_MANIFEST_OVERLAY_BASE_MISMATCH:" + name
        )
    _core.apply_entries(artifacts, overlay)


def load_effective_manifest() -> dict:
    current = _base.load_effective_manifest()
    artifacts = {row[0]: row for row in current["artifacts"]}
    evidence = _core.ROOT / "docs/evidence"
    r99_raw = (
        evidence / "ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R99.json"
    ).read_bytes()
    r100_raw = (
        evidence / "ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R100.json"
    ).read_bytes()
    closure_r1_raw = (
        evidence / "ARTIFACT_MANIFEST_OVERLAY_WBR2_M5_CLOSURE_R1.json"
    ).read_bytes()
    closure_r2_raw = (
        evidence / "ARTIFACT_MANIFEST_OVERLAY_WBR2_M5_CLOSURE_R2.json"
    ).read_bytes()
    full_redteam_raw = (
        evidence / "ARTIFACT_MANIFEST_OVERLAY_FULL_PROJECT_REDTEAM_R1.json"
    ).read_bytes()
    universal_partial_raw = (
        evidence / "ARTIFACT_MANIFEST_OVERLAY_UNIVERSAL_PARTIAL_R1.json"
    ).read_bytes()

    _apply_parallel_overlay(artifacts, GOVERNANCE_OVERLAY, r99_raw)
    _apply_parallel_overlay(artifacts, R100_OVERLAY, r99_raw)
    _apply_parallel_overlay(artifacts, M5_CLOSURE_OVERLAY, r100_raw)
    _apply_parallel_overlay(
        artifacts,
        M5_CLOSURE_CORRECTIVE_R2_OVERLAY,
        closure_r1_raw,
    )
    _apply_parallel_overlay(
        artifacts,
        FULL_PROJECT_REDTEAM_R1_OVERLAY,
        closure_r2_raw,
    )
    _apply_parallel_overlay(
        artifacts,
        UNIVERSAL_PARTIAL_R1_OVERLAY,
        full_redteam_raw,
    )
    _apply_parallel_overlay(
        artifacts,
        XLSX_NAMESPACE_FALLBACK_R1_OVERLAY,
        universal_partial_raw,
    )

    current["artifacts"] = [artifacts[path] for path in sorted(artifacts)]
    current["artifact_count"] = len(current["artifacts"])
    return current
