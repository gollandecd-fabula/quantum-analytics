from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from threading import RLock
from typing import Any

from quantum.access import TenantContext
from quantum.domain.events import CanonicalEvent, EventStatus
from quantum.domain.idempotency import canonical_json_hash
from quantum.domain.source_rows import ImmutableSourceRow, SourceRowStatus


_HEX = re.compile(r"^[0-9a-f]{64}$")


class CanonicalLedgerError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class LedgerAppendResult:
    source_inserted: bool
    event_inserted: bool


@dataclass(frozen=True, slots=True)
class EventTrace:
    event: CanonicalEvent
    source_row: ImmutableSourceRow
    raw_file_id: str
    source_file_sha256: str


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, frozenset):
        return sorted((_plain(item) for item in value), key=repr)
    return value


def _typed(payload: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    try:
        value = payload[field]
    except (KeyError, TypeError) as exc:
        raise CanonicalLedgerError("EVENT_TYPED_VALUE_INVALID") from exc
    if not isinstance(value, Mapping) or value.get("state") != "VALID":
        raise CanonicalLedgerError("EVENT_TYPED_VALUE_INVALID")
    return value


def _typed_integer(payload: Mapping[str, Any], field: str) -> tuple[int, str]:
    value = _typed(payload, field)
    raw = value.get("value")
    unit = value.get("unit")
    if (
        value.get("value_type") != "integer"
        or type(raw) is not int
        or raw <= 0
        or not isinstance(unit, str)
        or not unit
    ):
        raise CanonicalLedgerError("EVENT_TYPED_INTEGER_INVALID")
    return raw, unit


def _typed_decimal(payload: Mapping[str, Any], field: str) -> tuple[Decimal, str]:
    value = _typed(payload, field)
    raw = value.get("value")
    unit = value.get("unit")
    if (
        value.get("value_type") != "decimal"
        or not isinstance(raw, str)
        or not isinstance(unit, str)
        or not unit
    ):
        raise CanonicalLedgerError("EVENT_TYPED_DECIMAL_INVALID")
    try:
        parsed = Decimal(raw)
    except InvalidOperation as exc:
        raise CanonicalLedgerError("EVENT_TYPED_DECIMAL_INVALID") from exc
    if not parsed.is_finite() or parsed < 0:
        raise CanonicalLedgerError("EVENT_TYPED_DECIMAL_INVALID")
    return parsed, unit


def _typed_string(payload: Mapping[str, Any], field: str) -> str:
    value = _typed(payload, field)
    raw = value.get("value")
    if value.get("value_type") != "string" or not isinstance(raw, str) or not raw:
        raise CanonicalLedgerError("EVENT_TYPED_STRING_INVALID")
    return raw


class InMemoryCanonicalLedger:
    """Thread-safe append-only P1.3 ledger with atomic batch support."""

    def __init__(self) -> None:
        self._source_by_id: dict[tuple[str, str], ImmutableSourceRow] = {}
        self._source_by_locator: dict[tuple[str, str, int], str] = {}
        self._event_by_id: dict[tuple[str, str], CanonicalEvent] = {}
        self._event_by_idempotency: dict[tuple[str, str], CanonicalEvent] = {}
        self._event_by_revision: dict[
            tuple[str, str, str, int], CanonicalEvent
        ] = {}
        self._lock = RLock()

    @staticmethod
    def _require_tenant(tenant: TenantContext) -> TenantContext:
        if not isinstance(tenant, TenantContext):
            raise CanonicalLedgerError("TENANT_CONTEXT_REQUIRED")
        return tenant

    def _event_or_error(
        self,
        *,
        tenant_id: str,
        event_id: str,
        code: str,
    ) -> CanonicalEvent:
        event = self._event_by_id.get((tenant_id, event_id))
        if event is None:
            raise CanonicalLedgerError(code)
        return event

    @staticmethod
    def _validate_lineage(
        source_row: ImmutableSourceRow,
        event: CanonicalEvent,
    ) -> None:
        if source_row.validation_status is not SourceRowStatus.VALID:
            raise CanonicalLedgerError("EVENT_SOURCE_ROW_NOT_VALID")
        if event.status is not EventStatus.VALID:
            raise CanonicalLedgerError("EVENT_STATUS_NOT_VALID")
        for observed in (event.event_time, event.recognition_time, event.created_at):
            if observed.tzinfo is None or observed.utcoffset() is None:
                raise CanonicalLedgerError("EVENT_TIMEZONE_REQUIRED")
        if (
            not isinstance(event.idempotency_key, str)
            or _HEX.fullmatch(event.idempotency_key) is None
        ):
            raise CanonicalLedgerError("EVENT_IDEMPOTENCY_KEY_INVALID")
        if canonical_json_hash(_plain(event.payload)) != event.semantic_payload_hash:
            raise CanonicalLedgerError("EVENT_SEMANTIC_HASH_MISMATCH")
        if event.organization_id != source_row.tenant_id:
            raise CanonicalLedgerError("EVENT_TENANT_MISMATCH")
        if event.source_record_id != source_row.source_record_id:
            raise CanonicalLedgerError("EVENT_SOURCE_RECORD_MISMATCH")
        if event.source_row_key != source_row.source_row_key:
            raise CanonicalLedgerError("EVENT_SOURCE_ROW_KEY_MISMATCH")
        if event.import_batch_id != source_row.import_batch_id:
            raise CanonicalLedgerError("EVENT_IMPORT_BATCH_MISMATCH")
        if event.schema_version != source_row.schema_version:
            raise CanonicalLedgerError("EVENT_SCHEMA_VERSION_MISMATCH")

        provenance = event.provenance
        required = (
            "source_file_sha256",
            "source_adapter",
            "source_adapter_version",
            "source_schema_id",
            "normalization_rule_version",
            "actor",
            "created_at",
            "trace_id",
        )
        if any(not provenance.get(field) for field in required):
            raise CanonicalLedgerError("EVENT_PROVENANCE_INCOMPLETE")
        if provenance["created_at"] != event.created_at.isoformat():
            raise CanonicalLedgerError("EVENT_PROVENANCE_TIME_MISMATCH")
        if provenance["source_file_sha256"] != source_row.source_file_sha256:
            raise CanonicalLedgerError("EVENT_SOURCE_FILE_MISMATCH")
        if provenance["source_adapter"] != source_row.adapter_id:
            raise CanonicalLedgerError("EVENT_ADAPTER_MISMATCH")
        if provenance["source_adapter_version"] != source_row.adapter_version:
            raise CanonicalLedgerError("EVENT_ADAPTER_VERSION_MISMATCH")
        if provenance["source_schema_id"] != source_row.schema_version:
            raise CanonicalLedgerError("EVENT_SOURCE_SCHEMA_MISMATCH")

    def _validate_revision(self, *, tenant_id: str, event: CanonicalEvent) -> None:
        revision_key = (
            tenant_id,
            event.marketplace_account_id,
            event.stable_business_key,
            event.revision,
        )
        existing_revision = self._event_by_revision.get(revision_key)
        if existing_revision is not None and existing_revision != event:
            raise CanonicalLedgerError("EVENT_REVISION_CONFLICT")
        if event.revision == 1:
            if event.supersedes_event_id is not None:
                raise CanonicalLedgerError("EVENT_SUPERSESSION_INVALID")
            return
        if event.supersedes_event_id is None:
            raise CanonicalLedgerError("EVENT_SUPERSESSION_REQUIRED")
        previous = self._event_or_error(
            tenant_id=tenant_id,
            event_id=event.supersedes_event_id,
            code="EVENT_SUPERSEDED_TARGET_MISSING",
        )
        if (
            previous.marketplace_account_id != event.marketplace_account_id
            or previous.stable_business_key != event.stable_business_key
            or previous.event_type != event.event_type
            or previous.revision + 1 != event.revision
        ):
            raise CanonicalLedgerError("EVENT_SUPERSESSION_INVALID")

    def _active_reversals(
        self,
        *,
        tenant_id: str,
        original_event_id: str,
        candidate: CanonicalEvent,
    ) -> list[CanonicalEvent]:
        superseded = {
            item.supersedes_event_id
            for (scope, _), item in self._event_by_id.items()
            if scope == tenant_id and item.supersedes_event_id is not None
        }
        if candidate.supersedes_event_id is not None:
            superseded.add(candidate.supersedes_event_id)
        return [
            item
            for (scope, _), item in self._event_by_id.items()
            if scope == tenant_id
            and item.event_id != candidate.event_id
            and item.event_id not in superseded
            and item.event_type == "RETURN_ACCEPTED"
            and item.reversal_of_event_id == original_event_id
        ]

    def _validate_reversal(self, *, tenant_id: str, event: CanonicalEvent) -> None:
        if event.event_type == "RETURN_ACCEPTED":
            if event.reversal_of_event_id is None:
                raise CanonicalLedgerError("EVENT_REVERSAL_REQUIRED")
        elif event.reversal_of_event_id is not None:
            raise CanonicalLedgerError("EVENT_REVERSAL_INVALID")
        else:
            return

        original = self._event_or_error(
            tenant_id=tenant_id,
            event_id=event.reversal_of_event_id,
            code="EVENT_REVERSAL_TARGET_MISSING",
        )
        if (
            original.marketplace_account_id != event.marketplace_account_id
            or original.event_type != "SALE_RECOGNIZED"
        ):
            raise CanonicalLedgerError("EVENT_REVERSAL_INVALID")

        original_product = _typed_string(original.payload, "product_external_id")
        reversal_product = _typed_string(event.payload, "product_external_id")
        original_quantity, quantity_unit = _typed_integer(
            original.payload,
            "quantity",
        )
        reversed_quantity, reversal_quantity_unit = _typed_integer(
            event.payload,
            "quantity",
        )
        original_amount, amount_unit = _typed_decimal(
            original.payload,
            "gross_amount",
        )
        reversed_amount, reversal_amount_unit = _typed_decimal(
            event.payload,
            "gross_amount",
        )
        if (
            original_product != reversal_product
            or quantity_unit != reversal_quantity_unit
            or amount_unit != reversal_amount_unit
        ):
            raise CanonicalLedgerError("EVENT_REVERSAL_UNIT_MISMATCH")

        for existing in self._active_reversals(
            tenant_id=tenant_id,
            original_event_id=original.event_id,
            candidate=event,
        ):
            quantity, unit = _typed_integer(existing.payload, "quantity")
            amount, currency = _typed_decimal(existing.payload, "gross_amount")
            product = _typed_string(existing.payload, "product_external_id")
            if (
                product != original_product
                or unit != quantity_unit
                or currency != amount_unit
            ):
                raise CanonicalLedgerError("EVENT_REVERSAL_UNIT_MISMATCH")
            reversed_quantity += quantity
            reversed_amount += amount

        if reversed_quantity > original_quantity or reversed_amount > original_amount:
            raise CanonicalLedgerError("EVENT_REVERSAL_EXCEEDS_ORIGINAL")

    def _append_locked(
        self,
        *,
        tenant: TenantContext,
        source_row: ImmutableSourceRow,
        event: CanonicalEvent | None,
    ) -> LedgerAppendResult:
        if not isinstance(source_row, ImmutableSourceRow):
            raise CanonicalLedgerError("SOURCE_ROW_REQUIRED")
        if source_row.tenant_id != tenant.tenant_id:
            raise CanonicalLedgerError("SOURCE_ROW_NOT_FOUND")
        if event is not None and not isinstance(event, CanonicalEvent):
            raise CanonicalLedgerError("CANONICAL_EVENT_INVALID")
        if event is None and source_row.validation_status is SourceRowStatus.VALID:
            raise CanonicalLedgerError("VALID_SOURCE_ROW_EVENT_REQUIRED")
        if event is not None:
            self._validate_lineage(source_row, event)

        source_key = (tenant.tenant_id, source_row.source_record_id)
        locator_key = (
            tenant.tenant_id,
            source_row.raw_file_id,
            source_row.row_number,
        )
        existing_source = self._source_by_id.get(source_key)
        if (
            existing_source is not None
            and existing_source.content_fingerprint()
            != source_row.content_fingerprint()
        ):
            raise CanonicalLedgerError("SOURCE_RECORD_CONFLICT")
        existing_locator = self._source_by_locator.get(locator_key)
        if existing_locator is not None and existing_locator != source_row.source_record_id:
            raise CanonicalLedgerError("SOURCE_ROW_LOCATOR_CONFLICT")

        event_inserted = False
        if event is not None:
            existing_event = self._event_by_id.get(
                (tenant.tenant_id, event.event_id)
            )
            if existing_event is not None and existing_event != event:
                raise CanonicalLedgerError("EVENT_ID_CONFLICT")
            existing_idempotency = self._event_by_idempotency.get(
                (tenant.tenant_id, event.idempotency_key)
            )
            if existing_idempotency is not None and existing_idempotency != event:
                raise CanonicalLedgerError("EVENT_IDEMPOTENCY_CONFLICT")
            self._validate_revision(tenant_id=tenant.tenant_id, event=event)
            self._validate_reversal(tenant_id=tenant.tenant_id, event=event)
            event_inserted = existing_event is None

        source_inserted = existing_source is None
        if source_inserted:
            self._source_by_id[source_key] = source_row
        self._source_by_locator[locator_key] = source_row.source_record_id
        if event is not None and event_inserted:
            self._event_by_id[(tenant.tenant_id, event.event_id)] = event
            self._event_by_idempotency[
                (tenant.tenant_id, event.idempotency_key)
            ] = event
            self._event_by_revision[
                (
                    tenant.tenant_id,
                    event.marketplace_account_id,
                    event.stable_business_key,
                    event.revision,
                )
            ] = event
        return LedgerAppendResult(source_inserted, event_inserted)

    def append(
        self,
        *,
        tenant: TenantContext,
        source_row: ImmutableSourceRow,
        event: CanonicalEvent | None,
    ) -> LedgerAppendResult:
        tenant = self._require_tenant(tenant)
        with self._lock:
            return self._append_locked(
                tenant=tenant,
                source_row=source_row,
                event=event,
            )

    def append_batch(
        self,
        *,
        tenant: TenantContext,
        items: Iterable[tuple[ImmutableSourceRow, CanonicalEvent | None]],
    ) -> tuple[LedgerAppendResult, ...]:
        tenant = self._require_tenant(tenant)
        materialized = tuple(items)
        with self._lock:
            backups = (
                self._source_by_id.copy(),
                self._source_by_locator.copy(),
                self._event_by_id.copy(),
                self._event_by_idempotency.copy(),
                self._event_by_revision.copy(),
            )
            try:
                return tuple(
                    self._append_locked(
                        tenant=tenant,
                        source_row=source_row,
                        event=event,
                    )
                    for source_row, event in materialized
                )
            except Exception:
                (
                    self._source_by_id,
                    self._source_by_locator,
                    self._event_by_id,
                    self._event_by_idempotency,
                    self._event_by_revision,
                ) = backups
                raise

    def fork(self) -> InMemoryCanonicalLedger:
        clone = InMemoryCanonicalLedger()
        with self._lock:
            clone._source_by_id = self._source_by_id.copy()
            clone._source_by_locator = self._source_by_locator.copy()
            clone._event_by_id = self._event_by_id.copy()
            clone._event_by_idempotency = self._event_by_idempotency.copy()
            clone._event_by_revision = self._event_by_revision.copy()
        return clone

    def has_event(self, *, tenant: TenantContext, event_id: str) -> bool:
        tenant = self._require_tenant(tenant)
        if not isinstance(event_id, str) or not event_id:
            raise CanonicalLedgerError("EVENT_ID_INVALID")
        with self._lock:
            return (tenant.tenant_id, event_id) in self._event_by_id

    def get_event(
        self,
        *,
        tenant: TenantContext,
        event_id: str,
    ) -> CanonicalEvent:
        tenant = self._require_tenant(tenant)
        if not isinstance(event_id, str) or not event_id:
            raise CanonicalLedgerError("EVENT_ID_INVALID")
        with self._lock:
            event = self._event_by_id.get((tenant.tenant_id, event_id))
        if event is None:
            raise CanonicalLedgerError("EVENT_NOT_FOUND")
        return event

    def get_source_row(
        self,
        *,
        tenant: TenantContext,
        source_record_id: str,
    ) -> ImmutableSourceRow:
        tenant = self._require_tenant(tenant)
        if not isinstance(source_record_id, str) or not source_record_id:
            raise CanonicalLedgerError("SOURCE_RECORD_ID_INVALID")
        with self._lock:
            row = self._source_by_id.get((tenant.tenant_id, source_record_id))
        if row is None:
            raise CanonicalLedgerError("SOURCE_ROW_NOT_FOUND")
        return row

    def trace_event(
        self,
        *,
        tenant: TenantContext,
        event_id: str,
    ) -> EventTrace:
        event = self.get_event(tenant=tenant, event_id=event_id)
        source_row = self.get_source_row(
            tenant=tenant,
            source_record_id=event.source_record_id,
        )
        return EventTrace(
            event=event,
            source_row=source_row,
            raw_file_id=source_row.raw_file_id,
            source_file_sha256=source_row.source_file_sha256,
        )

    def list_events(self, *, tenant: TenantContext) -> tuple[CanonicalEvent, ...]:
        tenant = self._require_tenant(tenant)
        with self._lock:
            events = [
                event
                for (tenant_id, _), event in self._event_by_id.items()
                if tenant_id == tenant.tenant_id
            ]
        return tuple(sorted(events, key=lambda item: item.event_id))

    def list_source_rows(
        self,
        *,
        tenant: TenantContext,
    ) -> tuple[ImmutableSourceRow, ...]:
        tenant = self._require_tenant(tenant)
        with self._lock:
            rows = [
                row
                for (tenant_id, _), row in self._source_by_id.items()
                if tenant_id == tenant.tenant_id
            ]
        return tuple(
            sorted(
                rows,
                key=lambda item: (
                    item.raw_file_id,
                    item.row_number,
                    item.source_record_id,
                ),
            )
        )
