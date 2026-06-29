from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePath
import re
from threading import RLock
from typing import Final
from uuid import uuid4

from quantum.access.contracts import TenantContext


_SAFE_FILENAME: Final = re.compile(r"[^A-Za-z0-9._-]+")


class IngestionError(ValueError):
    """Fail-closed ingestion error with a stable diagnostic code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ImmutableUploadReceipt:
    raw_file_id: str
    tenant_id: str
    sha256: str
    size_bytes: int
    sanitized_filename: str
    storage_key: str
    duplicate: bool


class UploadReceiptRegistry:
    """Thread-safe P1 immutable upload receipt registry without persistence."""

    def __init__(self) -> None:
        self._receipts_by_digest: dict[
            tuple[str, str], ImmutableUploadReceipt
        ] = {}
        self._receipts_by_id: dict[
            tuple[str, str], ImmutableUploadReceipt
        ] = {}
        self._lock = RLock()

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        if not isinstance(filename, str):
            raise IngestionError("UPLOAD_FILENAME_INVALID")
        leaf = PurePath(filename.replace("\\", "/")).name
        sanitized = _SAFE_FILENAME.sub("_", leaf).strip("._")
        return sanitized[:120] or "upload.bin"

    @staticmethod
    def _require_tenant(tenant: TenantContext) -> TenantContext:
        if not isinstance(tenant, TenantContext):
            raise IngestionError("TENANT_CONTEXT_REQUIRED")
        return tenant

    def receive(
        self,
        *,
        tenant: TenantContext,
        payload: bytes,
        filename: str,
    ) -> ImmutableUploadReceipt:
        tenant = self._require_tenant(tenant)
        if not isinstance(payload, bytes):
            raise IngestionError("UPLOAD_BYTES_REQUIRED")
        if not payload:
            raise IngestionError("UPLOAD_EMPTY")
        safe_filename = self.sanitize_filename(filename)

        digest = sha256(payload).hexdigest()
        digest_key = (tenant.tenant_id, digest)
        with self._lock:
            existing = self._receipts_by_digest.get(digest_key)
            if existing is not None:
                return ImmutableUploadReceipt(
                    raw_file_id=existing.raw_file_id,
                    tenant_id=existing.tenant_id,
                    sha256=existing.sha256,
                    size_bytes=existing.size_bytes,
                    sanitized_filename=existing.sanitized_filename,
                    storage_key=existing.storage_key,
                    duplicate=True,
                )

            raw_file_id = str(uuid4())
            receipt = ImmutableUploadReceipt(
                raw_file_id=raw_file_id,
                tenant_id=tenant.tenant_id,
                sha256=digest,
                size_bytes=len(payload),
                sanitized_filename=safe_filename,
                storage_key=f"tenants/{tenant.tenant_id}/raw/{digest}",
                duplicate=False,
            )
            self._receipts_by_digest[digest_key] = receipt
            self._receipts_by_id[(tenant.tenant_id, raw_file_id)] = receipt
            return receipt

    def get(
        self,
        *,
        tenant: TenantContext,
        raw_file_id: str,
    ) -> ImmutableUploadReceipt:
        tenant = self._require_tenant(tenant)
        if not isinstance(raw_file_id, str) or not raw_file_id:
            raise IngestionError("RAW_FILE_ID_INVALID")
        with self._lock:
            receipt = self._receipts_by_id.get(
                (tenant.tenant_id, raw_file_id)
            )
        if receipt is None:
            # Do not reveal whether an identifier exists in another tenant.
            raise IngestionError("RAW_FILE_NOT_FOUND")
        return receipt
