from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping


class AnyFileError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class Detection:
    kind: str
    media_type: str
    workbook_payload: bytes | None = None
    archive_entries: int = 0


def atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8")
    atomic_bytes(path.resolve(), encoded)


def safe_filename(name: str) -> str:
    candidate = Path(name).name.strip()
    candidate = "".join(
        "_" if ord(char) < 32 or char in '<>:"/\\|?*' else char
        for char in candidate
    )
    candidate = candidate.strip(" .")
    return (candidate or "source.bin")[:180]


def store_original(
    *, storage_root: Path, payload: bytes, digest: str, zone: str
) -> tuple[str, bool]:
    relative = Path("intake") / zone / digest[:2] / digest
    target = storage_root.resolve() / relative
    duplicate = target.exists()
    if duplicate:
        if sha256(target.read_bytes()).hexdigest() != digest:
            raise AnyFileError("ANY_FILE_STORED_DIGEST_MISMATCH")
    else:
        atomic_bytes(target, payload)
    return relative.as_posix(), duplicate
