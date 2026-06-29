from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
import csv
import json
import os
from pathlib import Path
import re
import tempfile
from threading import RLock
from typing import ClassVar, Final
from uuid import UUID

from quantum.access import TenantContext
from quantum.ingestion.receipts import ImmutableUploadReceipt
from quantum.ingestion.schema_registry import SchemaDetection, detect_csv_schema
from quantum.ingestion.fingerprints import semantic_fingerprint


_HEX_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
_SAFE_FILENAME: Final = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]{0,119}$")


class RawStorageError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RawFileState(StrEnum):
    RECEIVED = "RECEIVED"
    VALIDATING = "VALIDATING"
    VALID = "VALID"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class RawFileRecord:
    raw_file_id: str
    tenant_id: str
    sha256: str
    size_bytes: int
    sanitized_filename: str
    storage_key: str
    state: RawFileState
    schema_id: str | None = None
    structural_fingerprint: dict[str, object] | None = None
    semantic_fingerprint: dict[str, object] | None = None
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SchemaGateResult:
    record: RawFileRecord
    detection: SchemaDetection | None


_ALLOWED_TRANSITIONS: Final = {
    RawFileState.RECEIVED: {RawFileState.VALIDATING},
    RawFileState.VALIDATING: {
        RawFileState.VALID,
        RawFileState.QUARANTINED,
        RawFileState.REJECTED,
    },
    RawFileState.VALID: set(),
    RawFileState.QUARANTINED: set(),
    RawFileState.REJECTED: set(),
}
_TERMINAL_STATES: Final = {
    RawFileState.VALID,
    RawFileState.QUARANTINED,
    RawFileState.REJECTED,
}


