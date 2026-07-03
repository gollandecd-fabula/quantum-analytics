from __future__ import annotations

from ._scope import LocalPilotExecutionError


def calculate_finance_results(**kwargs):
    raise LocalPilotExecutionError("PILOT_FINANCE_FLOW_NOT_IMPLEMENTED")


__all__ = ["calculate_finance_results"]
