from __future__ import annotations

import os
from pathlib import Path
import tempfile

from quantum.ingestion import LocalRawStorage


def _storage_atomic_write(
    cls: type[LocalRawStorage],
    path: Path,
    payload: bytes,
) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name == "nt":
            return
        cls._fsync_directory(path.parent)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def install_windows_storage_compatibility() -> None:
    LocalRawStorage._atomic_write = classmethod(_storage_atomic_write)
