from __future__ import annotations

from pathlib import Path

from ._scope import LocalPilotExecutionError


def require_descendant(base: Path, candidate: Path) -> Path:
    base_resolved = base.resolve()
    candidate_resolved = candidate.resolve()
    try:
        candidate_resolved.relative_to(base_resolved)
    except ValueError as exc:
        raise LocalPilotExecutionError("PILOT_WORKSPACE_PATH_ESCAPE") from exc
    return candidate_resolved


def reject_symlinks(root: Path) -> None:
    if root.is_symlink():
        raise LocalPilotExecutionError("PILOT_WORKSPACE_SYMLINK_FORBIDDEN")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise LocalPilotExecutionError("PILOT_WORKSPACE_SYMLINK_FORBIDDEN")


__all__ = ["reject_symlinks", "require_descendant"]
