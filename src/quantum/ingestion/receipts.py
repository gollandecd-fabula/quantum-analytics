from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import PurePath
import re
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
    """P1 immutable upload receipt registry without file persistence."""

    def __init__(self) -> None:
        self._receipts: dict[tuple[str, str], ImmutableUploadReceipt] = {}

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        leaf = PurePath(filename.replace("\\", "/")).name
        sanitized = _SAFE_FILENAME.sub("_", leaf).strip("._")
        return sanitized[:120] or "upload.bin"

    def receive(
        self,
        *,
        tenant: TenantContext,
        payload: bytes,
        filename: str,
    ) -> ImmutableUploadReceipt:
        if not isinstance(payload, bytes):
            raise IngestionError("UPLOAD_BYTES_REQUIRED")
        if not payload:
            raise IngestionError("UPLOAD_EMPTY")

        digest = sha256(payload).hexdigest()
        key = (tenant.tenant_id, digest)
        existing = self._receipts.get(key)
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
            sanitized_filename=self.sanitize_filename(filename),
            storage_key=f"tenants/{tenant.tenant_id}/raw/{digest}",
            duplicate=False,
        )
        self._receipts[key] = receipt
        return receipt

    def get(
        self,
        *,
        tenant: TenantContext,
        raw_file_id: str,
    ) -> ImmutableUploadReceipt:
        for receipt in self._receipts.values():
            if receipt.raw_file_id == raw_file_id:
                tenant.require_tenant(receipt.tenant_id)
                return receipt
        raise IngestionError("RAW_FILE_NOT_FOUND")
