from __future__ import annotations

from collections.abc import Iterable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import BinaryIO, Protocol

from quantum.domain.events import CanonicalEvent


class RawStorage(Protocol):
    def put_immutable(
        self,
        *,
        storage_key: str,
        stream: BinaryIO,
        expected_sha256: str,
    ) -> Path:
        """Store bytes exactly once, or return existing identical object."""

    def open_read(self, *, storage_key: str) -> BinaryIO:
        """Open an existing immutable object for reading."""


class CanonicalEventRepository(Protocol):
    def add(self, event: CanonicalEvent) -> None:
        """Persist one canonical event under durable uniqueness constraints."""

    def get_by_idempotency_key(self, key: str) -> CanonicalEvent | None:
        """Return existing event for idempotent replay."""

    def list_by_business_key(self, stable_business_key: str) -> Iterable[CanonicalEvent]:
        """Return complete immutable history for one business key."""


class UnitOfWork(AbstractContextManager["UnitOfWork"], Protocol):
    events: CanonicalEventRepository

    def commit(self) -> None:
        """Commit one atomic publication unit."""

    def rollback(self) -> None:
        """Rollback uncommitted work."""
