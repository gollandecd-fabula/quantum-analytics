from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from quantum.finance import calculate

from ._scope import LocalPilotExecutionError, LocalPilotScope, validate_finance_request


def execute_finance_request(
    *,
    label: str,
    request: object,
    scope: LocalPilotScope,
    admitted_at: datetime,
    reconciled_at: datetime,
) -> Mapping[str, Any]:
    validated = validate_finance_request(
        label,
        request,
        scope,
        admitted_at=admitted_at,
        reconciled_at=reconciled_at,
    )
    result = calculate(validated)
    if result.get("publication_state") != "PREVIEW_ONLY":
        raise LocalPilotExecutionError("PILOT_PUBLICATION_STATE_INVALID")
    return result


__all__ = ["execute_finance_request"]
