from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from ._scope import LocalPilotExecutionError


def metric_view(metric: object) -> dict[str, Any]:
    if not isinstance(metric, Mapping):
        raise LocalPilotExecutionError("PILOT_RECONCILIATION_METRIC_INVALID")
    keys = ("state", "value", "value_type", "unit", "currency")
    if any(key not in metric for key in keys):
        raise LocalPilotExecutionError("PILOT_RECONCILIATION_METRIC_INVALID")
    return {key: metric[key] for key in keys}


def bound_metrics(
    finance_results: Mapping[str, Mapping[str, Any]],
    binding: object,
) -> list[dict[str, Any]]:
    if not isinstance(binding, tuple) or not binding:
        raise LocalPilotExecutionError("PILOT_RECONCILIATION_BINDING_INVALID")
    seen: set[tuple[str, str]] = set()
    output: list[dict[str, Any]] = []
    for component in binding:
        if (
            not isinstance(component, tuple)
            or len(component) != 2
            or not all(isinstance(item, str) and item for item in component)
        ):
            raise LocalPilotExecutionError("PILOT_RECONCILIATION_BINDING_INVALID")
        if component in seen:
            raise LocalPilotExecutionError("PILOT_RECONCILIATION_BINDING_DUPLICATE")
        seen.add(component)
        label, metric_id = component
        result = finance_results.get(label)
        results = result.get("results") if isinstance(result, Mapping) else None
        if not isinstance(results, Mapping) or metric_id not in results:
            raise LocalPilotExecutionError("PILOT_RECONCILIATION_BINDING_INVALID")
        output.append(metric_view(results[metric_id]))
    return output


def sum_metrics(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    first = metrics[0]
    signature = (first["value_type"], first["unit"], first["currency"])
    if any(
        metric["state"] != "VALID"
        or (metric["value_type"], metric["unit"], metric["currency"]) != signature
        for metric in metrics
    ):
        raise LocalPilotExecutionError("PILOT_RECONCILIATION_METRIC_NONVALID")
    try:
        total = sum((Decimal(str(item["value"])) for item in metrics), Decimal(0))
    except (InvalidOperation, ValueError) as exc:
        raise LocalPilotExecutionError("PILOT_RECONCILIATION_METRIC_INVALID") from exc
    value_type, unit, currency = signature
    if value_type == "INTEGER":
        if total != total.to_integral_value():
            raise LocalPilotExecutionError("PILOT_RECONCILIATION_METRIC_INVALID")
        value = str(int(total))
    else:
        value = format(total, "f")
    return {
        "state": "VALID",
        "value": value,
        "value_type": value_type,
        "unit": unit,
        "currency": currency,
    }


__all__ = ["bound_metrics", "metric_view", "sum_metrics"]
