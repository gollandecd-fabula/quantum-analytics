from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._common import FinanceError, _clone_json
from ._runtime_core import (
    evaluate_expression,
    evaluate_resolved_rule,
    resolve_rule,
)
from ._runtime_core import calculate as _core_calculate

_REQUIRED_KEYS = frozenset(
    {
        "calculation_id",
        "organization_id",
        "mode",
        "scenario_id",
        "calculated_at",
        "profile_ref",
        "profile_status",
        "rounding_policy",
        "currency",
        "inputs",
        "cost_per_unit",
        "other_expense_components",
        "tax_rate",
        "tax_base_metric_id",
    }
)


def calculate(request: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and sanitize the request before entering the reviewed core."""
    if not isinstance(request, Mapping) or set(request) != _REQUIRED_KEYS:
        raise FinanceError("KERNEL_REQUEST_INVALID")
    try:
        sanitized = _clone_json(request)
    except FinanceError as exc:
        raise FinanceError("KERNEL_REQUEST_INVALID") from exc
    if not isinstance(sanitized, dict):
        raise FinanceError("KERNEL_REQUEST_INVALID")
    return _core_calculate(sanitized)


__all__ = [
    "calculate",
    "evaluate_expression",
    "evaluate_resolved_rule",
    "resolve_rule",
]
