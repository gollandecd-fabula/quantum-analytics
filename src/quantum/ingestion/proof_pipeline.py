from __future__ import annotations

import csv
import hashlib
import json
import shutil
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from quantum.adapters.wildberries.synthetic import normalize_row, validate_row
from quantum.ingestion.fingerprints import semantic_fingerprint
from quantum.ingestion.schema_registry import detect_csv_schema
from quantum.infrastructure.json_event_ledger import JsonEventLedger
from quantum.infrastructure.local_raw_storage import LocalImmutableRawStorage


@dataclass(frozen=True, slots=True)
class ImportProofResult:
    status: str
    file_sha256: str
    structural_fingerprint: dict[str, object]
    semantic_fingerprint: dict[str, object] | None
    inserted_events: int
    duplicate_events: int
    quarantined: bool
    diagnostics: tuple[str, ...]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _quarantine(
    *,
    source_path: Path,
    quarantine_root: Path,
    file_hash: str,
    reason: str,
    diagnostics: list[str],
    structural: dict[str, object],
    semantic: dict[str, object] | None,
) -> ImportProofResult:
    target_dir = quarantine_root / file_hash
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, target_dir / source_path.name)

    evidence = {
        "status": "QUARANTINED",
        "reason": reason,
        "diagnostics": diagnostics,
        "source_file_sha256": file_hash,
        "structural_fingerprint": structural,
        "semantic_fingerprint": semantic,
    }
    (target_dir / "diagnostics.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return ImportProofResult(
        status="QUARANTINED",
        file_sha256=file_hash,
        structural_fingerprint=structural,
        semantic_fingerprint=semantic,
        inserted_events=0,
        duplicate_events=0,
        quarantined=True,
        diagnostics=tuple(diagnostics),
    )


def import_csv_for_proof(
    *,
    source_path: Path,
    raw_storage_root: Path,
    quarantine_root: Path,
    ledger_path: Path,
    source_records_path: Path,
    organization_id: str = "org-synthetic",
    marketplace_account_id: str = "wb-synthetic-account",
) -> ImportProofResult:
    file_hash = file_sha256(source_path)
    detection = detect_csv_schema(source_path)
    structural = detection.structural_fingerprint

    if detection.status != "MATCHED":
        return _quarantine(
            source_path=source_path,
            quarantine_root=quarantine_root,
            file_hash=file_hash,
            reason="UNKNOWN_SCHEMA",
            diagnostics=list(detection.diagnostics),
            structural=structural,
            semantic=None,
        )

    with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    semantic = semantic_fingerprint(rows)
    validation_errors: list[str] = []
    for source_line, row in enumerate(rows, start=2):
        try:
            validate_row(row)
        except ValueError as exc:
            validation_errors.append(f"row={source_line}: {exc}")

    if validation_errors:
        return _quarantine(
            source_path=source_path,
            quarantine_root=quarantine_root,
            file_hash=file_hash,
            reason="SEMANTIC_VALIDATION_FAILED",
            diagnostics=validation_errors,
            structural=structural,
            semantic=semantic,
        )

    storage = LocalImmutableRawStorage(raw_storage_root)
    with source_path.open("rb") as stream:
        storage.put_immutable(
            storage_key=f"sha256/{file_hash[:2]}/{file_hash}",
            stream=stream,
            expected_sha256=file_hash,
        )

    ledger = JsonEventLedger(ledger_path)
    source_records_path.parent.mkdir(parents=True, exist_ok=True)
    source_records: dict[str, dict[str, Any]] = {}

    if source_records_path.exists():
        for line in source_records_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                source_records[item["source_record_id"]] = item

    import_batch_id = f"batch-{file_hash[:16]}"
    trace_id = f"trace-{file_hash[:16]}"
    inserted = 0
    duplicates = 0

    for row in rows:
        source_record_id = f"src-{file_hash[:12]}-{row['row_id']}"
        normalized = normalize_row(
            row,
            organization_id=organization_id,
            marketplace_account_id=marketplace_account_id,
            import_batch_id=import_batch_id,
            source_record_id=source_record_id,
            source_file_sha256=file_hash,
            schema_version=detection.schema_id or "UNAVAILABLE",
            adapter_id=detection.adapter_id or "UNAVAILABLE",
            adapter_version=detection.adapter_version or "UNAVAILABLE",
            trace_id=trace_id,
        )

        source_records.setdefault(
            source_record_id,
            {
                "source_record_id": source_record_id,
                "import_batch_id": import_batch_id,
                "source_row_key": normalized.source_row_key,
                "raw_row_hash": normalized.raw_row_hash,
                "raw_payload": dict(row),
                "structural_fingerprint": structural["sha256"],
                "semantic_fingerprint": semantic["sha256"],
                "validation_status": "VALID",
                "adapter_id": detection.adapter_id,
                "adapter_version": detection.adapter_version,
                "created_at": row["recognition_time"],
            },
        )

        if ledger.add_if_absent(normalized.event):
            inserted += 1
        else:
            duplicates += 1

    with source_records_path.open("w", encoding="utf-8") as handle:
        for source_record_id in sorted(source_records):
            handle.write(
                json.dumps(source_records[source_record_id], ensure_ascii=False) + "\n"
            )

    return ImportProofResult(
        status="PUBLISHED",
        file_sha256=file_hash,
        structural_fingerprint=structural,
        semantic_fingerprint=semantic,
        inserted_events=inserted,
        duplicate_events=duplicates,
        quarantined=False,
        diagnostics=(),
    )


def build_metric_evidence(
    *,
    ledger_path: Path,
    source_file_sha256: str,
    source_records_path: Path,
) -> dict[str, Any]:
    events = JsonEventLedger(ledger_path).list_events()

    superseded_ids = {
        event["supersedes_event_id"]
        for event in events
        if event["supersedes_event_id"]
    }
    reversed_ids = {
        event["reversal_of_event_id"]
        for event in events
        if event["reversal_of_event_id"]
    }

    active_sales = [
        event
        for event in events
        if event["event_type"] == "SALE_RECOGNIZED"
        and event["event_id"] not in superseded_ids
        and event["event_id"] not in reversed_ids
    ]

    amount = sum(
        Decimal(event["payload"]["gross_amount"]["value"])
        for event in active_sales
    )

    excluded: list[dict[str, str]] = []
    for event in events:
        if event["event_id"] in superseded_ids:
            excluded.append({"event_id": event["event_id"], "reason": "SUPERSEDED"})
        if event["event_id"] in reversed_ids:
            excluded.append({"event_id": event["event_id"], "reason": "REVERSED"})

    return {
        "metric_id": "proof.current_gross_sales_amount",
        "metric_version": "1.0",
        "state": "VALID",
        "value": format(amount, "f"),
        "value_type": "decimal",
        "unit": "RUB",
        "calculation_profile_version": "a6-proof-profile-v1",
        "rounding_policy_version": "no-rounding-proof-v1",
        "active_event_ids": sorted(event["event_id"] for event in active_sales),
        "excluded_events": sorted(excluded, key=lambda item: item["event_id"]),
        "canonical_event_ids": sorted(event["event_id"] for event in events),
        "source_record_ids": sorted({
            event["source_record_id"]
            for event in events
        }),
        "source_records_file": source_records_path.name,
        "source_file_sha256": source_file_sha256,
        "normalization_rule_versions": ["wb-synthetic-normalization-v1"],
        "limitations": [
            "synthetic_data_only",
            "not_a_production_financial_metric",
            "no_tax_cost_or_other_expense_rules_applied",
        ],
    }
