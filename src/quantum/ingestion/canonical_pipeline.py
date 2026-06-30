from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from io import StringIO

from quantum.access import TenantContext
from quantum.adapters.wildberries.synthetic import NormalizedRow, normalize_row
from quantum.domain.events import CanonicalEvent
from quantum.domain.idempotency import canonical_json_hash
from quantum.domain.source_rows import ImmutableSourceRow, SourceRowStatus
from quantum.infrastructure.in_memory_canonical_ledger import (
    CanonicalLedgerError,
    InMemoryCanonicalLedger,
)
from quantum.ingestion.storage import LocalRawStorage, RawFileState


_MISSING_DEPENDENCY_CODES = {
    "EVENT_SUPERSEDED_TARGET_MISSING",
    "EVENT_REVERSAL_TARGET_MISSING",
}
_ROW_QUARANTINE_CODES = {
    "EVENT_SUPERSESSION_INVALID",
    "EVENT_REVERSAL_INVALID",
    "EVENT_REVERSAL_REQUIRED",
    "EVENT_REVERSAL_EXCEEDS_ORIGINAL",
    "EVENT_REVERSAL_UNIT_MISMATCH",
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
    inserted_quarantined_rows: int
    duplicate_quarantined_rows: int
    source_record_ids: tuple[str, ...]
    event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Candidate:
    source_row: ImmutableSourceRow
    event: CanonicalEvent


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
        source_file_sha256: str,
        schema_version: str,
        adapter_id: str,
        adapter_version: str,
    ) -> str:
        digest = sha256(
            "\x1f".join(
                (
                    tenant_id,
                    source_file_sha256,
                    schema_version,
                    adapter_id,
                    adapter_version,
                )
            ).encode("utf-8")
        ).hexdigest()
        return f"batch-{digest[:24]}"

    @staticmethod
    def _source_record_id(
        *,
        tenant_id: str,
        source_file_sha256: str,
        row_number: int,
        raw_row_hash: str,
    ) -> str:
        digest = sha256(
            "\x1f".join(
                (
                    tenant_id,
                    source_file_sha256,
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

    @classmethod
    def _quarantine_candidate(
        cls,
        candidate: _Candidate,
        diagnostics: tuple[str, ...],
    ) -> ImmutableSourceRow:
        row = candidate.source_row
        return ImmutableSourceRow(
            source_record_id=row.source_record_id,
            tenant_id=row.tenant_id,
            raw_file_id=row.raw_file_id,
            source_file_sha256=row.source_file_sha256,
            import_batch_id=row.import_batch_id,
            row_number=row.row_number,
            source_row_key=row.source_row_key,
            raw_row_hash=row.raw_row_hash,
            raw_payload=row.raw_payload,
            structural_fingerprint=row.structural_fingerprint,
            semantic_fingerprint=row.semantic_fingerprint,
            validation_status=SourceRowStatus.QUARANTINED,
            diagnostics=diagnostics,
            adapter_id=row.adapter_id,
            adapter_version=row.adapter_version,
            schema_version=row.schema_version,
            ingested_at=row.ingested_at,
        )

    @staticmethod
    def _candidate_order(
        candidate: _Candidate,
        superseded_targets: set[str],
    ) -> tuple[int, datetime, str]:
        event = candidate.event
        if event.supersedes_event_id is not None:
            rank = 0
        elif event.event_id in superseded_targets:
            rank = 1
        else:
            rank = 2
        return rank, event.recognition_time, event.event_id

    def _resolve_batch(
        self,
        *,
        tenant: TenantContext,
        immediate: list[ImmutableSourceRow],
        candidates: list[_Candidate],
    ) -> list[tuple[ImmutableSourceRow, CanonicalEvent | None]]:
        staging = self._ledger.fork()
        planned: list[tuple[ImmutableSourceRow, CanonicalEvent | None]] = []
        for source_row in immediate:
            staging.append(tenant=tenant, source_row=source_row, event=None)
            planned.append((source_row, None))

        pending = list(candidates)
        while pending:
            superseded_targets = {
                candidate.event.supersedes_event_id
                for candidate in pending
                if candidate.event.supersedes_event_id is not None
            }
            ordered = sorted(
                pending,
                key=lambda item: self._candidate_order(
                    item,
                    superseded_targets,
                ),
            )
            progress = False
            for candidate in ordered:
                try:
                    staging.append(
                        tenant=tenant,
                        source_row=candidate.source_row,
                        event=candidate.event,
                    )
                except CanonicalLedgerError as exc:
                    if exc.code in _MISSING_DEPENDENCY_CODES:
                        continue
                    if exc.code not in _ROW_QUARANTINE_CODES:
                        raise
                    quarantined = self._quarantine_candidate(
                        candidate,
                        (exc.code,),
                    )
                    staging.append(
                        tenant=tenant,
                        source_row=quarantined,
                        event=None,
                    )
                    planned.append((quarantined, None))
                else:
                    planned.append((candidate.source_row, candidate.event))
                pending.remove(candidate)
                progress = True
                break
            if not progress:
                raise CanonicalLedgerError("BATCH_DEPENDENCY_UNRESOLVED")
        return planned

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
        if not isinstance(marketplace_account_id, str) or not marketplace_account_id:
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

        record = self._storage.get_record(tenant=tenant, raw_file_id=raw_file_id)
        if record.state is not RawFileState.VALID:
            raise CanonicalLedgerError("RAW_FILE_NOT_VALID")
        if record.schema_id != "wb-synthetic-operations-v1":
            raise CanonicalLedgerError("SOURCE_SCHEMA_UNSUPPORTED")
        if not isinstance(record.structural_fingerprint, dict):
            raise CanonicalLedgerError("STRUCTURAL_FINGERPRINT_REQUIRED")
        if not isinstance(record.semantic_fingerprint, dict):
            raise CanonicalLedgerError("SEMANTIC_FINGERPRINT_REQUIRED")

        rows = self._strict_rows(
            self._storage.read(tenant=tenant, raw_file_id=raw_file_id)
        )
        import_batch_id = self._batch_id(
            tenant_id=tenant.tenant_id,
            source_file_sha256=record.sha256,
            schema_version=record.schema_id,
            adapter_id=adapter_id,
            adapter_version=adapter_version,
        )
        trace_id = f"trace-{import_batch_id.removeprefix('batch-')}"
        immediate: list[ImmutableSourceRow] = []
        candidates: list[_Candidate] = []
        source_record_ids: list[str] = []

        for row_number, row in enumerate(rows, start=2):
            raw_row_hash = canonical_json_hash(row)
            source_record_id = self._source_record_id(
                tenant_id=tenant.tenant_id,
                source_file_sha256=record.sha256,
                row_number=row_number,
                raw_row_hash=raw_row_hash,
            )
            source_record_ids.append(source_record_id)
            fallback_key = f"csv:row:{row.get('row_id') or row_number}"
            try:
                normalized: NormalizedRow = normalize_row(
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
            except ValueError as exc:
                immediate.append(
                    self._source_row(
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
                )
                continue
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
            candidates.append(_Candidate(source_row, normalized.event))

        planned = self._resolve_batch(
            tenant=tenant,
            immediate=immediate,
            candidates=candidates,
        )
        results = self._ledger.append_batch(tenant=tenant, items=planned)

        inserted_source_rows = sum(item.source_inserted for item in results)
        inserted_events = sum(item.event_inserted for item in results)
        duplicate_source_rows = len(results) - inserted_source_rows
        event_pairs = [
            (event, result)
            for (_, event), result in zip(planned, results, strict=True)
            if event is not None
        ]
        duplicate_events = sum(not result.event_inserted for _, result in event_pairs)
        quarantine_pairs = [
            result
            for (_, event), result in zip(planned, results, strict=True)
            if event is None
        ]
        inserted_quarantined = sum(item.source_inserted for item in quarantine_pairs)
        quarantined_rows = len(quarantine_pairs)

        return CanonicalImportResult(
            raw_file_id=raw_file_id,
            import_batch_id=import_batch_id,
            total_rows=len(rows),
            inserted_source_rows=inserted_source_rows,
            inserted_events=inserted_events,
            duplicate_source_rows=duplicate_source_rows,
            duplicate_events=duplicate_events,
            quarantined_rows=quarantined_rows,
            inserted_quarantined_rows=inserted_quarantined,
            duplicate_quarantined_rows=quarantined_rows - inserted_quarantined,
            source_record_ids=tuple(source_record_ids),
            event_ids=tuple(event.event_id for event, _ in event_pairs),
        )
