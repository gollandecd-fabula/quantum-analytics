from __future__ import annotations

from pathlib import Path
from typing import Any

from ._atomic_io import atomic_json
from ._workspace_layout import WorkspaceLayout


def write_outputs(
    layout: WorkspaceLayout,
    *,
    operator_result: Any,
    evidence: Any,
) -> tuple[Path, Path]:
    result_path = layout.derived / "operator-result.json"
    evidence_path = layout.evidence / "pilot-evidence.json"
    atomic_json(result_path, operator_result)
    atomic_json(evidence_path, evidence)
    return result_path, evidence_path


def write_failure(layout: WorkspaceLayout, *, code: str) -> Path:
    path = layout.evidence / "failure.json"
    atomic_json(
        path,
        {
            "schema_version": "quantum-local-pilot-failure-v1",
            "error_code": code,
            "release_state": "RELEASE_BLOCKED",
        },
    )
    return path


__all__ = ["write_failure", "write_outputs"]
