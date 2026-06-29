from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Mapping

from quantum.domain.events import CanonicalEvent, EventStatus
from quantum.domain.idempotency import canonical_json_hash, event_idempotency_key


_OPERATION_TO_EVENT = {
    "SALE": "SALE_RECOGNIZED",
    "RETURN": "RETURN_ACCEPTED",
}


@dataclass(frozen=True, slots=True)
class NormalizedRow:
    source_row_key: str
    event: CanonicalEvent
    raw_row_hash: str


def _parse_datetime(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field}: invalid datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field}: timezone is required")
    return parsed


def validate_row(row: Mapping[str, str]) -> None:
    required = (
        "row_id",
        "operation_id",
        "operation_type",
        "event_time",
        "recognition_time",
        "product_external_id",
        "quantity",
        "gross_amount",
        "currency",
        "revision",
    )
    for field in required:
        if not row.get(field, "").strip():
            raise ValueError(f"{field}: required")

    if row["operation_type"] not in _OPERATION_TO_EVENT:
        raise ValueError("operation_type: unsupported")

    try:
        quantity = int(row["quantity"])
    except ValueError as exc:
        raise ValueError("quantity: invalid integer") from exc
    if quantity <= 0:
        raise ValueError("quantity: must be positive")

    try:
        gross_amount = Decimal(row["gross_amount"])
    except InvalidOperation as exc:
        raise ValueError("gross_amount: invalid decimal") from exc
    if not gross_amount.is_finite():
        raise ValueError("gross_amount: must be finite")
    if gross_amount < 0:
        raise ValueError("gross_amount: must be non-negative")

    try:
        revision = int(row["revision"])
    except ValueError as exc:
        raise ValueError("revision: invalid integer") from exc
    if revision < 1:
        raise ValueError("revision: must be >= 1")

    _parse_datetime(row["event_time"], "event_time")
    _parse_datetime(row["recognition_time"], "recognition_time")

    supersedes = row.get("supersedes_event_id", "").strip()
    reversal = row.get("reversal_of_event_id", "").strip()

    if revision > 1 and not supersedes:
        raise ValueError("supersedes_event_id: required for revision > 1")
    if row["operation_type"] == "RETURN" and not reversal:
        raise ValueError("reversal_of_event_id: required for RETURN")


def normalize_row(
    row: Mapping[str, str],
    *,
    organization_id: str,
    marketplace_account_id: str,
    import_batch_id: str,
    source_record_id: str,
    source_file_sha256: str,
    schema_version: str,
    adapter_id: str,
    adapter_version: str,
    trace_id: str,
    actor: str = "a6-proof-worker",
) -> NormalizedRow:
    validate_row(row)
    if not isinstance(actor, str) or not actor.strip():
        raise ValueError("actor: required")

    quantity = int(row["quantity"])
    gross_amount = Decimal(row["gross_amount"])
    revision = int(row["revision"])
    event_type = _OPERATION_TO_EVENT[row["operation_type"]]
    event_id = f"evt-{row['operation_id']}-r{revision}"
    source_row_key = f"csv:row:{row['row_id']}"
    event_time = _parse_datetime(row["event_time"], "event_time")
    recognition_time = _parse_datetime(
        row["recognition_time"],
        "recognition_time",
    )

    payload = {
        "product_external_id": {
            "state": "VALID",
            "value": row["product_external_id"],
            "value_type": "string",
            "unit": None,
            "reason_code": None,
            "source_record_id": source_record_id,
        },
        "quantity": {
            "state": "VALID",
            "value": quantity,
            "value_type": "integer",
            "unit": "item",
            "reason_code": None,
            "source_record_id": source_record_id,
        },
        "gross_amount": {
            "state": "VALID",
            "value": format(gross_amount, "f"),
            "value_type": "decimal",
            "unit": row["currency"],
            "reason_code": None,
            "source_record_id": source_record_id,
        },
    }

    semantic_payload_hash = canonical_json_hash(payload)
    idempotency_key = event_idempotency_key(
        organization_id=organization_id,
        marketplace_account_id=marketplace_account_id,
        event_type=event_type,
        stable_business_key=row["operation_id"],
        revision=revision,
        semantic_payload_hash=semantic_payload_hash,
    )

    event = CanonicalEvent(
        event_id=event_id,
        organization_id=organization_id,
        marketplace_account_id=marketplace_account_id,
        event_type=event_type,
        event_time=event_time,
        recognition_time=recognition_time,
        stable_business_key=row["operation_id"],
        source_row_key=source_row_key,
        revision=revision,
        idempotency_key=idempotency_key,
        semantic_payload_hash=semantic_payload_hash,
        supersedes_event_id=row.get("supersedes_event_id", "").strip() or None,
        reversal_of_event_id=row.get("reversal_of_event_id", "").strip() or None,
        import_batch_id=import_batch_id,
        source_record_id=source_record_id,
        schema_version=schema_version,
        payload=payload,
        provenance={
            "source_file_sha256": source_file_sha256,
            "source_adapter": adapter_id,
            "source_adapter_version": adapter_version,
            "source_schema_id": schema_version,
            "normalization_rule_version": "wb-synthetic-normalization-v1",
            "product_master_version": None,
            "actor": actor.strip(),
            "created_at": recognition_time.isoformat(),
            "trace_id": trace_id,
        },
        status=EventStatus.VALID,
        created_at=recognition_time,
    )

    return NormalizedRow(
        source_row_key=source_row_key,
        event=event,
        raw_row_hash=canonical_json_hash(dict(row)),
    )
