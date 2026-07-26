from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any

from quantum.application._finance_center_shared import *


_AUTO_INBOX_SCHEMA = "quantum-auto-inbox-v1"
_SUPPORTED_SUFFIXES = frozenset(
    {
        ".xls", ".xlsx", ".xlsm", ".csv", ".tsv", ".json", ".xml",
        ".zip", ".tar", ".gz", ".tgz", ".bz2", ".tbz", ".tbz2",
        ".xz", ".txz", ".7z", ".rar",
    }
)
_IGNORED_SUFFIXES = frozenset({".tmp", ".part", ".crdownload"})
_MAX_FILE_BYTES = 100 * 1024 * 1024
_MAX_STATE_BYTES = 2 * 1024 * 1024
_MAX_EVENTS = 200
_RECORD_STATUSES = frozenset(
    {"RECOVERED", "CLAIMED", "QUEUED", "COMPLETED", "REJECTED", "DUPLICATE"}
)


class AutoInboxError(RuntimeError):
    def __init__(self, code: str, details: tuple[str, ...] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


@dataclass(frozen=True, slots=True)
class AutoInboxCandidate:
    path: Path
    size_bytes: int
    mtime_ns: int


@dataclass(slots=True)
class _Observation:
    size_bytes: int
    mtime_ns: int
    stable_scans: int


def _valid_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _sha256_file(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
    except OSError as exc:
        raise AutoInboxError(
            "AUTO_INBOX_FILE_READ_FAILED",
            (type(exc).__name__,),
        ) from exc
    return digest.hexdigest()


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-zА-Яа-яЁё._-]+", "_", name).strip("._")
    return (cleaned or "report")[:96]


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class AutoInboxController:
    """Stable-file inbox with persistent digest and outcome tracking."""

    def __init__(
        self,
        root: Path,
        *,
        minimum_age_seconds: float = 2.0,
        stable_scans_required: int = 2,
    ) -> None:
        self.root = root.resolve()
        self.incoming_dir = self.root / "incoming"
        self.processing_dir = self.root / "processing"
        self.completed_dir = self.root / "completed"
        self.rejected_dir = self.root / "rejected"
        self.review_dir = self.root / "review-required"
        self.state_path = self.root / "state.json"
        self.minimum_age_ns = max(0, int(minimum_age_seconds * 1_000_000_000))
        self.stable_scans_required = max(2, stable_scans_required)
        self._observations: dict[str, _Observation] = {}
        self._ensure_directories()
        self._state = self._load_state()
        self._recover_processing()

    def _ensure_directories(self) -> None:
        for path in (
            self.incoming_dir,
            self.processing_dir,
            self.completed_dir,
            self.rejected_dir,
            self.review_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _empty_state(self) -> dict[str, Any]:
        return {
            "schema_version": _AUTO_INBOX_SCHEMA,
            "records": {},
            "events": [],
            "marketplace_write_enabled": False,
            "release_scope": "WB_ONLY",
        }

    def relative_internal(self, path: Path) -> str:
        try:
            absolute = path.absolute()
            return absolute.relative_to(self.root).as_posix()
        except (OSError, ValueError) as exc:
            raise AutoInboxError("AUTO_INBOX_PATH_OUTSIDE_ROOT") from exc

    def resolve_internal(
        self,
        raw: object,
        *,
        required_parent: Path | None = None,
    ) -> Path:
        if not isinstance(raw, str) or not raw.strip():
            raise AutoInboxError("AUTO_INBOX_INTERNAL_PATH_REQUIRED")
        relative = Path(raw.strip())
        if relative.is_absolute() or ".." in relative.parts:
            raise AutoInboxError("AUTO_INBOX_INTERNAL_PATH_INVALID")
        candidate = (self.root / relative).resolve()
        if not _inside(candidate, self.root):
            raise AutoInboxError("AUTO_INBOX_INTERNAL_PATH_INVALID")
        if required_parent is not None and not _inside(candidate, required_parent):
            raise AutoInboxError("AUTO_INBOX_INTERNAL_PATH_INVALID")
        return candidate

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return self._empty_state()
        try:
            if self.state_path.stat().st_size > _MAX_STATE_BYTES:
                raise AutoInboxError("AUTO_INBOX_STATE_TOO_LARGE")
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except AutoInboxError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AutoInboxError(
                "AUTO_INBOX_STATE_READ_FAILED",
                (type(exc).__name__,),
            ) from exc
        if not isinstance(value, dict):
            raise AutoInboxError("AUTO_INBOX_STATE_INVALID")
        if value.get("schema_version") != _AUTO_INBOX_SCHEMA:
            raise AutoInboxError("AUTO_INBOX_STATE_VERSION_UNSUPPORTED")
        records = value.get("records")
        events = value.get("events")
        if not isinstance(records, dict) or not isinstance(events, list):
            raise AutoInboxError("AUTO_INBOX_STATE_INVALID")
        if len(events) > _MAX_EVENTS:
            raise AutoInboxError("AUTO_INBOX_STATE_INVALID")
        if value.get("marketplace_write_enabled") is not False:
            raise AutoInboxError("AUTO_INBOX_WRITES_MUST_BE_DISABLED")
        if value.get("release_scope") != "WB_ONLY":
            raise AutoInboxError("AUTO_INBOX_SCOPE_INVALID")
        for digest, record in records.items():
            if not _valid_digest(digest) or not isinstance(record, dict):
                raise AutoInboxError("AUTO_INBOX_STATE_INVALID")
            if record.get("sha256") != digest:
                raise AutoInboxError("AUTO_INBOX_STATE_INVALID")
            if record.get("status") not in _RECORD_STATUSES:
                raise AutoInboxError("AUTO_INBOX_STATE_INVALID")
            if record.get("marketplace_write_enabled") is not False:
                raise AutoInboxError("AUTO_INBOX_WRITES_MUST_BE_DISABLED")
            self.resolve_internal(record.get("internal_path"))
        return value

    def _write_state(self) -> None:
        payload = json.dumps(
            self._state,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
        if len(payload) > _MAX_STATE_BYTES:
            raise AutoInboxError("AUTO_INBOX_STATE_TOO_LARGE")
        self.root.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.root,
                prefix=".auto-inbox-state-",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.state_path)
            temporary = None
            _fsync_directory(self.root)
        except OSError as exc:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise AutoInboxError(
                "AUTO_INBOX_STATE_WRITE_FAILED",
                (type(exc).__name__,),
            ) from exc

    def _append_event(self, event: str, **fields: Any) -> None:
        events = self._state["events"]
        events.append(
            {
                "event": event,
                "recorded_at_unix_ns": time.time_ns(),
                **fields,
            }
        )
        del events[:-_MAX_EVENTS]

    def _set_record(
        self,
        digest: str,
        *,
        status: str,
        source_name: str,
        path: Path,
        reason: str | None = None,
    ) -> None:
        if not _valid_digest(digest) or status not in _RECORD_STATUSES:
            raise AutoInboxError("AUTO_INBOX_RECORD_INVALID")
        internal_path = self.relative_internal(path)
        records = self._state["records"]
        records[digest] = {
            "sha256": digest,
            "status": status,
            "source_name": Path(source_name).name or "report",
            "internal_path": internal_path,
            "reason": reason,
            "updated_at_unix_ns": time.time_ns(),
            "marketplace_write_enabled": False,
        }
        self._append_event(
            "STATUS",
            sha256=digest,
            status=status,
            internal_path=internal_path,
            reason=reason,
        )

    def _record(self, digest: str, **fields: Any) -> None:
        self._set_record(digest, **fields)
        self._write_state()

    def _destination(self, directory: Path, prefix: str, source_name: str) -> Path:
        if not _inside(directory, self.root):
            raise AutoInboxError("AUTO_INBOX_DESTINATION_OUTSIDE_ROOT")
        base = directory / f"{prefix}__{_safe_name(source_name)}"
        if not base.exists():
            return base
        for index in range(1, 1000):
            candidate = directory / f"{prefix}__{index:03d}__{_safe_name(source_name)}"
            if not candidate.exists():
                return candidate
        raise AutoInboxError("AUTO_INBOX_DESTINATION_EXHAUSTED")

    def _recover_processing(self) -> None:
        changed = False
        for path in sorted(self.processing_dir.iterdir()):
            if not path.is_file() or path.is_symlink():
                continue
            digest = _sha256_file(path)
            record = self._state["records"].get(digest)
            canonical_done = (
                isinstance(record, dict)
                and record.get("status") in {"COMPLETED", "DUPLICATE"}
            )
            if canonical_done:
                target = self._destination(
                    self.completed_dir,
                    f"recovered-duplicate__{digest[:16]}",
                    path.name,
                )
            else:
                target = self._destination(
                    self.incoming_dir,
                    "recovered",
                    path.name,
                )
            try:
                os.replace(path, target)
            except OSError as exc:
                raise AutoInboxError(
                    "AUTO_INBOX_RECOVERY_FAILED",
                    (type(exc).__name__,),
                ) from exc
            if canonical_done:
                self._append_event(
                    "RECOVERED_DUPLICATE",
                    sha256=digest,
                    internal_path=self.relative_internal(target),
                )
            else:
                self._set_record(
                    digest,
                    status="RECOVERED",
                    source_name=path.name,
                    path=target,
                    reason="PROCESS_INTERRUPTED",
                )
            changed = True
        if changed:
            self._write_state()

    def scan(self, *, now_ns: int | None = None) -> tuple[AutoInboxCandidate, ...]:
        now_ns = time.time_ns() if now_ns is None else now_ns
        ready: list[AutoInboxCandidate] = []
        seen: set[str] = set()
        for path in sorted(self.incoming_dir.iterdir(), key=lambda item: item.name.lower()):
            key = str(path.absolute())
            seen.add(key)
            if path.is_symlink():
                self.defer(path, "AUTO_INBOX_SYMLINK_REJECTED")
                continue
            if not path.is_file():
                continue
            lower_name = path.name.lower()
            if lower_name.startswith("~$") or path.suffix.lower() in _IGNORED_SUFFIXES:
                continue
            if path.suffix.lower() not in _SUPPORTED_SUFFIXES:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size <= 0:
                continue
            if stat.st_size > _MAX_FILE_BYTES:
                self.defer(path, "AUTO_INBOX_FILE_TOO_LARGE")
                continue
            previous = self._observations.get(key)
            stable_scans = 1
            if (
                previous is not None
                and previous.size_bytes == stat.st_size
                and previous.mtime_ns == stat.st_mtime_ns
            ):
                stable_scans = previous.stable_scans + 1
            self._observations[key] = _Observation(
                size_bytes=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                stable_scans=stable_scans,
            )
            if (
                stable_scans >= self.stable_scans_required
                and now_ns - stat.st_mtime_ns >= self.minimum_age_ns
            ):
                ready.append(
                    AutoInboxCandidate(
                        path=path,
                        size_bytes=stat.st_size,
                        mtime_ns=stat.st_mtime_ns,
                    )
                )
        for key in tuple(self._observations):
            if key not in seen:
                self._observations.pop(key, None)
        return tuple(ready)

    def already_handled(self, digest: str) -> bool:
        record = self._state["records"].get(digest)
        if not isinstance(record, dict):
            return False
        status = record.get("status")
        if status in {"COMPLETED", "DUPLICATE"}:
            return True
        if status in {"CLAIMED", "QUEUED"}:
            try:
                return self.resolve_internal(record.get("internal_path")).is_file()
            except AutoInboxError:
                return False
        return False

    def claim(self, candidate: AutoInboxCandidate, expected_digest: str) -> Path:
        if not _valid_digest(expected_digest):
            raise AutoInboxError("AUTO_INBOX_DIGEST_INVALID")
        path = candidate.path
        try:
            before = path.stat()
        except OSError as exc:
            raise AutoInboxError(
                "AUTO_INBOX_SOURCE_UNAVAILABLE",
                (type(exc).__name__,),
            ) from exc
        if before.st_size != candidate.size_bytes or before.st_mtime_ns != candidate.mtime_ns:
            raise AutoInboxError("AUTO_INBOX_SOURCE_CHANGED")
        digest = _sha256_file(path)
        try:
            after = path.stat()
        except OSError as exc:
            raise AutoInboxError(
                "AUTO_INBOX_SOURCE_UNAVAILABLE",
                (type(exc).__name__,),
            ) from exc
        if (
            after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
            or digest != expected_digest
        ):
            raise AutoInboxError("AUTO_INBOX_SOURCE_CHANGED")
        target = self._destination(self.processing_dir, digest[:16], path.name)
        try:
            os.replace(path, target)
        except OSError as exc:
            raise AutoInboxError(
                "AUTO_INBOX_CLAIM_FAILED",
                (type(exc).__name__,),
            ) from exc
        self._observations.pop(str(path.absolute()), None)
        if _sha256_file(target) != digest:
            rejected = self._destination(
                self.rejected_dir,
                f"claim-hash-mismatch__{digest[:16]}",
                path.name,
            )
            try:
                os.replace(target, rejected)
            except OSError as exc:
                raise AutoInboxError(
                    "AUTO_INBOX_CLAIM_HASH_MISMATCH_UNRECOVERABLE",
                    (type(exc).__name__,),
                ) from exc
            self._record(
                digest,
                status="REJECTED",
                source_name=path.name,
                path=rejected,
                reason="AUTO_INBOX_CLAIM_HASH_MISMATCH",
            )
            raise AutoInboxError("AUTO_INBOX_CLAIM_HASH_MISMATCH")
        self._record(
            digest,
            status="CLAIMED",
            source_name=path.name,
            path=target,
        )
        return target

    def mark_queued(self, digest: str, processing_path: Path, source_name: str) -> None:
        if not _inside(processing_path, self.processing_dir):
            raise AutoInboxError("AUTO_INBOX_PROCESSING_PATH_INVALID")
        self._record(
            digest,
            status="QUEUED",
            source_name=source_name,
            path=processing_path,
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

    def defer(self, path: Path, reason: str) -> Path:
        target = self._destination(self.review_dir, "review", path.name)
        try:
            os.replace(path, target)
        except OSError as exc:
            raise AutoInboxError(
                "AUTO_INBOX_DEFER_FAILED",
                (type(exc).__name__,),
            ) from exc
        self._observations.pop(str(path.absolute()), None)
        self._append_event(
            "REVIEW_REQUIRED",
            internal_path=self.relative_internal(target),
            reason=reason,
        )
        self._write_state()
        return target

    def finalize(
        self,
        processing_path: Path,
        digest: str,
        *,
        success: bool,
        reason: str | None,
        source_name: str,
    ) -> Path:
        if not _valid_digest(digest):
            raise AutoInboxError("AUTO_INBOX_DIGEST_INVALID")
        resolved = processing_path.resolve()
        if not _inside(resolved, self.processing_dir):
            raise AutoInboxError("AUTO_INBOX_PROCESSING_PATH_INVALID")
        if not resolved.is_file() or resolved.is_symlink():
            raise AutoInboxError("AUTO_INBOX_PROCESSING_FILE_MISSING")
        if _sha256_file(resolved) != digest:
            raise AutoInboxError("AUTO_INBOX_PROCESSING_HASH_MISMATCH")
        destination_dir = self.completed_dir if success else self.rejected_dir
        status = "COMPLETED" if success else "REJECTED"
        target = self._destination(
            destination_dir,
            f"{status.lower()}__{digest[:16]}",
            source_name,
        )
        try:
            os.replace(resolved, target)
        except OSError as exc:
            raise AutoInboxError(
                "AUTO_INBOX_FINALIZE_FAILED",
                (type(exc).__name__,),
            ) from exc
        self._record(
            digest,
            status=status,
            source_name=source_name,
            path=target,
            reason=reason,
        )
        return target


class FinanceCenterAutoInboxMixin:
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

    def _schedule_auto_inbox_poll(self) -> None:
        if not self.closing and self.auto_inbox is not None:
            self.root_widget.after(self.auto_inbox_poll_ms, self._poll_auto_inbox)

    def _poll_auto_inbox(self) -> None:
        try:
            if self.closing or self.auto_inbox is None or self.import_queue.is_busy:
                return
            candidates = self.auto_inbox.scan()
            if not candidates:
                return
            candidates = candidates[:8]
            if not self._confirm_authority(len(candidates)):
                for candidate in candidates:
                    self.auto_inbox.defer(
                        candidate.path,
                        "AUTHORITY_NOT_CONFIRMED",
                    )
                self.set_status(
                    "Автовходящие перемещены в папку проверки: "
                    "полномочия не подтверждены.",
                    "warning",
                )
                return

            added = 0
            duplicates = 0
            deferred = 0
            for candidate in candidates:
                preview = self._review_source(
                    candidate.path,
                    authority_attested=True,
                )
                if preview is None:
                    self.auto_inbox.defer(
                        candidate.path,
                        "SCHEMA_REVIEW_NOT_CONFIRMED",
                    )
                    deferred += 1
                    continue
                digest = preview.file_sha256
                if self._loaded_digest(digest) or self.auto_inbox.already_handled(
                    digest
                ):
                    self.auto_inbox.archive_duplicate(candidate.path, digest)
                    duplicates += 1
                    continue
                processing_path = self.auto_inbox.claim(candidate, digest)
                row_id = f"report-{self.counter + 1}"
                row = ImportRow(
                    row_id=row_id,
                    source_path=processing_path,
                    size_text=str(preview.file_size_bytes),
                    status="В очереди",
                    progress="0%",
                    comment=(
                        "Автовходящие: полномочия и схема подтверждены; "
                        "ожидает последовательной обработки."
                    ),
                    details={
                        "original_source_name": candidate.path.name,
                        "selected_file_sha256": digest,
                        "authority_attested": True,
                        "schema_reviewed": preview.requires_schema_review,
                        "schema_preview": preview.to_dict(),
                        "auto_inbox": True,
                        "auto_inbox_transaction_open": True,
                        "auto_inbox_processing_path": (
                            self.auto_inbox.relative_internal(processing_path)
                        ),
                        "auto_inbox_digest": digest,
                    },
                )
                self.auto_inbox.mark_queued(
                    digest,
                    processing_path,
                    candidate.path.name,
                )
                if not self.import_queue.add(row_id, processing_path):
                    self.auto_inbox.finalize(
                        processing_path,
                        digest,
                        success=False,
                        reason="IMPORT_QUEUE_DUPLICATE",
                        source_name=candidate.path.name,
                    )
                    duplicates += 1
                    continue
                self.counter += 1
                self.reports[row_id] = ReportState(row)
                self._update_report_row(row)
                added += 1

            if added:
                self.show_page("reports")
                self.set_status(
                    f"Автовходящие добавлены в очередь: {added}; "
                    f"дубли: {duplicates}; на проверку: {deferred}.",
                    "info",
                )
                self._start_next_if_idle()
            elif duplicates or deferred:
                self.set_status(
                    f"Автовходящие: дубли {duplicates}; "
                    f"на проверку {deferred}.",
                    "info",
                )
        except AutoInboxError as exc:
            self.set_status("Автовходящие заблокированы: " + exc.code, "error")
        finally:
            self._schedule_auto_inbox_poll()

    def _finalize_auto_inbox_row(self, row: ImportRow) -> None:
        if (
            row.details.get("auto_inbox") is not True
            or row.details.get("auto_inbox_transaction_open") is not True
        ):
            return
        if self.auto_inbox is None:
            row.status = "Ошибка"
            row.progress = "Сбой"
            row.error = self.auto_inbox_error or "AUTO_INBOX_DISABLED"
            row.comment = "Автовходящие отключены fail-closed."
            return
        digest = str(row.details.get("auto_inbox_digest") or "").strip().lower()
        raw_processing = row.details.get("auto_inbox_processing_path")
        source_name = str(
            row.details.get("original_source_name") or row.source_path.name
        )
        if not digest or not raw_processing:
            row.status = "Ошибка"
            row.progress = "Сбой"
            row.error = "AUTO_INBOX_FINALIZATION_METADATA_MISSING"
            row.comment = "Автовходящие: отсутствуют данные завершения."
            return
        success = row.status not in {"Ошибка", "Отменено", "Недоступен"}
        reason = row.error or row.raw_status or row.status
        try:
            processing_path = self.auto_inbox.resolve_internal(
                raw_processing,
                required_parent=self.auto_inbox.processing_dir,
            )
            final_path = self.auto_inbox.finalize(
                processing_path,
                digest,
                success=success,
                reason=str(reason) if reason else None,
                source_name=source_name,
            )
        except AutoInboxError as exc:
            row.status = "Ошибка"
            row.progress = "Сбой"
            row.error = exc.code
            row.comment = (
                "Импорт завершён, но автовходящие не удалось закрыть: "
                + exc.code
            )
            return
        row.details["auto_inbox_transaction_open"] = False
        row.details["auto_inbox_final_path"] = self.auto_inbox.relative_internal(
            final_path
        )
        row.details["auto_inbox_status"] = "COMPLETED" if success else "REJECTED"


__all__ = [
    "AutoInboxCandidate",
    "AutoInboxController",
    "AutoInboxError",
    "FinanceCenterAutoInboxMixin",
]
