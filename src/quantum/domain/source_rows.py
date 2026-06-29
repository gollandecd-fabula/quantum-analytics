from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import re
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID

from quantum.domain.idempotency import canonical_json_hash


_HEX = re.compile(r"^[0-9a-f]{64}$")


def _freeze(value: Any) -> Any:
    if isinstance(value, MappingABC):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, MappingABC):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _check_fingerprint(value: Any, field: str) -> Mapping[str, object]:
    if not isinstance(value, MappingABC) or not value:
        raise ValueError(f"{field}: required")
    digest = value.get("sha256")
    if not isinstance(digest, str) or _HEX.fullmatch(digest) is None:
        raise ValueError(f"{field}.sha256: invalid")
    return value


class SourceRowStatus(StrEnum):
    VALID = "VALID"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True, slots=True)
class ImmutableSourceRow:
    source_record_id: str
    tenant_id: str
    raw_file_id: str
    source_file_sha256: str
    import_batch_id: str
    row_number: int
    source_row_key: str
    raw_row_hash: str
    raw_payload: Mapping[str, str]
    structural_fingerprint: Mapping[str, object]
    semantic_fingerprint: Mapping[str, object] | None
    validation_status: SourceRowStatus
    diagnostics: tuple[str, ...]
    adapter_id: str
    adapter_version: str
    schema_version: str
    ingested_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "source_record_id",
            "tenant_id",
            "import_batch_id",
            "source_row_key",
            "adapter_id",
            "adapter_version",
            "schema_version",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name}: required")
        try:
            UUID(self.raw_file_id)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("raw_file_id: invalid UUID") from exc
        for name in ("source_file_sha256", "raw_row_hash"):
            value = getattr(self, name)
            if not isinstance(value, str) or _HEX.fullmatch(value) is None:
                raise ValueError(f"{name}: invalid SHA-256")
        if not isinstance(self.row_number, int) or self.row_number < 2:
            raise ValueError("row_number: must be >= 2")
        if (
            not isinstance(self.raw_payload, MappingABC)
            or not self.raw_payload
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in self.raw_payload.items()
            )
        ):
            raise ValueError("raw_payload: non-empty string mapping required")
        if canonical_json_hash(_plain(self.raw_payload)) != self.raw_row_hash:
            raise ValueError("raw_row_hash: does not match raw_payload")
        structural = _check_fingerprint(
            self.structural_fingerprint,
            "structural_fingerprint",
        )
        semantic = self.semantic_fingerprint
        if semantic is not None:
            semantic = _check_fingerprint(semantic, "semantic_fingerprint")
        if not isinstance(self.validation_status, SourceRowStatus):
            raise ValueError("validation_status: invalid")
        if not all(isinstance(item, str) and item for item in self.diagnostics):
            raise ValueError("diagnostics: invalid")
        if self.validation_status is SourceRowStatus.VALID:
            if self.diagnostics:
                raise ValueError("diagnostics: forbidden for VALID row")
            if semantic is None:
                raise ValueError("semantic_fingerprint: required for VALID row")
        if (
            self.validation_status is SourceRowStatus.QUARANTINED
            and not self.diagnostics
        ):
            raise ValueError("diagnostics: required for QUARANTINED row")
        if (
            not isinstance(self.ingested_at, datetime)
            or self.ingested_at.tzinfo is None
            or self.ingested_at.utcoffset() is None
        ):
            raise ValueError("ingested_at: timezone-aware datetime required")
        object.__setattr__(self, "raw_payload", _freeze(self.raw_payload))
        object.__setattr__(self, "structural_fingerprint", _freeze(structural))
        if semantic is not None:
            object.__setattr__(self, "semantic_fingerprint", _freeze(semantic))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))

    def content_fingerprint(self) -> str:
        return canonical_json_hash(
            {
                "source_record_id": self.source_record_id,
                "tenant_id": self.tenant_id,
                "raw_file_id": self.raw_file_id,
                "source_file_sha256": self.source_file_sha256,
                "import_batch_id": self.import_batch_id,
                "row_number": self.row_number,
                "source_row_key": self.source_row_key,
                "raw_row_hash": self.raw_row_hash,
                "raw_payload": _plain(self.raw_payload),
                "structural_fingerprint": _plain(self.structural_fingerprint),
                "semantic_fingerprint": _plain(self.semantic_fingerprint),
                "validation_status": self.validation_status.value,
                "diagnostics": list(self.diagnostics),
                "adapter_id": self.adapter_id,
                "adapter_version": self.adapter_version,
                "schema_version": self.schema_version,
            }
        )
