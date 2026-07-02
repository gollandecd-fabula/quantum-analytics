from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from threading import RLock
from typing import Any

from ._common import FinanceError, canonical_hash
from ._rules import _validate_rule_document

_CACHE_LIMIT = 4096
_LOCK = RLock()
_TRACES: OrderedDict[str, tuple[dict[str, Any], str]] = OrderedDict()


def snapshot_rules(rules: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    if not isinstance(rules, Sequence) or isinstance(rules, (str, bytes)):
        raise FinanceError("RULE_DOCUMENT_INVALID")
    return tuple(sorted(
        (_validate_rule_document(rule) for rule in rules),
        key=lambda item: (item["rule_id"], item["version"], item["content_hash"]),
    ))


def _fingerprint(rules: Sequence[Mapping[str, Any]]) -> str:
    return canonical_hash({"rules": list(rules)})


def register_resolution(
    resolution: Mapping[str, Any],
    rules: Sequence[Mapping[str, Any]],
) -> None:
    trace_id = resolution.get("trace_id")
    if not isinstance(trace_id, str):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    with _LOCK:
        _TRACES[trace_id] = (deepcopy(dict(resolution)), _fingerprint(rules))
        _TRACES.move_to_end(trace_id)
        while len(_TRACES) > _CACHE_LIMIT:
            _TRACES.popitem(last=False)


def resolution_is_trusted(
    resolution: Mapping[str, Any],
    rules: Sequence[Mapping[str, Any]],
) -> bool:
    trace_id = resolution.get("trace_id")
    if not isinstance(trace_id, str):
        return False
    with _LOCK:
        stored = _TRACES.get(trace_id)
        if stored is None:
            return False
        expected_resolution, expected_rules = stored
        _TRACES.move_to_end(trace_id)
    return dict(resolution) == expected_resolution and _fingerprint(rules) == expected_rules


def selected_rule(
    resolution: Mapping[str, Any],
    rules: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if resolution.get("state") != "VALID":
        return None
    candidate = next(
        item for item in resolution["candidates"]
        if item["eligible"] is True and item["selected"] is True
    )
    ref = candidate["rule"]
    lookup = {
        (rule["rule_id"], rule["version"], rule["content_hash"]): rule
        for rule in rules
    }
    return lookup.get((ref["rule_id"], ref["version"], ref["content_hash"]))


def rule_signature(rule: Mapping[str, Any]) -> tuple[str, str, str | None]:
    unit = str(rule["unit"])
    if unit.startswith("MONEY"):
        return "MONEY", unit, str(rule["currency"])
    if unit == "RATE":
        return "RATE", unit, None
    return "DECIMAL", unit, None
