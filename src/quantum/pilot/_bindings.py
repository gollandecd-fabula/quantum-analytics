from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._metric_values import bound_metrics, sum_metrics
from ._scope import LocalPilotExecutionError
from ._source_binding import validate_source_identity

MetricBindings = Mapping[str, tuple[tuple[str, str], ...]]


def finance_result_snapshot(
    *,
    dataset_id: str,
    original_file_sha256: str,
    row_count: int,
    finance_results: Mapping[str, Mapping[str, Any]],
    metric_bindings: MetricBindings,
) -> dict[str, Any]:
    if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 0:
        raise LocalPilotExecutionError("PILOT_RECONCILIATION_ROW_COUNT_INVALID")
    if not isinstance(metric_bindings, Mapping) or not metric_bindings:
        raise LocalPilotExecutionError("PILOT_RECONCILIATION_BINDINGS_REQUIRED")
    totals: dict[str, dict[str, Any]] = {}
    for target, binding in metric_bindings.items():
        if not isinstance(target, str) or not target:
            raise LocalPilotExecutionError("PILOT_RECONCILIATION_BINDING_INVALID")
        totals[target] = sum_metrics(bound_metrics(finance_results, binding))
    return {
        "dataset_id": dataset_id,
        "original_file_sha256": original_file_sha256,
        "row_count": row_count,
        "totals": totals,
    }


__all__ = ["MetricBindings", "finance_result_snapshot", "validate_source_identity"]
