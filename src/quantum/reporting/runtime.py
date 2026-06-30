from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from quantum.evidence import verify_evidence_chain, verify_metric_snapshot

REPORT_SCHEMA_VERSION = "quantum-report-record-v1"
EXPORT_SCHEMA_VERSION = "quantum-report-export-v1"
MAX_PAGE_SIZE = 100
MAX_EXPORT_RECORDS = 10_000
MAX_EXPORT_BYTES = 10_000_000

_REPORT_FIELDS = frozenset({
    "report_record_id", "schema_version", "organization_id",
    "marketplace_account_id", "mode", "scenario_id", "accounting_view",
    "metric_snapshot_id", "snapshot_revision", "metric_content_hash",
    "evidence_chain_ref", "state", "value", "value_type", "unit",
    "currency", "reason_code", "expense_boundary", "rounding", "freshness",
    "confidence", "limitations", "publication_state", "generated_at",
})
_BUNDLE_FIELDS = frozenset({
    "schema_version", "bundle_id", "organization_id", "mode", "scenario_id",
    "generated_at", "record_count", "records", "bundle_hash",
})
_STATES = frozenset({
    "VALID", "EMPTY", "BLOCKED", "UNAVAILABLE", "CONFLICT", "INVALID",
    "NOT_APPLICABLE",
})
_PUBLICATION_STATES = frozenset({"PREVIEW_ONLY", "EVIDENCE_VERIFIED"})
_ACCOUNTING_VIEWS = frozenset({"OPERATIONAL", "SETTLEMENT", "TAX_RECOGNITION"})
_HASH_RE = re.compile(r"^[a-f0-9]{64}$")
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_CSV_FIELDS = (
    "report_record_id", "organization_id", "marketplace_account_id", "mode",
    "scenario_id", "accounting_view", "metric_snapshot_id", "state", "value",
    "currency", "unit", "evidence_chain_id", "evidence_chain_version",
    "publication_state", "record_json",
)


class ReportingError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class ReportPage:
    records: tuple[dict[str, Any], ...]
    next_cursor: str | None
    total_records: int


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReportingError("REPORT_JSON_INVALID") from exc


