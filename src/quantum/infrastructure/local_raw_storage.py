from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import BinaryIO


class ImmutableObjectConflict(RuntimeError):
    pass


class LocalImmutableRawStorage:
    """Foundation-only immutable object store.

    This adapter is suitable for contract tests and local proof. It is not the
    production object-storage implementation.
    """

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, storage_key: str) -> Path:
        if not storage_key or storage_key.startswith(("/", "\\")):
            raise ValueError("storage_key must be a non-empty relative path.")
        candidate = (self._root / storage_key).resolve()
        if self._root not in candidate.parents:
            raise ValueError("storage_key escapes raw-storage root.")
        return candidate

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def put_immutable(
        self,
        *,
        storage_key: str,
        stream: BinaryIO,
        expected_sha256: str,
    ) -> Path:
        if len(expected_sha256) != 64:
            raise ValueError("expected_sha256 must be a SHA-256 hex digest.")
        int(expected_sha256, 16)

        destination = self._safe_path(storage_key)
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists():
            actual_existing = self._file_sha256(destination)
            if actual_existing != expected_sha256:
                raise ImmutableObjectConflict(
                    "Immutable storage key already exists with different bytes."
                )
            return destination

        temporary = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
        digest = hashlib.sha256()
        try:
            with temporary.open("xb") as output:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
                    output.write(block)
                output.flush()
                os.fsync(output.fileno())

            actual = digest.hexdigest()
            if actual != expected_sha256:
                raise ValueError(
                    f"SHA-256 mismatch: expected {expected_sha256}, got {actual}."
                )

            # Hard-link publication provides create-if-absent semantics on one filesystem.
            try:
                os.link(temporary, destination)
            except FileExistsError:
                actual_existing = self._file_sha256(destination)
                if actual_existing != expected_sha256:
                    raise ImmutableObjectConflict(
                        "Concurrent immutable write produced different bytes."
                    )
            return destination
        finally:
            temporary.unlink(missing_ok=True)

    def open_read(self, *, storage_key: str) -> BinaryIO:
        return self._safe_path(storage_key).open("rb")
