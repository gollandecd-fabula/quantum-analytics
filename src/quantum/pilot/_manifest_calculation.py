from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from ._bindings import MetricBindings
from ._manifest_common import integer, mapping, text
from ._scope import LocalPilotExecutionError


def build_finance_requests(value: object) -> dict[str, Mapping[str, Any]]:
    item = mapping(value, "PILOT_FINANCE_REQUESTS_INVALID")
    if not item:
        raise LocalPilotExecutionError("PILOT_FINANCE_REQUESTS_INVALID")
    output: dict[str, Mapping[str, Any]] = {}
    for label, request in item.items():
        normalized = text(label, "PILOT_FINANCE_LABEL_INVALID")
        output[normalized] = deepcopy(
            mapping(request, "PILOT_FINANCE_REQUEST_INVALID")
        )
    return output


def build_source_snapshot(
    value: object,
    *,
    dataset_id: str,
    original_file_sha256: str,
) -> dict[str, Any]:
    item = mapping(value, "PILOT_SOURCE_SNAPSHOT_INVALID")
    if set(item) != {"row_count", "totals"}:
        raise LocalPilotExecutionError("PILOT_SOURCE_SNAPSHOT_INVALID")
    totals = mapping(item["totals"], "PILOT_SOURCE_SNAPSHOT_INVALID")
    if not totals:
        raise LocalPilotExecutionError("PILOT_SOURCE_SNAPSHOT_INVALID")
    return {
        "dataset_id": dataset_id,
        "original_file_sha256": original_file_sha256,
        "row_count": integer(item["row_count"], "PILOT_SOURCE_SNAPSHOT_INVALID"),
        "totals": deepcopy(dict(totals)),
    }


def build_metric_bindings(
    value: object,
    *,
    finance_labels: set[str],
) -> MetricBindings:
    item = mapping(value, "PILOT_RECONCILIATION_BINDINGS_REQUIRED")
    if not item:
        raise LocalPilotExecutionError("PILOT_RECONCILIATION_BINDINGS_REQUIRED")
    output: dict[str, tuple[tuple[str, str], ...]] = {}
    for target, raw_components in item.items():
        target_id = text(target, "PILOT_RECONCILIATION_BINDING_INVALID")
        if not isinstance(raw_components, list) or not raw_components:
            raise LocalPilotExecutionError("PILOT_RECONCILIATION_BINDING_INVALID")
        components: list[tuple[str, str]] = []
        for raw in raw_components:
            if not isinstance(raw, list) or len(raw) != 2:
                raise LocalPilotExecutionError("PILOT_RECONCILIATION_BINDING_INVALID")
            label = text(raw[0], "PILOT_RECONCILIATION_BINDING_INVALID")
            metric_id = text(raw[1], "PILOT_RECONCILIATION_BINDING_INVALID")
            if label not in finance_labels:
                raise LocalPilotExecutionError("PILOT_RECONCILIATION_BINDING_INVALID")
            components.append((label, metric_id))
        output[target_id] = tuple(components)
    return output


def build_reconciliation_policy(value: object) -> Mapping[str, Any]:
    return deepcopy(mapping(value, "PILOT_RECONCILIATION_POLICY_INVALID"))


__all__ = [
    "build_finance_requests",
    "build_metric_bindings",
    "build_reconciliation_policy",
    "build_source_snapshot",
]
