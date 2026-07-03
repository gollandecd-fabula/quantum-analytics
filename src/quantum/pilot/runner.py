from __future__ import annotations

from pathlib import Path
from typing import Any

from ._manifest_loader import load_runner_bundle
from ._runner_execute import execute_runner_bundle


def run_manifest(manifest_path: Path, *, workspace_base: Path) -> dict[str, Any]:
    bundle = load_runner_bundle(manifest_path)
    return execute_runner_bundle(bundle, workspace_base=workspace_base)


__all__ = ["run_manifest"]
