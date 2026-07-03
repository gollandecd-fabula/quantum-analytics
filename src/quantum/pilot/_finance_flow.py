from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from quantum.ingestion.admission_v2 import DatasetAdmissionRecord

from ._bindings import MetricBindings, finance_result_snapshot
from ._finance_request import execute_finance_request
from ._scope import LocalPilotExecutionError, LocalPilotScope


def calculate_finance_results(
    *,
    scope: LocalPilotScope,
    admitted: DatasetAdmissionRecord,
    finance_requests: Mapping[str, Mapping[str, Any]],
    metric_bindings: MetricBindings,
    reconciled_at: datetime,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Any]]:
    if not isinstance(finance_requests, Mapping) or not finance_requests:
        raise LocalPilotExecutionError("PILOT_FINANCE_REQUESTS_REQUIRED")
    labels = tuple(finance_requests)
    if any(not isinstance(label, str) or not label for label in labels):
        raise LocalPilotExecutionError("PILOT_FINANCE_LABEL_INVALID")
    results: dict[str, Mapping[str, Any]] = {}
    for label in sorted(labels):
        results[label] = execute_finance_request(
            label=label,
            request=finance_requests[label],
            scope=scope,
            admitted_at=admitted.latest_decision.decided_at,
            reconciled_at=reconciled_at,
        )
    inspection = admitted.inspection
    if inspection is None:
        raise LocalPilotExecutionError("PILOT_INSPECTION_EVIDENCE_MISSING")
    snapshot = finance_result_snapshot(
        dataset_id=admitted.declaration.dataset_id,
        original_file_sha256=admitted.declaration.original_file_sha256,
        row_count=inspection.data_row_count,
        finance_results=results,
        metric_bindings=metric_bindings,
    )
    return results, snapshot


__all__ = ["calculate_finance_results"]
