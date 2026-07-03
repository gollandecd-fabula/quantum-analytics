from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ._common import FinanceError, _make_nonvalid, _value_to_dict
from ._rules_resolution_validation import validate_resolution_envelope
from ._rules_trace_registry import (
    resolution_is_trusted,
    rule_signature,
    selected_rule,
    snapshot_rules,
)

_APPROVED = {"SHADOW", "PILOT", "ACTIVE"}


def prepare_rule_evaluation(
    resolution: Mapping[str, Any],
    rules: Sequence[Mapping[str, Any]],
    variables: Mapping[str, Mapping[str, Any]],
) -> tuple[tuple[dict[str, Any], ...], dict[str, Any] | None, dict[str, Any] | None]:
    snapshot = snapshot_rules(rules)
    validate_resolution_envelope(resolution)
    if not resolution_is_trusted(resolution, snapshot):
        raise FinanceError("RULE_RESOLUTION_REPLAY_MISMATCH")
    selected = selected_rule(resolution, snapshot)
    if selected is not None and selected["status"] not in _APPROVED:
        raise FinanceError("RULE_NOT_APPROVED")
    if selected is None:
        return snapshot, None, None
    missing = sorted(set(selected["dependencies"]) - set(variables))
    if not missing:
        return snapshot, selected, None
    value_type, unit, currency = rule_signature(selected)
    unavailable = _value_to_dict(_make_nonvalid(
        "UNAVAILABLE",
        value_type=value_type,
        unit=unit,
        currency=currency,
        reason_code=f"RULE_DEPENDENCY_UNAVAILABLE:{missing[0]}",
        source_ids=(str(resolution["trace_id"]), str(selected["content_hash"])),
    ))
    return snapshot, selected, unavailable
