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
from typing import Final
from uuid import UUID

from quantum.access import TenantContext
from quantum.ingestion.receipts import ImmutableUploadReceipt
from quantum.ingestion.schema_registry import SchemaDetection, detect_csv_schema
from quantum.ingestion.fingerprints import semantic_fingerprint


_HEX_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")


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
    """Tenant-scoped content-addressed storage for synthetic P1.2 fixtures."""

    def __init__(self, root: Path) -> None:
        if not isinstance(root, Path):
            raise RawStorageError("STORAGE_ROOT_INVALID")
        self._root = root.resolve()
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._lock = RLock()

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
            filename = data["sanitized_filename"]
            storage_key = data["storage_key"]
            diagnostics = tuple(data.get("diagnostics", []))
            if (
                not isinstance(tenant_id, str)
                or not tenant_id
                or size_bytes < 0
                or not isinstance(filename, str)
                or not filename
                or not isinstance(storage_key, str)
                or not all(isinstance(item, str) for item in diagnostics)
            ):
                raise ValueError("invalid metadata fields")
            return RawFileRecord(
                raw_file_id=raw_file_id,
                tenant_id=tenant_id,
                sha256=digest,
                size_bytes=size_bytes,
                sanitized_filename=filename,
                storage_key=storage_key,
                state=RawFileState(data["state"]),
                schema_id=data.get("schema_id"),
                structural_fingerprint=data.get("structural_fingerprint"),
                semantic_fingerprint=data.get("semantic_fingerprint"),
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
        digest = sha256(payload).hexdigest()
        if digest != receipt.sha256 or len(payload) != receipt.size_bytes:
            raise RawStorageError("UPLOAD_RECEIPT_MISMATCH")

        with self._lock:
            content_path = self._content_path(tenant, digest)
            metadata_path = self._metadata_path(tenant, receipt.raw_file_id)

            if content_path.exists():
                existing = content_path.read_bytes()
                if (
                    sha256(existing).hexdigest() != digest
                    or len(existing) != receipt.size_bytes
                ):
                    raise RawStorageError("STORAGE_INTEGRITY_FAILED")
            else:
                self._atomic_write(content_path, payload)

            if metadata_path.exists():
                existing_record = self._record_from_payload(
                    metadata_path.read_bytes()
                )
                if (
                    existing_record.sha256 != digest
                    or existing_record.tenant_id != tenant.tenant_id
                ):
                    raise RawStorageError("STORAGE_METADATA_CONFLICT")
                return existing_record

            record = RawFileRecord(
                raw_file_id=self._raw_id(receipt.raw_file_id),
                tenant_id=tenant.tenant_id,
                sha256=digest,
                size_bytes=len(payload),
                sanitized_filename=receipt.sanitized_filename,
                storage_key=f"tenants/{tenant.tenant_id}/raw/{digest}",
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
        if not all(isinstance(item, str) for item in diagnostics):
            raise RawStorageError("RAW_FILE_DIAGNOSTICS_INVALID")
        with self._lock:
            current = self.get_record(tenant=tenant, raw_file_id=raw_file_id)
            if state not in _ALLOWED_TRANSITIONS[current.state]:
                raise RawStorageError("RAW_FILE_STATE_TRANSITION_INVALID")
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
        current = self._storage.get_record(
            tenant=tenant, raw_file_id=raw_file_id
        )
        if current.state in _TERMINAL_STATES:
            return SchemaGateResult(record=current, detection=None)
        self._storage.transition(
            tenant=tenant,
            raw_file_id=raw_file_id,
            state=RawFileState.VALIDATING,
        )
        try:
            path = self._storage.content_path(
                tenant=tenant, raw_file_id=raw_file_id
            )
            detection = detect_csv_schema(path)
            if detection.status != "MATCHED":
                record = self._storage.transition(
                    tenant=tenant,
                    raw_file_id=raw_file_id,
                    state=RawFileState.QUARANTINED,
                    structural_fingerprint=detection.structural_fingerprint,
                    diagnostics=detection.diagnostics or ("SCHEMA_UNKNOWN",),
                )
                return SchemaGateResult(record=record, detection=detection)

            with path.open("r", encoding="utf-8-sig", newline="") as handle:
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
