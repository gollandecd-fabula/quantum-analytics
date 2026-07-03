from __future__ import annotations

from pathlib import Path
from typing import Any

from ._manifest_loader import load_runner_bundle


def validate_manifest(manifest_path: Path) -> dict[str, Any]:
    bundle = load_runner_bundle(manifest_path)
    return {
        "schema_version": "quantum-local-pilot-validation-v1",
        "status": "VALID",
        "run_id": bundle.run_id,
        "dataset_id": bundle.declaration.dataset_id,
        "original_file_sha256": bundle.declaration.original_file_sha256,
        "source_size_bytes": len(bundle.payload),
        "finance_labels": sorted(bundle.finance_requests),
        "release_state": "RELEASE_BLOCKED",
    }


__all__ = ["validate_manifest"]
