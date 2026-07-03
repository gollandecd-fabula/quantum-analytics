from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

from quantum.ingestion.receipts import UploadReceiptRegistry

from ._atomic_io import atomic_write
from ._scope import LocalPilotExecutionError
from ._workspace_layout import WorkspaceLayout


def _write_once(path: Path, payload: bytes) -> None:
    if path.exists():
        raise LocalPilotExecutionError("PILOT_WORKSPACE_CONTENT_EXISTS")
    atomic_write(path, payload)
    stored = path.read_bytes()
    if len(stored) != len(payload) or sha256(stored).digest() != sha256(payload).digest():
        raise LocalPilotExecutionError("PILOT_WORKSPACE_INTEGRITY_FAILED")


def stage_payload(
    layout: WorkspaceLayout,
    *,
    payload: bytes,
    filename: str,
) -> dict[str, Any]:
    if not isinstance(payload, bytes) or not payload:
        raise LocalPilotExecutionError("PILOT_RAW_BYTES_REQUIRED")
    safe_name = UploadReceiptRegistry.sanitize_filename(filename)
    digest = sha256(payload).hexdigest()
    raw_path = layout.raw / digest
    _write_once(raw_path, payload)
    _write_once(layout.quarantine / digest, payload)
    key = raw_path.relative_to(layout.base).as_posix()
    return {
        "sha256": digest,
        "size_bytes": len(payload),
        "filename_sha256": sha256(safe_name.encode("utf-8")).hexdigest(),
        "storage_key_sha256": sha256(key.encode("utf-8")).hexdigest(),
    }


def promote_payload(
    layout: WorkspaceLayout,
    *,
    payload: bytes,
    expected_sha256: str,
) -> Path:
    if sha256(payload).hexdigest() != expected_sha256:
        raise LocalPilotExecutionError("PILOT_WORKSPACE_INTEGRITY_FAILED")
    path = layout.admitted / expected_sha256
    _write_once(path, payload)
    return path


__all__ = ["promote_payload", "stage_payload"]
