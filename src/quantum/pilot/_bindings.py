from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from quantum.ingestion.admission_v2 import DatasetAdmissionRecord

from ._scope import LocalPilotExecutionError, secure_equal


MetricBindings = Mapping[str, tuple[tuple[str, str], ...]]


def _metric_view(metric: object) -> dict[str, Any]:
    if not isinstance(metric, Mapping):
        raise LocalPilotExecutionError(
            "PILOT_RECONCILIATION_METRIC_INVALID"
        )
    required = ("state", "value", "value_type", "unit", "currency")
    if any(key not in metric for key in required):
        raise LocalPilotExecutionError(
            "PILOT_RECONCILIATION_METRIC_INVALID"
        )
    return {key: metric[key] for key in required}


def _binding_metrics(
    finance_results: Mapping[str, Mapping[str, Any]],
    binding: object,
) -> list[dict[str, Any]]:
    if not isinstance(binding, tuple) or not binding:
        raise LocalPilotExecutionError(
            "PILOT_RECONCILIATION_BINDING_INVALID"
        )
    metrics: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for component in binding:
        if (
            not isinstance(component, tuple)
            or len(component) != 2
            or not all(isinstance(item, str) and item for item in component)
        ):
            raise LocalPilotExecutionError(
                "PILOT_RECONCILIATION_BINDING_INVALID"
            )
        if component in seen:
            raise LocalPilotExecutionError(
                "PILOT_RECONCILIATION_BINDING_DUPLICATE"
            )
        seen.add(component)
        label, result_metric = component
        result = finance_results.get(label)
        result_metrics = result.get("results") if isinstance(result, Mapping) else None
        if not isinstance(result_metrics, Mapping) or result_metric not in result_metrics:
            raise LocalPilotExecutionError(
                "PILOT_RECONCILIATION_BINDING_INVALID"
            )
        metrics.append(_metric_view(result_metrics[result_metric]))
    return metrics


def _sum_bound_metrics(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    first = metrics[0]
    signature = (
        first["value_type"],
        first["unit"],
        first["currency"],
    )
    if any(
        metric["state"] != "VALID"
        or (
            metric["value_type"],
            metric["unit"],
            metric["currency"],
        )
        != signature
        for metric in metrics
    ):
        raise LocalPilotExecutionError(
            "PILOT_RECONCILIATION_METRIC_NONVALID"
        )
    try:
        values = [Decimal(str(metric["value"])) for metric in metrics]
    except (InvalidOperation, ValueError) as exc:
        raise LocalPilotExecutionError(
            "PILOT_RECONCILIATION_METRIC_INVALID"
        ) from exc
    total = sum(values, Decimal(0))
    value_type, unit, currency = signature
    if value_type == "INTEGER":
        if total != total.to_integral_value():
            raise LocalPilotExecutionError(
                "PILOT_RECONCILIATION_METRIC_INVALID"
            )
        encoded = str(int(total))
    else:
        encoded = format(total, "f")
    return {
        "state": "VALID",
        "value": encoded,
        "value_type": value_type,
        "unit": unit,
        "currency": currency,
    }


def finance_result_snapshot(
    *,
    dataset_id: str,
    original_file_sha256: str,
    row_count: int,
    finance_results: Mapping[str, Mapping[str, Any]],
    metric_bindings: MetricBindings,
) -> dict[str, Any]:
    """Build a B2 snapshot only from explicit finance-result bindings."""
    if (
        not isinstance(row_count, int)
        or isinstance(row_count, bool)
        or row_count < 0
    ):
        raise LocalPilotExecutionError(
            "PILOT_RECONCILIATION_ROW_COUNT_INVALID"
        )
    if not isinstance(metric_bindings, Mapping) or not metric_bindings:
        raise LocalPilotExecutionError(
            "PILOT_RECONCILIATION_BINDINGS_REQUIRED"
        )
    totals: dict[str, dict[str, Any]] = {}
    for target_metric, binding in metric_bindings.items():
        if not isinstance(target_metric, str) or not target_metric:
            raise LocalPilotExecutionError(
                "PILOT_RECONCILIATION_BINDING_INVALID"
            )
        totals[target_metric] = _sum_bound_metrics(
            _binding_metrics(finance_results, binding)
        )
    return {
        "dataset_id": dataset_id,
        "original_file_sha256": original_file_sha256,
        "row_count": row_count,
        "totals": totals,
    }


def validate_source_identity(
    source_snapshot: object,
    admitted: DatasetAdmissionRecord,
) -> Mapping[str, Any]:
    if not isinstance(source_snapshot, Mapping):
        raise LocalPilotExecutionError("PILOT_SOURCE_SNAPSHOT_INVALID")
    dataset_id = source_snapshot.get("dataset_id")
    original_hash = source_snapshot.get("original_file_sha256")
    if (
        not isinstance(dataset_id, str)
        or not isinstance(original_hash, str)
        or not secure_equal(dataset_id, admitted.declaration.dataset_id)
        or not secure_equal(
            original_hash,
            admitted.declaration.original_file_sha256,
        )
    ):
        raise LocalPilotExecutionError(
            "PILOT_SOURCE_SNAPSHOT_IDENTITY_MISMATCH"
        )
    return source_snapshot


__all__ = [
    "MetricBindings",
    "finance_result_snapshot",
    "validate_source_identity",
]
