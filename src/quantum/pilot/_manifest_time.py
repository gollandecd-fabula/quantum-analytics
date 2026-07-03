from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ._manifest_common import datetime_value, exact_keys, mapping
from ._scope import LocalPilotExecutionError


@dataclass(frozen=True, slots=True)
class PilotTimes:
    declared_at: datetime
    observed_at: datetime
    admitted_at: datetime
    reconciled_at: datetime


def build_times(value: object) -> PilotTimes:
    item = mapping(value, "PILOT_TIMESTAMPS_INVALID")
    exact_keys(
        item,
        {"declared_at", "observed_at", "admitted_at", "reconciled_at"},
        "PILOT_TIMESTAMPS_INVALID",
    )
    times = PilotTimes(
        declared_at=datetime_value(item["declared_at"], "PILOT_TIMESTAMPS_INVALID"),
        observed_at=datetime_value(item["observed_at"], "PILOT_TIMESTAMPS_INVALID"),
        admitted_at=datetime_value(item["admitted_at"], "PILOT_TIMESTAMPS_INVALID"),
        reconciled_at=datetime_value(item["reconciled_at"], "PILOT_TIMESTAMPS_INVALID"),
    )
    if not (
        times.declared_at
        <= times.observed_at
        <= times.admitted_at
        <= times.reconciled_at
    ):
        raise LocalPilotExecutionError("PILOT_TIMESTAMPS_INVALID")
    return times


__all__ = ["PilotTimes", "build_times"]
