from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

MARKER_NAME = ".quantum-local-pilot-v1.json"
ZONE_NAMES = ("raw", "quarantine", "admitted", "derived", "evidence")


@dataclass(frozen=True, slots=True)
class WorkspaceLayout:
    base: Path
    root: Path
    raw: Path
    quarantine: Path
    admitted: Path
    derived: Path
    evidence: Path
    marker: Path


def layout_from_root(base: Path, root: Path) -> WorkspaceLayout:
    zones = {name: root / name for name in ZONE_NAMES}
    return WorkspaceLayout(
        base=base,
        root=root,
        raw=zones["raw"],
        quarantine=zones["quarantine"],
        admitted=zones["admitted"],
        derived=zones["derived"],
        evidence=zones["evidence"],
        marker=root / MARKER_NAME,
    )


__all__ = ["MARKER_NAME", "ZONE_NAMES", "WorkspaceLayout", "layout_from_root"]
