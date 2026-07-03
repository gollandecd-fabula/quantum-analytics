from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from ._scope import LocalPilotExecutionError


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temp = Path(handle.name)
        try:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            os.replace(temp, path)
            try:
                path.chmod(0o600)
            except OSError:
                pass
        except Exception:
            temp.unlink(missing_ok=True)
            raise


def atomic_json(path: Path, value: Any) -> None:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise LocalPilotExecutionError("PILOT_WORKSPACE_JSON_INVALID") from exc
    atomic_write(path, payload)


__all__ = ["atomic_json", "atomic_write"]
