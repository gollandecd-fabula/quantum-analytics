from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from quantum.application._finance_center_auto_inbox import (
    AutoInboxController as _BaseAutoInboxController,
    AutoInboxError,
    FinanceCenterAutoInboxMixin as _BaseFinanceCenterAutoInboxMixin,
    _inside,
    _sha256_file,
    _valid_digest,
)


_MAX_RECORDS = 2048
_TERMINAL_RECORD_STATUSES = frozenset({"COMPLETED", "REJECTED", "DUPLICATE"})


class AutoInboxController(_BaseAutoInboxController):
    """M4 corrective controller with bounded state and post-move hash binding."""

    def _load_state(self) -> dict[str, Any]:
        value = super()._load_state()
        if len(value["records"]) > _MAX_RECORDS:
            raise AutoInboxError("AUTO_INBOX_STATE_RECORD_LIMIT_EXCEEDED")
        return value

    def _ensure_record_capacity(self, digest: str) -> None:
        records = self._state["records"]
        if digest in records or len(records) < _MAX_RECORDS:
            return
        terminal = sorted(
            (
                int(record.get("updated_at_unix_ns") or 0),
                current_digest,
                record,
            )
            for current_digest, record in records.items()
            if isinstance(record, dict)
            and record.get("status") in _TERMINAL_RECORD_STATUSES
        )
        if not terminal:
            raise AutoInboxError("AUTO_INBOX_STATE_CAPACITY_EXHAUSTED")
        _, removed_digest, removed = terminal[0]
        records.pop(removed_digest)
        self._append_event(
            "RECORD_PRUNED",
            sha256=removed_digest,
            status=removed.get("status"),
            internal_path=removed.get("internal_path"),
            reason="BOUNDED_STATE_RETENTION",
        )

    def _set_record(
        self,
        digest: str,
        *,
        status: str,
        source_name: str,
        path: Path,
        reason: str | None = None,
    ) -> None:
        self._ensure_record_capacity(digest)
        super()._set_record(
            digest,
            status=status,
            source_name=source_name,
            path=path,
            reason=reason,
        )

    def archive_duplicate(self, path: Path, digest: str) -> Path:
        if not _valid_digest(digest) or _sha256_file(path) != digest:
            raise AutoInboxError("AUTO_INBOX_DUPLICATE_HASH_MISMATCH")
        target = self._destination(
            self.completed_dir,
            f"duplicate__{digest[:16]}",
            path.name,
        )
        try:
            os.replace(path, target)
        except OSError as exc:
            raise AutoInboxError(
                "AUTO_INBOX_DUPLICATE_ARCHIVE_FAILED",
                (type(exc).__name__,),
            ) from exc
        self._observations.pop(str(path.absolute()), None)

        moved_digest = _sha256_file(target)
        if moved_digest != digest:
            rejected = self._destination(
                self.rejected_dir,
                f"duplicate-hash-mismatch__{digest[:16]}",
                path.name,
            )
            try:
                os.replace(target, rejected)
            except OSError as exc:
                raise AutoInboxError(
                    "AUTO_INBOX_DUPLICATE_HASH_MISMATCH_UNRECOVERABLE",
                    (type(exc).__name__,),
                ) from exc
            self._append_event(
                "DUPLICATE_HASH_MISMATCH",
                expected_sha256=digest,
                actual_sha256=moved_digest,
                internal_path=self.relative_internal(rejected),
            )
            self._write_state()
            raise AutoInboxError("AUTO_INBOX_DUPLICATE_HASH_MISMATCH")

        existing = self._state["records"].get(digest)
        if isinstance(existing, dict) and existing.get("status") in {
            "CLAIMED",
            "QUEUED",
            "COMPLETED",
            "DUPLICATE",
        }:
            self._append_event(
                "DUPLICATE_ARCHIVED",
                sha256=digest,
                internal_path=self.relative_internal(target),
                canonical_status=existing.get("status"),
            )
            self._write_state()
        else:
            self._record(
                digest,
                status="DUPLICATE",
                source_name=path.name,
                path=target,
                reason="ALREADY_IMPORTED_OR_QUEUED",
            )
        return target


class FinanceCenterAutoInboxMixin(_BaseFinanceCenterAutoInboxMixin):
    def _initialize_auto_inbox(self) -> None:
        self.auto_inbox: AutoInboxController | None = None
        self.auto_inbox_error: str | None = None
        try:
            self.auto_inbox = AutoInboxController(
                self.project_root / "data" / "auto-inbox"
            )
        except AutoInboxError as exc:
            self.auto_inbox_error = exc.code
        self.auto_inbox_poll_ms = 1000


__all__ = [
    "AutoInboxController",
    "AutoInboxError",
    "FinanceCenterAutoInboxMixin",
]
