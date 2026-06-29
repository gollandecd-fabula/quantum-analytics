from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from io import StringIO

from quantum.access import TenantContext
from quantum.adapters.wildberries.synthetic import normalize_row
from quantum.domain.idempotency import canonical_json_hash
from quantum.domain.source_rows import ImmutableSourceRow, SourceRowStatus
from quantum.infrastructure.in_memory_canonical_ledger import (
    CanonicalLedgerError,
    InMemoryCanonicalLedger,
)
from quantum.ingestion.storage import LocalRawStorage, RawFileState


_ROW_QUARANTINE_CODES = {
    "EVENT_SUPERSEDED_TARGET_MISSING",
    "EVENT_SUPERSESSION_INVALID",
    "EVENT_SUPERSESSION_REQUIRED",
    "EVENT_REVERSAL_TARGET_MISSING",
    "EVENT_REVERSAL_INVALID",
    "EVENT_REVERSAL_REQUIRED",
    "EVENT_REVERSAL_EXCEEDS_ORIGINAL",
}


@dataclass(frozen=True, slots=True)
class CanonicalImportResult:
    raw_file_id: str
    import_batch_id: str
    total_rows: int
    inserted_source_rows: int
    inserted_events: int
    duplicate_source_rows: int
    duplicate_events: int
    quarantined_rows: int
    source_record_ids: tuple[str, ...]
    event_ids: tuple[str, ...]


