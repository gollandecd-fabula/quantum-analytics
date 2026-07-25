from __future__ import annotations

from collections import deque
import os
from pathlib import Path


class SequentialImportQueue:
    """Deterministic one-at-a-time queue with lifetime duplicate protection."""

    def __init__(self) -> None:
        self._pending: deque[str] = deque()
        self._active: str | None = None
        self._source_keys: dict[str, str] = {}

    @staticmethod
    def source_key(path: Path) -> str:
        return os.path.normcase(str(path.resolve()))

    @property
    def active(self) -> str | None:
        return self._active

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def is_busy(self) -> bool:
        return self._active is not None or bool(self._pending)

    def add(self, row_id: str, source_path: Path) -> bool:
        key = self.source_key(source_path)
        if key in self._source_keys.values():
            return False
        self._source_keys[row_id] = key
        self._pending.append(row_id)
        return True

    def requeue(self, row_id: str) -> bool:
        if row_id not in self._source_keys:
            return False
        if row_id == self._active or row_id in self._pending:
            return False
        self._pending.append(row_id)
        return True

    def enqueue_existing(self, row_id: str, source_path: Path) -> bool:
        """Queue a restored row while preserving duplicate-source protection."""
        if row_id == self._active or row_id in self._pending:
            return False
        key = self.source_key(source_path)
        owner = next(
            (
                known_id
                for known_id, known_key in self._source_keys.items()
                if known_key == key
            ),
            None,
        )
        if owner is not None and owner != row_id:
            return False
        self._source_keys[row_id] = key
        self._pending.append(row_id)
        return True

    def start_next(self) -> str | None:
        if self._active is not None or not self._pending:
            return None
        self._active = self._pending.popleft()
        return self._active

    def complete(self, row_id: str) -> None:
        if self._active == row_id:
            self._active = None

    def cancel_pending(self) -> tuple[str, ...]:
        cancelled = tuple(self._pending)
        self._pending.clear()
        return cancelled

    def forget(self, row_id: str) -> bool:
        if row_id == self._active or row_id in self._pending:
            return False
        return self._source_keys.pop(row_id, None) is not None