class LocalRawStorage:
    """Thread-safe single-process storage for synthetic P1.2 fixtures."""

    _registry_lock: ClassVar[RLock] = RLock()
    _root_locks: ClassVar[dict[str, RLock]] = {}
    _validation_lock_registry: ClassVar[
        dict[tuple[str, str, str], RLock]
    ] = {}

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise RawStorageError("STORAGE_ROOT_INVALID")
        self._root = root.resolve()
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root_key = os.fspath(self._root)
        with self._registry_lock:
            self._lock = self._root_locks.setdefault(root_key, RLock())

    @staticmethod
    def _tenant_token(tenant: TenantContext) -> str:
        if not isinstance(tenant, TenantContext):
            raise RawStorageError("TENANT_CONTEXT_REQUIRED")
        return sha256(tenant.tenant_id.encode("utf-8")).hexdigest()

    @staticmethod
    def _raw_id(value: str) -> str:
        if not isinstance(value, str):
            raise RawStorageError("RAW_FILE_ID_INVALID")
        try:
            return str(UUID(value))
        except (ValueError, AttributeError) as exc:
            raise RawStorageError("RAW_FILE_ID_INVALID") from exc

    @staticmethod
    def _digest(value: str) -> str:
        if not isinstance(value, str) or _HEX_SHA256.fullmatch(value) is None:
            raise RawStorageError("STORAGE_DIGEST_INVALID")
        return value

    @staticmethod
    def _filename(value: str) -> str:
        if not isinstance(value, str) or _SAFE_FILENAME.fullmatch(value) is None:
            raise RawStorageError("UPLOAD_FILENAME_INVALID")
        return value

    @staticmethod
    def _canonical_storage_key(tenant_id: str, digest: str) -> str:
        return f"tenants/{tenant_id}/raw/{digest}"

    def _tenant_root(self, tenant: TenantContext) -> Path:
        path = self._root / "tenants" / self._tenant_token(tenant)
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        return path

    def _content_path(self, tenant: TenantContext, digest: str) -> Path:
        return self._tenant_root(tenant) / "raw" / self._digest(digest)

    def _metadata_path(self, tenant: TenantContext, raw_file_id: str) -> Path:
        return (
            self._tenant_root(tenant)
            / "metadata"
            / f"{self._raw_id(raw_file_id)}.json"
        )

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @classmethod
    def _atomic_write(cls, path: Path, payload: bytes) -> None:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temp_path = Path(handle.name)
            try:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                os.replace(temp_path, path)
                cls._fsync_directory(path.parent)
            except Exception:
                temp_path.unlink(missing_ok=True)
                raise

    @staticmethod
    def _record_payload(record: RawFileRecord) -> bytes:
        return json.dumps(
            {
                "raw_file_id": record.raw_file_id,
                "tenant_id": record.tenant_id,
                "sha256": record.sha256,
                "size_bytes": record.size_bytes,
                "sanitized_filename": record.sanitized_filename,
                "storage_key": record.storage_key,
                "state": record.state.value,
                "schema_id": record.schema_id,
                "structural_fingerprint": record.structural_fingerprint,
                "semantic_fingerprint": record.semantic_fingerprint,
                "diagnostics": list(record.diagnostics),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @classmethod
    def _record_from_payload(cls, payload: bytes) -> RawFileRecord:
        try:
            data = json.loads(payload.decode("utf-8"))
            raw_file_id = cls._raw_id(data["raw_file_id"])
            digest = cls._digest(data["sha256"])
            tenant_id = data["tenant_id"]
            size_bytes = int(data["size_bytes"])
            filename = cls._filename(data["sanitized_filename"])
            storage_key = data["storage_key"]
            state = RawFileState(data["state"])
            schema_id = data.get("schema_id")
            structural = data.get("structural_fingerprint")
            semantic = data.get("semantic_fingerprint")
            diagnostics = tuple(data.get("diagnostics", []))
            if (
                not isinstance(tenant_id, str)
                or not tenant_id
                or size_bytes < 0
                or not isinstance(storage_key, str)
                or (schema_id is not None and not isinstance(schema_id, str))
                or (structural is not None and not isinstance(structural, dict))
                or (semantic is not None and not isinstance(semantic, dict))
                or not all(isinstance(item, str) for item in diagnostics)
            ):
                raise ValueError("invalid metadata fields")
            if storage_key != cls._canonical_storage_key(tenant_id, digest):
                raise ValueError("non-canonical storage key")
            cls._validate_transition_payload(
                state,
                schema_id=schema_id,
                structural_fingerprint=structural,
                semantic_fingerprint_value=semantic,
                diagnostics=diagnostics,
            )
            return RawFileRecord(
                raw_file_id=raw_file_id,
                tenant_id=tenant_id,
                sha256=digest,
                size_bytes=size_bytes,
                sanitized_filename=filename,
                storage_key=storage_key,
                state=state,
                schema_id=schema_id,
                structural_fingerprint=structural,
                semantic_fingerprint=semantic,
                diagnostics=diagnostics,
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            RawStorageError,
        ) as exc:
            raise RawStorageError("STORAGE_METADATA_INVALID") from exc

    def store(
        self,
        *,
        tenant: TenantContext,
        receipt: ImmutableUploadReceipt,
        payload: bytes,
    ) -> RawFileRecord:
        self._tenant_token(tenant)
        if not isinstance(receipt, ImmutableUploadReceipt):
            raise RawStorageError("UPLOAD_RECEIPT_REQUIRED")
        if receipt.tenant_id != tenant.tenant_id:
            raise RawStorageError("RAW_FILE_NOT_FOUND")
        if not isinstance(payload, bytes) or not payload:
            raise RawStorageError("UPLOAD_BYTES_REQUIRED")
        filename = self._filename(receipt.sanitized_filename)
        raw_file_id = self._raw_id(receipt.raw_file_id)
        digest = sha256(payload).hexdigest()
        if digest != receipt.sha256 or len(payload) != receipt.size_bytes:
            raise RawStorageError("UPLOAD_RECEIPT_MISMATCH")

        with self._lock:
            content_path = self._content_path(tenant, digest)
            metadata_path = self._metadata_path(tenant, raw_file_id)

            if metadata_path.exists():
                existing_record = self._record_from_payload(
                    metadata_path.read_bytes()
                )
                if (
                    existing_record.sha256 != digest
                    or existing_record.tenant_id != tenant.tenant_id
                    or existing_record.size_bytes != len(payload)
                    or existing_record.sanitized_filename != filename
                ):
                    raise RawStorageError("STORAGE_METADATA_CONFLICT")
                if content_path.exists():
                    existing = content_path.read_bytes()
                    if (
                        sha256(existing).hexdigest() != digest
                        or len(existing) != len(payload)
                    ):
                        raise RawStorageError("STORAGE_INTEGRITY_FAILED")
                else:
                    self._atomic_write(content_path, payload)
                return existing_record

            if content_path.exists():
                existing = content_path.read_bytes()
                if (
                    sha256(existing).hexdigest() != digest
                    or len(existing) != len(payload)
                ):
                    raise RawStorageError("STORAGE_INTEGRITY_FAILED")
            else:
                self._atomic_write(content_path, payload)

            record = RawFileRecord(
                raw_file_id=raw_file_id,
                tenant_id=tenant.tenant_id,
                sha256=digest,
                size_bytes=len(payload),
                sanitized_filename=filename,
                storage_key=self._canonical_storage_key(
                    tenant.tenant_id,
                    digest,
                ),
                state=RawFileState.RECEIVED,
            )
            self._atomic_write(metadata_path, self._record_payload(record))
            return record

    def get_record(
        self, *, tenant: TenantContext, raw_file_id: str
    ) -> RawFileRecord:
        metadata_path = self._metadata_path(tenant, raw_file_id)
        with self._lock:
            if not metadata_path.exists():
                raise RawStorageError("RAW_FILE_NOT_FOUND")
            record = self._record_from_payload(metadata_path.read_bytes())
        if record.tenant_id != tenant.tenant_id:
            raise RawStorageError("RAW_FILE_NOT_FOUND")
        return record

    def read(self, *, tenant: TenantContext, raw_file_id: str) -> bytes:
        with self._lock:
            record = self.get_record(tenant=tenant, raw_file_id=raw_file_id)
            path = self._content_path(tenant, record.sha256)
            if not path.exists():
                raise RawStorageError("STORAGE_CONTENT_MISSING")
            payload = path.read_bytes()
        if (
            len(payload) != record.size_bytes
            or sha256(payload).hexdigest() != record.sha256
        ):
            raise RawStorageError("STORAGE_INTEGRITY_FAILED")
        return payload

    def content_path(
        self, *, tenant: TenantContext, raw_file_id: str
    ) -> Path:
        record = self.get_record(tenant=tenant, raw_file_id=raw_file_id)
        self.read(tenant=tenant, raw_file_id=raw_file_id)
        return self._content_path(tenant, record.sha256)

    def _validation_lock(
        self,
        *,
        tenant: TenantContext,
        raw_file_id: str,
    ) -> RLock:
        root_key = os.fspath(self._root)
        tenant_id = self._tenant_token(tenant)
        normalized_id = self._raw_id(raw_file_id)
        key = (root_key, tenant_id, normalized_id)
        with self._registry_lock:
            return self._validation_lock_registry.setdefault(key, RLock())

    @staticmethod
    def _validate_transition_payload(
        state: RawFileState,
        *,
        schema_id: str | None,
        structural_fingerprint: dict[str, object] | None,
        semantic_fingerprint_value: dict[str, object] | None,
        diagnostics: tuple[str, ...],
    ) -> None:
        if not all(isinstance(item, str) for item in diagnostics):
            raise RawStorageError("RAW_FILE_DIAGNOSTICS_INVALID")
        if state is RawFileState.RECEIVED:
            if (
                schema_id is not None
                or structural_fingerprint is not None
                or semantic_fingerprint_value is not None
                or diagnostics
            ):
                raise RawStorageError("RAW_FILE_STATE_PAYLOAD_INVALID")
            return
        if state is RawFileState.VALIDATING:
            if (
                schema_id is not None
                or structural_fingerprint is not None
                or semantic_fingerprint_value is not None
                or diagnostics
            ):
                raise RawStorageError("RAW_FILE_STATE_PAYLOAD_INVALID")
            return
        if state is RawFileState.VALID:
            if (
                not isinstance(schema_id, str)
                or not schema_id
                or not isinstance(structural_fingerprint, dict)
                or not isinstance(semantic_fingerprint_value, dict)
                or diagnostics
            ):
                raise RawStorageError("RAW_FILE_STATE_PAYLOAD_INVALID")
            return
        if state is RawFileState.QUARANTINED:
            if (
                schema_id is not None
                or not isinstance(structural_fingerprint, dict)
                or semantic_fingerprint_value is not None
                or not diagnostics
            ):
                raise RawStorageError("RAW_FILE_STATE_PAYLOAD_INVALID")
            return
        if state is RawFileState.REJECTED:
            if (
                schema_id is not None
                or structural_fingerprint is not None
                or semantic_fingerprint_value is not None
                or not diagnostics
            ):
                raise RawStorageError("RAW_FILE_STATE_PAYLOAD_INVALID")

    def transition(
        self,
        *,
        tenant: TenantContext,
        raw_file_id: str,
        state: RawFileState,
        schema_id: str | None = None,
        structural_fingerprint: dict[str, object] | None = None,
        semantic_fingerprint_value: dict[str, object] | None = None,
        diagnostics: tuple[str, ...] = (),
    ) -> RawFileRecord:
        if not isinstance(state, RawFileState):
            raise RawStorageError("RAW_FILE_STATE_INVALID")
        with self._lock:
            current = self.get_record(tenant=tenant, raw_file_id=raw_file_id)
            if state not in _ALLOWED_TRANSITIONS[current.state]:
                raise RawStorageError("RAW_FILE_STATE_TRANSITION_INVALID")
            self._validate_transition_payload(
                state,
                schema_id=schema_id,
                structural_fingerprint=structural_fingerprint,
                semantic_fingerprint_value=semantic_fingerprint_value,
                diagnostics=diagnostics,
            )
            updated = replace(
                current,
                state=state,
                schema_id=schema_id,
                structural_fingerprint=structural_fingerprint,
                semantic_fingerprint=semantic_fingerprint_value,
                diagnostics=tuple(diagnostics),
            )
            self._atomic_write(
                self._metadata_path(tenant, raw_file_id),
                self._record_payload(updated),
            )
            return updated


class CsvSchemaGate:
    def __init__(self, storage: LocalRawStorage) -> None:
        if not isinstance(storage, LocalRawStorage):
            raise RawStorageError("RAW_STORAGE_REQUIRED")
        self._storage = storage

    def inspect(
        self, *, tenant: TenantContext, raw_file_id: str
    ) -> SchemaGateResult:
        with self._storage._validation_lock(
            tenant=tenant,
            raw_file_id=raw_file_id,
        ):
            current = self._storage.get_record(
                tenant=tenant,
                raw_file_id=raw_file_id,
            )
            if current.state in _TERMINAL_STATES:
                return SchemaGateResult(record=current, detection=None)
            if current.state is RawFileState.RECEIVED:
                self._storage.transition(
                    tenant=tenant,
                    raw_file_id=raw_file_id,
                    state=RawFileState.VALIDATING,
                )
            elif current.state is not RawFileState.VALIDATING:
                raise RawStorageError("RAW_FILE_STATE_TRANSITION_INVALID")

            try:
                path = self._storage.content_path(
                    tenant=tenant,
                    raw_file_id=raw_file_id,
                )
                detection = detect_csv_schema(path)
                if detection.status != "MATCHED":
                    record = self._storage.transition(
                        tenant=tenant,
                        raw_file_id=raw_file_id,
                        state=RawFileState.QUARANTINED,
                        structural_fingerprint=detection.structural_fingerprint,
                        diagnostics=(
                            detection.diagnostics or ("SCHEMA_UNKNOWN",)
                        ),
                    )
                    return SchemaGateResult(
                        record=record,
                        detection=detection,
                    )

                with path.open(
                    "r",
                    encoding="utf-8-sig",
                    newline="",
                ) as handle:
                    semantic = semantic_fingerprint(csv.DictReader(handle))
                record = self._storage.transition(
                    tenant=tenant,
                    raw_file_id=raw_file_id,
                    state=RawFileState.VALID,
                    schema_id=detection.schema_id,
                    structural_fingerprint=detection.structural_fingerprint,
                    semantic_fingerprint_value=semantic,
                )
                return SchemaGateResult(record=record, detection=detection)
            except RawStorageError as exc:
                record = self._storage.transition(
                    tenant=tenant,
                    raw_file_id=raw_file_id,
                    state=RawFileState.REJECTED,
                    diagnostics=(exc.code,),
                )
                return SchemaGateResult(record=record, detection=None)
            except (
                UnicodeDecodeError,
                csv.Error,
                StopIteration,
                OSError,
                ValueError,
            ):
                record = self._storage.transition(
                    tenant=tenant,
                    raw_file_id=raw_file_id,
                    state=RawFileState.REJECTED,
                    diagnostics=("CSV_SCHEMA_READ_FAILED",),
                )
                return SchemaGateResult(record=record, detection=None)
