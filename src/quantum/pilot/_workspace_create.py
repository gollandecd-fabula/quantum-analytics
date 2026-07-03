from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from ._atomic_io import atomic_json
from ._manifest_common import text
from ._path_safety import require_descendant
from ._scope import LocalPilotExecutionError
from ._workspace_layout import ZONE_NAMES, WorkspaceLayout, layout_from_root


def create_workspace(
    *,
    base: Path,
    tenant_id: str,
    run_id: str,
    dataset_id: str,
) -> WorkspaceLayout:
    if not isinstance(base, Path):
        raise LocalPilotExecutionError("PILOT_WORKSPACE_BASE_INVALID")
    normalized_run = text(run_id, "PILOT_RUN_ID_INVALID")
    tenant_hash = sha256(tenant_id.encode("utf-8")).hexdigest()
    base_resolved = base.resolve()
    base_resolved.mkdir(mode=0o700, parents=True, exist_ok=True)
    root = require_descendant(
        base_resolved,
        base_resolved / "runs" / tenant_hash / normalized_run,
    )
    if root.exists():
        raise LocalPilotExecutionError("PILOT_WORKSPACE_EXISTS")
    layout = layout_from_root(base_resolved, root)
    for name in ZONE_NAMES:
        getattr(layout, name).mkdir(mode=0o700, parents=True, exist_ok=False)
    atomic_json(
        layout.marker,
        {
            "schema_version": "quantum-local-pilot-workspace-v1",
            "run_id": normalized_run,
            "tenant_id_sha256": tenant_hash,
            "dataset_id": dataset_id,
        },
    )
    return layout


__all__ = ["create_workspace"]
