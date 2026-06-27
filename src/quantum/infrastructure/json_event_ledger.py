from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from quantum.domain.events import CanonicalEvent


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
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, self._path)

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
            "payload": dict(event.payload),
            "provenance": dict(event.provenance),
            "status": event.status.value,
            "created_at": event.created_at.isoformat(),
        }

    def add_if_absent(self, event: CanonicalEvent) -> bool:
        document = self._read()
        existing = {
            item["idempotency_key"]: item
            for item in document["events"]
        }
        serialized = self._serialize(event)

        if event.idempotency_key in existing:
            if existing[event.idempotency_key] != serialized:
                raise RuntimeError("Idempotency-key collision with different event.")
            return False

        document["events"].append(serialized)
        self._atomic_write(document)
        return True

    def list_events(self) -> list[dict[str, Any]]:
        return list(self._read()["events"])
