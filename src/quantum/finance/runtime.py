from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._common import FinanceError, canonical_hash
from ._runtime_legacy import (
    evaluate_expression,
    evaluate_resolved_rule,
    resolve_rule,
)
from ._runtime_legacy import calculate as _legacy_calculate


def calculate(request: Mapping[str, Any]) -> dict[str, Any]:
    """Run the reviewed kernel with fail-closed public-input and evidence hardening."""
    if not isinstance(request, Mapping):
        raise FinanceError("KERNEL_REQUEST_INVALID")

    payload = _legacy_calculate(request)
    results = payload["results"]
    results["profit_per_sold_unit"]["expense_boundary"] = list(
        results["net_profit_amount"]["expense_boundary"]
    )
    payload["limitations"] = [
        "B2_RECONCILIATION_REQUIRED"
        if value == "B2_RECONCILIATION_NOT_IMPLEMENTED"
        else value
        for value in payload["limitations"]
    ]
    payload["result_hash"] = canonical_hash(
        payload, exclude=frozenset({"result_hash"})
    )
    return payload
