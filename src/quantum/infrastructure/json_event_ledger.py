from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from quantum.domain.events import CanonicalEvent


def _to_json_value(value: Any) -> Any:
    """Convert immutable event structures back to JSON-compatible values."""
    if isinstance(value, Mapping):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_json_value(item) for item in value]
    if isinstance(value, frozenset):
        return [_to_json_value(item) for item in sorted(value, key=repr)]
    return value


class JsonEventLedger:
    """A6-only durable proof ledger; not a production database."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._atomic_write({"events": []})

    def _read(self) -> dict[str, Any]:
        return json.loads(self._path.read_text(encoding="utf-8"))

    def _atomic_write(self, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=self._path.parent,
                prefix=self._path.name + ".",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self._path)
        except Exception:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _serialize(event: CanonicalEvent) -> dict[str, Any]:
        return {
            "event_id": event.event_id,
            "organization_id": event.organization_id,
            "marketplace_account_id": event.marketplace_account_id,
            "event_type": event.event_type,
            "event_time": event.event_time.isoformat(),
            "recognition_time": event.recognition_time.isoformat(),
            "stable_business_key": event.stable_business_key,
            "source_row_key": event.source_row_key,
            "revision": event.revision,
            "idempotency_key": event.idempotency_key,
            "semantic_payload_hash": event.semantic_payload_hash,
            "supersedes_event_id": event.supersedes_event_id,
            "reversal_of_event_id": event.reversal_of_event_id,
            "import_batch_id": event.import_batch_id,
            "source_record_id": event.source_record_id,
            "schema_version": event.schema_version,
            "payload": _to_json_value(event.payload),
            "provenance": _to_json_value(event.provenance),
            "status": event.status.value,
            "created_at": event.created_at.isoformat(),
        }

    def add_if_absent(self, event: CanonicalEvent) -> bool:
        document = self._read()
        existing_by_event_id: dict[str, dict[str, Any]] = {}
        existing_by_idempotency_key: dict[str, dict[str, Any]] = {}

        for item in document["events"]:
            event_id = item["event_id"]
            idempotency_key = item["idempotency_key"]

            if event_id in existing_by_event_id and existing_by_event_id[event_id] != item:
                raise RuntimeError("Ledger already contains conflicting duplicate event_id entries.")
            if (
                idempotency_key in existing_by_idempotency_key
                and existing_by_idempotency_key[idempotency_key] != item
            ):
                raise RuntimeError(
                    "Ledger already contains conflicting duplicate idempotency_key entries."
                )

            existing_by_event_id[event_id] = item
            existing_by_idempotency_key[idempotency_key] = item

        serialized = self._serialize(event)

        if event.event_id in existing_by_event_id:
            if existing_by_event_id[event.event_id] != serialized:
                raise RuntimeError("Event-id collision with different event.")
            return False

        if event.idempotency_key in existing_by_idempotency_key:
            if existing_by_idempotency_key[event.idempotency_key] != serialized:
                raise RuntimeError("Idempotency-key collision with different event.")
            return False

        document["events"].append(serialized)
        self._atomic_write(document)
        return True

    def list_events(self) -> list[dict[str, Any]]:
        return list(self._read()["events"])