def _canonical_hash(document: Mapping[str, Any], excluded: frozenset[str]) -> str:
    payload = {key: value for key, value in document.items() if key not in excluded}
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _clone_json(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_rfc3339(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _generated_at(value: datetime | str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ReportingError("REPORT_TIMESTAMP_INVALID")
        return value.isoformat()
    if _is_rfc3339(value):
        return value
    raise ReportingError("REPORT_TIMESTAMP_INVALID")


def _validate_evidence_binding(
    snapshot: Mapping[str, Any],
    evidence_chain: Mapping[str, Any],
) -> None:
    errors = verify_evidence_chain(evidence_chain)
    if errors:
        raise ReportingError(f"REPORT_EVIDENCE_INVALID:{errors[0]}")
    ref = snapshot["evidence_chain_ref"]
    if (
        evidence_chain.get("evidence_chain_id") != ref.get("id")
        or evidence_chain.get("version") != ref.get("version")
        or evidence_chain.get("organization_id") != snapshot.get("organization_id")
        or evidence_chain.get("mode") != snapshot.get("mode")
        or evidence_chain.get("scenario_id") != snapshot.get("scenario_id")
    ):
        raise ReportingError("REPORT_EVIDENCE_BINDING_MISMATCH")


def build_report_record(
    snapshot: Mapping[str, Any],
    *,
    report_record_id: str,
    generated_at: datetime | str,
    evidence_chain: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not _is_nonempty_string(report_record_id):
        raise ReportingError("REPORT_RECORD_ID_INVALID")
    errors = verify_metric_snapshot(snapshot)
    if errors:
        raise ReportingError(f"REPORT_SNAPSHOT_INVALID:{errors[0]}")

    publication_state = "PREVIEW_ONLY"
    limitations = list(snapshot["limitations"])
    if evidence_chain is not None:
        _validate_evidence_binding(snapshot, evidence_chain)
        publication_state = "EVIDENCE_VERIFIED"
    elif "EVIDENCE_NOT_VERIFIED_FOR_PUBLICATION" not in limitations:
        limitations.append("EVIDENCE_NOT_VERIFIED_FOR_PUBLICATION")

    record = {
        "report_record_id": report_record_id,
        "schema_version": REPORT_SCHEMA_VERSION,
        "organization_id": snapshot["organization_id"],
        "marketplace_account_id": snapshot["marketplace_account_id"],
        "mode": snapshot["mode"],
        "scenario_id": snapshot["scenario_id"],
        "accounting_view": snapshot["accounting_view"],
        "metric_snapshot_id": snapshot["metric_snapshot_id"],
        "snapshot_revision": snapshot["snapshot_revision"],
        "metric_content_hash": snapshot["content_hash"],
        "evidence_chain_ref": _clone_json(snapshot["evidence_chain_ref"]),
        "state": snapshot["state"],
        "value": snapshot["value"],
        "value_type": snapshot["value_type"],
        "unit": snapshot["unit"],
        "currency": snapshot["currency"],
        "reason_code": snapshot["reason_code"],
        "expense_boundary": list(snapshot["expense_boundary"]),
        "rounding": _clone_json(snapshot["rounding"]),
        "freshness": {
            "state": snapshot["data_freshness_state"],
            "observed_at": snapshot["freshness_observed_at"],
            "deadline": snapshot["freshness_deadline"],
        },
        "confidence": {
            "state": snapshot["confidence_state"],
            "reasons": list(snapshot["confidence_reasons"]),
        },
        "limitations": limitations,
        "publication_state": publication_state,
        "generated_at": _generated_at(generated_at),
    }
    validate_report_record(record)
    return record


def validate_report_record(record: object) -> None:
    if not isinstance(record, Mapping) or set(record) != set(_REPORT_FIELDS):
        raise ReportingError("REPORT_RECORD_MALFORMED")
    if record.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ReportingError("REPORT_SCHEMA_VERSION_UNSUPPORTED")
    for field in (
        "report_record_id", "organization_id", "metric_snapshot_id",
        "metric_content_hash",
    ):
        if not _is_nonempty_string(record.get(field)):
            raise ReportingError("REPORT_RECORD_MALFORMED")
    if _HASH_RE.fullmatch(str(record.get("metric_content_hash"))) is None:
        raise ReportingError("REPORT_SNAPSHOT_HASH_INVALID")
    if not _is_positive_int(record.get("snapshot_revision")):
        raise ReportingError("REPORT_RECORD_MALFORMED")

    mode = record.get("mode")
    scenario_id = record.get("scenario_id")
    if mode not in ("ACTUAL", "SCENARIO"):
        raise ReportingError("REPORT_MODE_INVALID")
    if mode == "ACTUAL" and scenario_id is not None:
        raise ReportingError("REPORT_MODE_CONTAMINATION")
    if mode == "SCENARIO" and not _is_nonempty_string(scenario_id):
        raise ReportingError("REPORT_MODE_CONTAMINATION")
    marketplace_account_id = record.get("marketplace_account_id")
    if marketplace_account_id is not None and not _is_nonempty_string(
        marketplace_account_id
    ):
        raise ReportingError("REPORT_RECORD_MALFORMED")

    if record.get("accounting_view") not in _ACCOUNTING_VIEWS:
        raise ReportingError("REPORT_ACCOUNTING_VIEW_INVALID")
    if record.get("state") not in _STATES:
        raise ReportingError("REPORT_STATE_INVALID")
    if record.get("publication_state") not in _PUBLICATION_STATES:
        raise ReportingError("REPORT_PUBLICATION_STATE_INVALID")
    if not _is_rfc3339(record.get("generated_at")):
        raise ReportingError("REPORT_TIMESTAMP_INVALID")

    evidence_ref = record.get("evidence_chain_ref")
    if (
        not isinstance(evidence_ref, Mapping)
        or set(evidence_ref) != {"id", "version"}
        or not _is_nonempty_string(evidence_ref.get("id"))
        or not _is_positive_int(evidence_ref.get("version"))
    ):
        raise ReportingError("REPORT_EVIDENCE_REF_INVALID")

    state = record["state"]
    if state == "VALID":
        if record.get("value") is None:
            raise ReportingError("REPORT_VALUE_INVALID")
        if not _is_nonempty_string(record.get("value_type")):
            raise ReportingError("REPORT_VALUE_INVALID")
        if not _is_nonempty_string(record.get("unit")):
            raise ReportingError("REPORT_VALUE_INVALID")
        if record.get("reason_code") is not None:
            raise ReportingError("REPORT_VALUE_INVALID")
        if record.get("value_type") == "MONEY":
            if (
                not isinstance(record.get("currency"), str)
                or _CURRENCY_RE.fullmatch(record["currency"]) is None
            ):
                raise ReportingError("REPORT_CURRENCY_INVALID")
        elif record.get("currency") is not None:
            raise ReportingError("REPORT_CURRENCY_INVALID")
    else:
        if any(
            record.get(field) is not None
            for field in ("value", "value_type", "unit", "currency")
        ):
            raise ReportingError("REPORT_STATE_VALUE_MISMATCH")
        if not _is_nonempty_string(record.get("reason_code")):
            raise ReportingError("REPORT_REASON_REQUIRED")

    if not isinstance(record.get("expense_boundary"), list) or len(
        record["expense_boundary"]
    ) != len(set(record["expense_boundary"])):
        raise ReportingError("REPORT_EXPENSE_BOUNDARY_INVALID")
    if not isinstance(record.get("rounding"), Mapping):
        raise ReportingError("REPORT_ROUNDING_INVALID")
    if not isinstance(record.get("freshness"), Mapping):
        raise ReportingError("REPORT_FRESHNESS_INVALID")
    if not isinstance(record.get("confidence"), Mapping):
        raise ReportingError("REPORT_CONFIDENCE_INVALID")
    if not isinstance(record.get("limitations"), list) or any(
        not _is_nonempty_string(item) for item in record["limitations"]
    ):
        raise ReportingError("REPORT_LIMITATIONS_INVALID")


def build_export_bundle(
    records: Iterable[Mapping[str, Any]],
    *,
    bundle_id: str,
    generated_at: datetime | str,
) -> dict[str, Any]:
    if not _is_nonempty_string(bundle_id):
        raise ReportingError("EXPORT_BUNDLE_ID_INVALID")
    materialized = [_clone_json(record) for record in records]
    if not materialized:
        raise ReportingError("EXPORT_EMPTY")
    if len(materialized) > MAX_EXPORT_RECORDS:
        raise ReportingError("EXPORT_RECORD_LIMIT_EXCEEDED")
    for record in materialized:
        validate_report_record(record)

    organization_ids = {record["organization_id"] for record in materialized}
    modes = {record["mode"] for record in materialized}
    scenario_ids = {record["scenario_id"] for record in materialized}
    if len(organization_ids) != 1:
        raise ReportingError("EXPORT_TENANT_MIXED")
    if len(modes) != 1 or len(scenario_ids) != 1:
        raise ReportingError("EXPORT_MODE_MIXED")

    bundle = {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "organization_id": materialized[0]["organization_id"],
        "mode": materialized[0]["mode"],
        "scenario_id": materialized[0]["scenario_id"],
        "generated_at": _generated_at(generated_at),
        "record_count": len(materialized),
        "records": materialized,
        "bundle_hash": "",
    }
    bundle["bundle_hash"] = _canonical_hash(bundle, frozenset({"bundle_hash"}))
    validate_export_bundle(bundle)
    return bundle


def validate_export_bundle(bundle: object) -> None:
    if not isinstance(bundle, Mapping) or set(bundle) != set(_BUNDLE_FIELDS):
        raise ReportingError("EXPORT_BUNDLE_MALFORMED")
    if bundle.get("schema_version") != EXPORT_SCHEMA_VERSION:
        raise ReportingError("EXPORT_SCHEMA_VERSION_UNSUPPORTED")
    if not _is_nonempty_string(bundle.get("bundle_id")):
        raise ReportingError("EXPORT_BUNDLE_MALFORMED")
    if not _is_rfc3339(bundle.get("generated_at")):
        raise ReportingError("EXPORT_TIMESTAMP_INVALID")
    records = bundle.get("records")
    if not isinstance(records, list) or not records:
        raise ReportingError("EXPORT_EMPTY")
    if len(records) > MAX_EXPORT_RECORDS:
        raise ReportingError("EXPORT_RECORD_LIMIT_EXCEEDED")
    if bundle.get("record_count") != len(records):
        raise ReportingError("EXPORT_COUNT_MISMATCH")
    for record in records:
        validate_report_record(record)
        if record["organization_id"] != bundle.get("organization_id"):
            raise ReportingError("EXPORT_TENANT_MIXED")
        if (
            record["mode"] != bundle.get("mode")
            or record["scenario_id"] != bundle.get("scenario_id")
        ):
            raise ReportingError("EXPORT_MODE_MIXED")
    supplied_hash = bundle.get("bundle_hash")
    if (
        not isinstance(supplied_hash, str)
        or _HASH_RE.fullmatch(supplied_hash) is None
        or supplied_hash != _canonical_hash(bundle, frozenset({"bundle_hash"}))
    ):
        raise ReportingError("EXPORT_HASH_MISMATCH")


def export_bundle_json(bundle: Mapping[str, Any]) -> bytes:
    validate_export_bundle(bundle)
    payload = _canonical_json(bundle).encode("utf-8")
    if len(payload) > MAX_EXPORT_BYTES:
        raise ReportingError("EXPORT_BYTE_LIMIT_EXCEEDED")
    return payload


def import_bundle_json(payload: bytes) -> dict[str, Any]:
    if not isinstance(payload, bytes) or len(payload) > MAX_EXPORT_BYTES:
        raise ReportingError("EXPORT_BYTE_LIMIT_EXCEEDED")
    try:
        bundle = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReportingError("EXPORT_JSON_INVALID") from exc
    validate_export_bundle(bundle)
    return bundle


def export_records_jsonl(records: Sequence[Mapping[str, Any]]) -> bytes:
    materialized = [_clone_json(record) for record in records]
    if len(materialized) > MAX_EXPORT_RECORDS:
        raise ReportingError("EXPORT_RECORD_LIMIT_EXCEEDED")
    for record in materialized:
        validate_report_record(record)
    payload = ("\n".join(_canonical_json(record) for record in materialized) + "\n").encode("utf-8")
    if len(payload) > MAX_EXPORT_BYTES:
        raise ReportingError("EXPORT_BYTE_LIMIT_EXCEEDED")
    return payload


def import_records_jsonl(payload: bytes) -> tuple[dict[str, Any], ...]:
    if not isinstance(payload, bytes) or len(payload) > MAX_EXPORT_BYTES:
        raise ReportingError("EXPORT_BYTE_LIMIT_EXCEEDED")
    try:
        lines = payload.decode("utf-8").splitlines()
        records = tuple(json.loads(line) for line in lines if line)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReportingError("EXPORT_JSON_INVALID") from exc
    if len(records) > MAX_EXPORT_RECORDS:
        raise ReportingError("EXPORT_RECORD_LIMIT_EXCEEDED")
    for record in records:
        validate_report_record(record)
    return records


def export_records_csv(records: Sequence[Mapping[str, Any]]) -> bytes:
    materialized = [_clone_json(record) for record in records]
    if len(materialized) > MAX_EXPORT_RECORDS:
        raise ReportingError("EXPORT_RECORD_LIMIT_EXCEEDED")
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=_CSV_FIELDS, extrasaction="raise")
    writer.writeheader()
    for record in materialized:
        validate_report_record(record)
        ref = record["evidence_chain_ref"]
        writer.writerow({
            "report_record_id": record["report_record_id"],
            "organization_id": record["organization_id"],
            "marketplace_account_id": record["marketplace_account_id"] or "",
            "mode": record["mode"],
            "scenario_id": record["scenario_id"] or "",
            "accounting_view": record["accounting_view"],
            "metric_snapshot_id": record["metric_snapshot_id"],
            "state": record["state"],
            "value": "" if record["value"] is None else str(record["value"]),
            "currency": record["currency"] or "",
            "unit": record["unit"] or "",
            "evidence_chain_id": ref["id"],
            "evidence_chain_version": str(ref["version"]),
            "publication_state": record["publication_state"],
            "record_json": _canonical_json(record),
        })
    payload = output.getvalue().encode("utf-8")
    if len(payload) > MAX_EXPORT_BYTES:
        raise ReportingError("EXPORT_BYTE_LIMIT_EXCEEDED")
    return payload


def import_records_csv(payload: bytes) -> tuple[dict[str, Any], ...]:
    if not isinstance(payload, bytes) or len(payload) > MAX_EXPORT_BYTES:
        raise ReportingError("EXPORT_BYTE_LIMIT_EXCEEDED")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ReportingError("EXPORT_CSV_INVALID") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if reader.fieldnames != list(_CSV_FIELDS):
        raise ReportingError("EXPORT_CSV_HEADER_INVALID")
    records: list[dict[str, Any]] = []
    try:
        for row in reader:
            if None in row:
                raise ReportingError("EXPORT_CSV_INVALID")
            record = json.loads(row["record_json"])
            validate_report_record(record)
            ref = record["evidence_chain_ref"]
            projection = {
                "report_record_id": record["report_record_id"],
                "organization_id": record["organization_id"],
                "marketplace_account_id": record["marketplace_account_id"] or "",
                "mode": record["mode"],
                "scenario_id": record["scenario_id"] or "",
                "accounting_view": record["accounting_view"],
                "metric_snapshot_id": record["metric_snapshot_id"],
                "state": record["state"],
                "value": "" if record["value"] is None else str(record["value"]),
                "currency": record["currency"] or "",
                "unit": record["unit"] or "",
                "evidence_chain_id": ref["id"],
                "evidence_chain_version": str(ref["version"]),
                "publication_state": record["publication_state"],
            }
            if any(row[key] != value for key, value in projection.items()):
                raise ReportingError("EXPORT_CSV_PROJECTION_MISMATCH")
            records.append(record)
    except (csv.Error, json.JSONDecodeError) as exc:
        raise ReportingError("EXPORT_CSV_INVALID") from exc
    if len(records) > MAX_EXPORT_RECORDS:
        raise ReportingError("EXPORT_RECORD_LIMIT_EXCEEDED")
    return tuple(records)


def _records_digest(records: Sequence[Mapping[str, Any]]) -> str:
    identity = [
        [record["report_record_id"], record["metric_content_hash"]]
        for record in records
    ]
    return hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()


def _encode_cursor(offset: int, digest: str) -> str:
    raw = _canonical_json({"offset": offset, "digest": digest}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, digest: str) -> int:
    if not _is_nonempty_string(cursor):
        raise ReportingError("REPORT_CURSOR_INVALID")
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode((cursor + padding).encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReportingError("REPORT_CURSOR_INVALID") from exc
    if (
        not isinstance(data, Mapping)
        or set(data) != {"offset", "digest"}
        or not isinstance(data.get("offset"), int)
        or isinstance(data.get("offset"), bool)
        or data["offset"] < 0
        or data.get("digest") != digest
    ):
        raise ReportingError("REPORT_CURSOR_INVALID")
    return data["offset"]


def page_records(
    records: Sequence[Mapping[str, Any]],
    *,
    limit: int,
    cursor: str | None = None,
) -> ReportPage:
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or limit < 1
        or limit > MAX_PAGE_SIZE
    ):
        raise ReportingError("REPORT_PAGE_LIMIT_INVALID")
    materialized = [_clone_json(record) for record in records]
    for record in materialized:
        validate_report_record(record)
    digest = _records_digest(materialized)
    offset = 0 if cursor is None else _decode_cursor(cursor, digest)
    if offset > len(materialized):
        raise ReportingError("REPORT_CURSOR_INVALID")
    page = materialized[offset : offset + limit]
    next_offset = offset + len(page)
    next_cursor = _encode_cursor(next_offset, digest) if next_offset < len(materialized) else None
    return ReportPage(records=tuple(page), next_cursor=next_cursor, total_records=len(materialized))
