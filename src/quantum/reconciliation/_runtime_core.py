from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, localcontext
import re
from typing import Any

from quantum.finance._common import canonical_hash
from quantum.ingestion._admission_contracts_v2 import (
    DatasetAdmissionRecord,
    DatasetAdmissionState,
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_METRICS = 128
_MAX_DECIMAL_DIGITS = 1000


class ReconciliationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _safe_id(value: object, code: str) -> str:
    if not isinstance(value, str) or _SAFE_ID.fullmatch(value) is None:
        raise ReconciliationError(code)
    return value


def _sha(value: object, code: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ReconciliationError(code)
    return value


def _aware_utc(value: object) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ReconciliationError("RECONCILIATION_TIMESTAMP_INVALID")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _nonnegative_int(value: object, code: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ReconciliationError(code)
    return value


def _decimal(value: object, code: str) -> Decimal:
    if not isinstance(value, str) or not value or len(value) > _MAX_DECIMAL_DIGITS + 2:
        raise ReconciliationError(code)
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ReconciliationError(code) from exc
    if not result.is_finite() or len(result.as_tuple().digits) > _MAX_DECIMAL_DIGITS:
        raise ReconciliationError(code)
    return result


def _policy(policy: object) -> tuple[dict[str, Any], dict[str, Mapping[str, Any]]]:
    required = {"policy_id", "version", "content_hash", "row_count_tolerance", "metric_tolerances"}
    if not isinstance(policy, Mapping) or set(policy) != required:
        raise ReconciliationError("RECONCILIATION_POLICY_INVALID")
    policy_id = _safe_id(policy["policy_id"], "RECONCILIATION_POLICY_ID_INVALID")
    version = policy["version"]
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ReconciliationError("RECONCILIATION_POLICY_VERSION_INVALID")
    content_hash = _sha(policy["content_hash"], "RECONCILIATION_POLICY_HASH_INVALID")
    if content_hash != canonical_hash(policy, exclude=frozenset({"content_hash"})):
        raise ReconciliationError("RECONCILIATION_POLICY_HASH_MISMATCH")
    row_tolerance = _nonnegative_int(
        policy["row_count_tolerance"], "RECONCILIATION_ROW_TOLERANCE_INVALID"
    )
    tolerances = policy["metric_tolerances"]
    if (
        not isinstance(tolerances, Mapping)
        or not tolerances
        or len(tolerances) > _MAX_METRICS
    ):
        raise ReconciliationError("RECONCILIATION_METRIC_POLICY_INVALID")
    normalized: dict[str, Mapping[str, Any]] = {}
    for metric_id, raw in tolerances.items():
        metric_id = _safe_id(metric_id, "RECONCILIATION_METRIC_ID_INVALID")
        if not isinstance(raw, Mapping) or set(raw) != {
            "absolute", "value_type", "unit", "currency"
        }:
            raise ReconciliationError("RECONCILIATION_METRIC_POLICY_INVALID")
        tolerance = _decimal(raw["absolute"], "RECONCILIATION_TOLERANCE_INVALID")
        if tolerance < 0:
            raise ReconciliationError("RECONCILIATION_TOLERANCE_INVALID")
        _safe_id(raw["value_type"], "RECONCILIATION_SIGNATURE_INVALID")
        _safe_id(raw["unit"], "RECONCILIATION_SIGNATURE_INVALID")
        currency = raw["currency"]
        if currency is not None:
            _safe_id(currency, "RECONCILIATION_SIGNATURE_INVALID")
        normalized[metric_id] = dict(raw)
    return {
        "id": policy_id,
        "version": version,
        "content_hash": content_hash,
        "row_count_tolerance": row_tolerance,
    }, normalized


def _snapshot(snapshot: object, expected_metrics: set[str], code: str) -> dict[str, Any]:
    if not isinstance(snapshot, Mapping) or set(snapshot) != {
        "dataset_id", "original_file_sha256", "row_count", "totals"
    }:
        raise ReconciliationError(code)
    dataset_id = _safe_id(snapshot["dataset_id"], "RECONCILIATION_DATASET_ID_INVALID")
    file_hash = _sha(snapshot["original_file_sha256"], "RECONCILIATION_SOURCE_HASH_INVALID")
    row_count = _nonnegative_int(snapshot["row_count"], "RECONCILIATION_ROW_COUNT_INVALID")
    totals = snapshot["totals"]
    if not isinstance(totals, Mapping) or set(totals) != expected_metrics:
        raise ReconciliationError("RECONCILIATION_METRIC_SET_MISMATCH")
    return {
        "dataset_id": dataset_id,
        "original_file_sha256": file_hash,
        "row_count": row_count,
        "totals": totals,
    }


def _total(raw: object, policy: Mapping[str, Any]) -> Decimal:
    if not isinstance(raw, Mapping) or set(raw) != {
        "state", "value", "value_type", "unit", "currency"
    }:
        raise ReconciliationError("RECONCILIATION_TOTAL_INVALID")
    if raw["state"] != "VALID":
        raise ReconciliationError("RECONCILIATION_TOTAL_NOT_VALID")
    if (
        raw["value_type"] != policy["value_type"]
        or raw["unit"] != policy["unit"]
        or raw["currency"] != policy["currency"]
    ):
        raise ReconciliationError("RECONCILIATION_TOTAL_SIGNATURE_MISMATCH")
    return _decimal(raw["value"], "RECONCILIATION_TOTAL_VALUE_INVALID")


def reconcile_source_totals(
    *,
    admission_record: DatasetAdmissionRecord,
    tenant_id: str,
    account_id: str,
    source_snapshot: Mapping[str, Any],
    calculated_snapshot: Mapping[str, Any],
    policy: Mapping[str, Any],
    reconciled_at: datetime,
) -> dict[str, Any]:
    if not isinstance(admission_record, DatasetAdmissionRecord):
        raise ReconciliationError("RECONCILIATION_ADMISSION_RECORD_INVALID")
    if admission_record.state is not DatasetAdmissionState.ADMITTED:
        raise ReconciliationError("RECONCILIATION_DATASET_NOT_ADMITTED")

    declaration = admission_record.declaration
    if tenant_id != declaration.tenant_id:
        raise ReconciliationError("RECONCILIATION_DATASET_NOT_FOUND")
    if account_id != declaration.uploader_account_id:
        raise ReconciliationError("RECONCILIATION_DATASET_NOT_FOUND")

    policy_ref, metric_policies = _policy(policy)
    expected_metrics = set(metric_policies)
    source = _snapshot(source_snapshot, expected_metrics, "RECONCILIATION_SOURCE_INVALID")
    calculated = _snapshot(
        calculated_snapshot, expected_metrics, "RECONCILIATION_CALCULATED_INVALID"
    )

    expected_dataset_id = declaration.dataset_id.lower()
    expected_hash = declaration.original_file_sha256
    for snapshot in (source, calculated):
        if snapshot["dataset_id"].lower() != expected_dataset_id:
            raise ReconciliationError("RECONCILIATION_DATASET_BINDING_MISMATCH")
        if snapshot["original_file_sha256"] != expected_hash:
            raise ReconciliationError("RECONCILIATION_SOURCE_HASH_MISMATCH")

    row_delta = abs(source["row_count"] - calculated["row_count"])
    expected_row_match = (
        declaration.expected_row_count is None
        or source["row_count"] == declaration.expected_row_count
    )
    row_match = row_delta <= policy_ref["row_count_tolerance"] and expected_row_match

    metric_results: dict[str, Any] = {}
    all_metrics_match = True
    for metric_id in sorted(metric_policies):
        metric_policy = metric_policies[metric_id]
        source_value = _total(source["totals"][metric_id], metric_policy)
        calculated_value = _total(calculated["totals"][metric_id], metric_policy)
        tolerance = _decimal(
            metric_policy["absolute"], "RECONCILIATION_TOLERANCE_INVALID"
        )
        precision = min(
            _MAX_DECIMAL_DIGITS,
            max(
                len(source_value.as_tuple().digits),
                len(calculated_value.as_tuple().digits),
                len(tolerance.as_tuple().digits),
            ) + 8,
        )
        with localcontext() as context:
            context.prec = precision
            delta = abs(source_value - calculated_value)
        matches = delta <= tolerance
        all_metrics_match = all_metrics_match and matches
        metric_results[metric_id] = {
            "state": "MATCH" if matches else "CONFLICT",
            "source_value": str(source_value),
            "calculated_value": str(calculated_value),
            "absolute_delta": str(delta),
            "absolute_tolerance": str(tolerance),
            "value_type": metric_policy["value_type"],
            "unit": metric_policy["unit"],
            "currency": metric_policy["currency"],
        }

    state = "RECONCILED" if row_match and all_metrics_match else "CONFLICT"
    result = {
        "schema_version": "b2-source-reconciliation-v1",
        "state": state,
        "dataset_id": expected_dataset_id,
        "tenant_id": declaration.tenant_id,
        "account_id": declaration.uploader_account_id,
        "original_file_sha256": expected_hash,
        "policy_ref": {
            "id": policy_ref["id"],
            "version": policy_ref["version"],
            "content_hash": policy_ref["content_hash"],
        },
        "row_count": {
            "state": "MATCH" if row_match else "CONFLICT",
            "source": source["row_count"],
            "calculated": calculated["row_count"],
            "expected": declaration.expected_row_count,
            "absolute_delta": row_delta,
            "tolerance": policy_ref["row_count_tolerance"],
        },
        "metrics": metric_results,
        "reconciled_at": _aware_utc(reconciled_at),
        "evidence_hash": "",
    }
    result["evidence_hash"] = canonical_hash(
        result, exclude=frozenset({"evidence_hash"})
    )
    return result
