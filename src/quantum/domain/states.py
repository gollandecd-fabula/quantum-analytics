from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping


class DataState(StrEnum):
    VALID = "VALID"
    EMPTY = "EMPTY"
    BLOCKED = "BLOCKED"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICT = "CONFLICT"
    INVALID = "INVALID"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class TypedValue:
    state: DataState
    value: Any
    value_type: str | None
    unit: str | None = None
    reason_code: str | None = None
    source_record_id: str | None = None
    observed_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.state is DataState.VALID:
            if self.value is None:
                raise ValueError("VALID typed value requires a non-null value.")
            if not self.value_type:
                raise ValueError("VALID typed value requires value_type.")
            if self.reason_code is not None:
                raise ValueError("VALID typed value must not contain reason_code.")
        else:
            if self.value is not None:
                raise ValueError(
                    f"{self.state} typed value must contain value=None; "
                    "missing states cannot be converted to zero."
                )
            if not self.reason_code:
                raise ValueError(f"{self.state} typed value requires reason_code.")

    @classmethod
    def valid(
        cls,
        value: Any,
        *,
        value_type: str,
        unit: str | None = None,
        source_record_id: str | None = None,
        observed_at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "TypedValue":
        return cls(
            state=DataState.VALID,
            value=value,
            value_type=value_type,
            unit=unit,
            reason_code=None,
            source_record_id=source_record_id,
            observed_at=observed_at,
            metadata=metadata or {},
        )

    @classmethod
    def missing(
        cls,
        state: DataState,
        *,
        reason_code: str,
        source_record_id: str | None = None,
        observed_at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "TypedValue":
        if state is DataState.VALID:
            raise ValueError("Use TypedValue.valid for VALID state.")
        return cls(
            state=state,
            value=None,
            value_type=None,
            unit=None,
            reason_code=reason_code,
            source_record_id=source_record_id,
            observed_at=observed_at,
            metadata=metadata or {},
        )
