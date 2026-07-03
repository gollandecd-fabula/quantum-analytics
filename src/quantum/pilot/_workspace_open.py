from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from ._manifest_common import text
from ._path_safety import reject_symlinks, require_descendant
from ._scope import LocalPilotExecutionError
from ._workspace_layout import ZONE_NAMES, WorkspaceLayout, layout_from_root


def open_workspace(
    *,
    base: Path,
    tenant_id: str,
    run_id: str,
) -> WorkspaceLayout:
    normalized_run = text(run_id, "PILOT_RUN_ID_INVALID")
    tenant_hash = sha256(tenant_id.encode("utf-8")).hexdigest()
    base_resolved = base.resolve()
    root = require_descendant(
        base_resolved,
        base_resolved / "runs" / tenant_hash / normalized_run,
    )
    reject_symlinks(root)
    layout = layout_from_root(base_resolved, root)
    try:
        marker = json.loads(layout.marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalPilotExecutionError("PILOT_WORKSPACE_MARKER_INVALID") from exc
    if (
        marker.get("schema_version") != "quantum-local-pilot-workspace-v1"
        or marker.get("run_id") != normalized_run
        or marker.get("tenant_id_sha256") != tenant_hash
    ):
        raise LocalPilotExecutionError("PILOT_WORKSPACE_MARKER_INVALID")
    if any(not getattr(layout, name).is_dir() for name in ZONE_NAMES):
        raise LocalPilotExecutionError("PILOT_WORKSPACE_LAYOUT_INVALID")
    return layout


__all__ = ["open_workspace"]
