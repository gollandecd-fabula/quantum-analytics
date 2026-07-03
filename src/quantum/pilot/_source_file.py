from __future__ import annotations

from pathlib import Path

from ._path_safety import require_descendant
from ._scope import LocalPilotExecutionError

_ALLOWED_SUFFIXES = {".xlsx", ".zip"}


def read_source_file(
    *,
    manifest_path: Path,
    source_file: object,
    max_file_bytes: int,
) -> tuple[Path, bytes]:
    if not isinstance(source_file, str) or not source_file:
        raise LocalPilotExecutionError("PILOT_SOURCE_FILE_INVALID")
    relative = Path(source_file)
    if relative.is_absolute():
        raise LocalPilotExecutionError("PILOT_SOURCE_FILE_INVALID")
    base = manifest_path.resolve().parent
    source = require_descendant(base, base / relative)
    if source.is_symlink() or not source.is_file():
        raise LocalPilotExecutionError("PILOT_SOURCE_FILE_INVALID")
    if source.suffix.casefold() not in _ALLOWED_SUFFIXES:
        raise LocalPilotExecutionError("PILOT_SOURCE_FILE_INVALID")
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise LocalPilotExecutionError("PILOT_SOURCE_FILE_READ_FAILED") from exc
    if size < 1 or size > max_file_bytes:
        raise LocalPilotExecutionError("PILOT_SOURCE_FILE_SIZE_INVALID")
    try:
        payload = source.read_bytes()
    except OSError as exc:
        raise LocalPilotExecutionError("PILOT_SOURCE_FILE_READ_FAILED") from exc
    if len(payload) != size:
        raise LocalPilotExecutionError("PILOT_SOURCE_FILE_READ_FAILED")
    return source, payload


__all__ = ["read_source_file"]
