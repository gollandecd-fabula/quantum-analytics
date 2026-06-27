from __future__ import annotations

from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping


def _deep_freeze(value: Any) -> Any:
    """Create a detached, recursively immutable representation."""
    if isinstance(value, MappingABC):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_deep_freeze(item) for item in value)
    return value


class EventStatus(StrEnum):
    VALID = "VALID"
    SUPERSEDED = "SUPERSEDED"
    REVERSED = "REVERSED"
    CONFLICT = "CONFLICT"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class CanonicalEvent:
    event_id: str
    organization_id: str
    marketplace_account_id: str
    event_type: str
    event_time: datetime
    recognition_time: datetime
    stable_business_key: str
    source_row_key: str
    revision: int
    idempotency_key: str
    semantic_payload_hash: str
    import_batch_id: str
    source_record_id: str
    schema_version: str
    payload: Mapping[str, Any]
    provenance: Mapping[str, Any]
    status: EventStatus
    created_at: datetime
    supersedes_event_id: str | None = None
    reversal_of_event_id: str | None = None

    def __post_init__(self) -> None:
        required_strings = {
            "event_id": self.event_id,
            "organization_id": self.organization_id,
            "marketplace_account_id": self.marketplace_account_id,
            "event_type": self.event_type,
            "stable_business_key": self.stable_business_key,
            "source_row_key": self.source_row_key,
            "idempotency_key": self.idempotency_key,
            "import_batch_id": self.import_batch_id,
            "source_record_id": self.source_record_id,
            "schema_version": self.schema_version,
        }
        for field_name, value in required_strings.items():
            if not value:
                raise ValueError(f"{field_name} is required.")

        if self.revision < 1:
            raise ValueError("revision must be >= 1.")
        if len(self.semantic_payload_hash) != 64:
            raise ValueError("semantic_payload_hash must be a SHA-256 hex digest.")
        int(self.semantic_payload_hash, 16)

        if self.event_id == self.supersedes_event_id:
            raise ValueError("An event cannot supersede itself.")
        if self.event_id == self.reversal_of_event_id:
            raise ValueError("An event cannot reverse itself.")
        if not self.payload:
            raise ValueError("payload must not be empty.")
        if not self.provenance:
            raise ValueError("provenance must not be empty.")

        object.__setattr__(self, "payload", _deep_freeze(self.payload))
        object.__setattr__(self, "provenance", _deep_freeze(self.provenance))