class SyntheticCsvCanonicalIngestor:
    def __init__(
        self,
        *,
        storage: LocalRawStorage,
        ledger: InMemoryCanonicalLedger,
    ) -> None:
        if not isinstance(storage, LocalRawStorage):
            raise CanonicalLedgerError("RAW_STORAGE_REQUIRED")
        if not isinstance(ledger, InMemoryCanonicalLedger):
            raise CanonicalLedgerError("CANONICAL_LEDGER_REQUIRED")
        self._storage = storage
        self._ledger = ledger

    @staticmethod
    def _strict_rows(payload: bytes) -> list[dict[str, str]]:
        try:
            text = payload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise CanonicalLedgerError("CSV_DECODE_FAILED") from exc
        reader = csv.DictReader(StringIO(text, newline=""))
        if reader.fieldnames is None:
            raise CanonicalLedgerError("CSV_HEADER_MISSING")
        rows: list[dict[str, str]] = []
        try:
            for row in reader:
                if None in row or any(
                    not isinstance(key, str) or not isinstance(value, str)
                    for key, value in row.items()
                ):
                    raise CanonicalLedgerError("CSV_ROW_SHAPE_INVALID")
                rows.append(dict(row))
        except csv.Error as exc:
            raise CanonicalLedgerError("CSV_PARSE_FAILED") from exc
        return rows

    @staticmethod
    def _batch_id(
        *,
        tenant_id: str,
        raw_file_id: str,
        source_file_sha256: str,
    ) -> str:
        digest = sha256(
            "\x1f".join(
                (tenant_id, raw_file_id, source_file_sha256)
            ).encode("utf-8")
        ).hexdigest()
        return f"batch-{digest[:24]}"

    @staticmethod
    def _source_record_id(
        *,
        tenant_id: str,
        raw_file_id: str,
        row_number: int,
        raw_row_hash: str,
    ) -> str:
        digest = sha256(
            "\x1f".join(
                (
                    tenant_id,
                    raw_file_id,
                    str(row_number),
                    raw_row_hash,
                )
            ).encode("utf-8")
        ).hexdigest()
        return f"src-{digest[:32]}"

    @staticmethod
    def _source_row(
        *,
        tenant: TenantContext,
        raw_file_id: str,
        source_file_sha256: str,
        import_batch_id: str,
        row_number: int,
        row: dict[str, str],
        raw_row_hash: str,
        source_record_id: str,
        source_row_key: str,
        structural_fingerprint: dict[str, object],
        semantic_fingerprint: dict[str, object] | None,
        status: SourceRowStatus,
        diagnostics: tuple[str, ...],
        adapter_id: str,
        adapter_version: str,
        schema_version: str,
        ingested_at: datetime,
    ) -> ImmutableSourceRow:
        return ImmutableSourceRow(
            source_record_id=source_record_id,
            tenant_id=tenant.tenant_id,
            raw_file_id=raw_file_id,
            source_file_sha256=source_file_sha256,
            import_batch_id=import_batch_id,
            row_number=row_number,
            source_row_key=source_row_key,
            raw_row_hash=raw_row_hash,
            raw_payload=row,
            structural_fingerprint=structural_fingerprint,
            semantic_fingerprint=semantic_fingerprint,
            validation_status=status,
            diagnostics=diagnostics,
            adapter_id=adapter_id,
            adapter_version=adapter_version,
            schema_version=schema_version,
            ingested_at=ingested_at,
        )

    def ingest(
        self,
        *,
        tenant: TenantContext,
        raw_file_id: str,
        marketplace_account_id: str,
        adapter_id: str = "wildberries-synthetic",
        adapter_version: str = "1.0",
        ingested_at: datetime | None = None,
    ) -> CanonicalImportResult:
        if not isinstance(tenant, TenantContext):
            raise CanonicalLedgerError("TENANT_CONTEXT_REQUIRED")
        if (
            not isinstance(marketplace_account_id, str)
            or not marketplace_account_id
        ):
            raise CanonicalLedgerError("MARKETPLACE_ACCOUNT_ID_REQUIRED")
        if not isinstance(adapter_id, str) or not adapter_id:
            raise CanonicalLedgerError("ADAPTER_ID_REQUIRED")
        if not isinstance(adapter_version, str) or not adapter_version:
            raise CanonicalLedgerError("ADAPTER_VERSION_REQUIRED")
        observed_at = ingested_at or datetime.now(UTC)
        if (
            not isinstance(observed_at, datetime)
            or observed_at.tzinfo is None
            or observed_at.utcoffset() is None
        ):
            raise CanonicalLedgerError("INGESTED_AT_TIMEZONE_REQUIRED")
        observed_at = observed_at.astimezone(UTC)

        record = self._storage.get_record(
            tenant=tenant,
            raw_file_id=raw_file_id,
        )
        if record.state is not RawFileState.VALID:
            raise CanonicalLedgerError("RAW_FILE_NOT_VALID")
        if record.schema_id != "wb-synthetic-operations-v1":
            raise CanonicalLedgerError("SOURCE_SCHEMA_UNSUPPORTED")
        if not isinstance(record.structural_fingerprint, dict):
            raise CanonicalLedgerError("STRUCTURAL_FINGERPRINT_REQUIRED")
        if not isinstance(record.semantic_fingerprint, dict):
            raise CanonicalLedgerError("SEMANTIC_FINGERPRINT_REQUIRED")

        rows = self._strict_rows(
            self._storage.read(
                tenant=tenant,
                raw_file_id=raw_file_id,
            )
        )
        import_batch_id = self._batch_id(
            tenant_id=tenant.tenant_id,
            raw_file_id=raw_file_id,
            source_file_sha256=record.sha256,
        )
        trace_id = f"trace-{import_batch_id.removeprefix('batch-')}"

        inserted_source_rows = 0
        inserted_events = 0
        duplicate_source_rows = 0
        duplicate_events = 0
        quarantined_rows = 0
        source_record_ids: list[str] = []
        event_ids: list[str] = []

        for row_number, row in enumerate(rows, start=2):
            raw_row_hash = canonical_json_hash(row)
            source_record_id = self._source_record_id(
                tenant_id=tenant.tenant_id,
                raw_file_id=raw_file_id,
                row_number=row_number,
                raw_row_hash=raw_row_hash,
            )
            source_record_ids.append(source_record_id)
            fallback_key = f"csv:row:{row.get('row_id') or row_number}"

            try:
                normalized = normalize_row(
                    row,
                    organization_id=tenant.tenant_id,
                    marketplace_account_id=marketplace_account_id,
                    import_batch_id=import_batch_id,
                    source_record_id=source_record_id,
                    source_file_sha256=record.sha256,
                    schema_version=record.schema_id,
                    adapter_id=adapter_id,
                    adapter_version=adapter_version,
                    trace_id=trace_id,
                    actor="p13-canonical-ingestor",
                )
                source_row = self._source_row(
                    tenant=tenant,
                    raw_file_id=raw_file_id,
                    source_file_sha256=record.sha256,
                    import_batch_id=import_batch_id,
                    row_number=row_number,
                    row=row,
                    raw_row_hash=raw_row_hash,
                    source_record_id=source_record_id,
                    source_row_key=normalized.source_row_key,
                    structural_fingerprint=record.structural_fingerprint,
                    semantic_fingerprint=record.semantic_fingerprint,
                    status=SourceRowStatus.VALID,
                    diagnostics=(),
                    adapter_id=adapter_id,
                    adapter_version=adapter_version,
                    schema_version=record.schema_id,
                    ingested_at=observed_at,
                )
                try:
                    append_result = self._ledger.append(
                        tenant=tenant,
                        source_row=source_row,
                        event=normalized.event,
                    )
                except CanonicalLedgerError as exc:
                    if exc.code not in _ROW_QUARANTINE_CODES:
                        raise
                    source_row = self._source_row(
                        tenant=tenant,
                        raw_file_id=raw_file_id,
                        source_file_sha256=record.sha256,
                        import_batch_id=import_batch_id,
                        row_number=row_number,
                        row=row,
                        raw_row_hash=raw_row_hash,
                        source_record_id=source_record_id,
                        source_row_key=normalized.source_row_key,
                        structural_fingerprint=record.structural_fingerprint,
                        semantic_fingerprint=record.semantic_fingerprint,
                        status=SourceRowStatus.QUARANTINED,
                        diagnostics=(exc.code,),
                        adapter_id=adapter_id,
                        adapter_version=adapter_version,
                        schema_version=record.schema_id,
                        ingested_at=observed_at,
                    )
                    append_result = self._ledger.append(
                        tenant=tenant,
                        source_row=source_row,
                        event=None,
                    )
                    quarantined_rows += 1
                else:
                    event_ids.append(normalized.event.event_id)
                    inserted_events += int(append_result.event_inserted)
                    duplicate_events += int(
                        not append_result.event_inserted
                    )
            except CanonicalLedgerError:
                raise
            except ValueError as exc:
                source_row = self._source_row(
                    tenant=tenant,
                    raw_file_id=raw_file_id,
                    source_file_sha256=record.sha256,
                    import_batch_id=import_batch_id,
                    row_number=row_number,
                    row=row,
                    raw_row_hash=raw_row_hash,
                    source_record_id=source_record_id,
                    source_row_key=fallback_key,
                    structural_fingerprint=record.structural_fingerprint,
                    semantic_fingerprint=record.semantic_fingerprint,
                    status=SourceRowStatus.QUARANTINED,
                    diagnostics=(f"NORMALIZATION_FAILED:{exc}",),
                    adapter_id=adapter_id,
                    adapter_version=adapter_version,
                    schema_version=record.schema_id,
                    ingested_at=observed_at,
                )
                append_result = self._ledger.append(
                    tenant=tenant,
                    source_row=source_row,
                    event=None,
                )
                quarantined_rows += 1

            inserted_source_rows += int(append_result.source_inserted)
            duplicate_source_rows += int(
                not append_result.source_inserted
            )

        return CanonicalImportResult(
            raw_file_id=raw_file_id,
            import_batch_id=import_batch_id,
            total_rows=len(rows),
            inserted_source_rows=inserted_source_rows,
            inserted_events=inserted_events,
            duplicate_source_rows=duplicate_source_rows,
            duplicate_events=duplicate_events,
            quarantined_rows=quarantined_rows,
            source_record_ids=tuple(source_record_ids),
            event_ids=tuple(event_ids),
        )
