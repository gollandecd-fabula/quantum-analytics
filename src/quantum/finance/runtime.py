from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._common import FinanceError, canonical_hash
from ._rounding import validate_rounding_policy
from ._runtime_legacy import (
    evaluate_expression,
    evaluate_resolved_rule,
    resolve_rule,
)
from ._runtime_legacy import calculate as _runtime_calculate


def calculate(request: Mapping[str, Any]) -> dict[str, Any]:
    """Run the financial kernel through the fail-closed public boundary."""
    if not isinstance(request, Mapping):
        raise FinanceError("KERNEL_REQUEST_INVALID")
    return _runtime_calculate(request)
