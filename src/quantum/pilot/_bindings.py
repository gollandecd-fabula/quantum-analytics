from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._scope import LocalPilotExecutionError

MetricBindings = Mapping[str, tuple[tuple[str, str], ...]]


def finance_result_snapshot(**kwargs: Any) -> dict[str, Any]:
    raise LocalPilotExecutionError("PILOT_BINDINGS_NOT_IMPLEMENTED")


def validate_source_identity(source_snapshot: object, admitted: object) -> Mapping[str, Any]:
    if not isinstance(source_snapshot, Mapping):
        raise LocalPilotExecutionError("PILOT_SOURCE_SNAPSHOT_INVALID")
    return source_snapshot


__all__ = ["MetricBindings", "finance_result_snapshot", "validate_source_identity"]
