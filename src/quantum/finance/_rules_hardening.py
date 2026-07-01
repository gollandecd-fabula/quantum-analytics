from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from threading import RLock
from typing import Any

from ._common import (
    FinanceError,
    RESOLVER_CONTRACT_VERSION,
    _HASH_RE,
    _is_nonempty_string,
    _make_nonvalid,
    _parse_rfc3339,
    _value_to_dict,
    canonical_hash,
)
from ._rules import (
    _validate_rule_document,
    evaluate_resolved_rule as _base_evaluate,
    resolve_rule as _base_resolve,
)

_APPROVED = {"SHADOW", "PILOT", "ACTIVE"}
_CACHE_LIMIT = 4096
_LOCK = RLock()
_TRACES: OrderedDict[str, tuple[dict[str, Any], str]] = OrderedDict()


def _snapshot(rules: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    if not isinstance(rules, Sequence) or isinstance(rules, (str, bytes)):
        raise FinanceError("RULE_DOCUMENT_INVALID")
    return tuple(sorted(
        (_validate_rule_document(rule) for rule in rules),
        key=lambda item: (item["rule_id"], item["version"], item["content_hash"]),
    ))


def _fingerprint(rules: Sequence[Mapping[str, Any]]) -> str:
    return canonical_hash({"rules": list(rules)})


def _register(resolution: Mapping[str, Any], rules: Sequence[Mapping[str, Any]]) -> None:
    trace_id = resolution.get("trace_id")
    if not isinstance(trace_id, str):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    with _LOCK:
        _TRACES[trace_id] = (deepcopy(dict(resolution)), _fingerprint(rules))
        _TRACES.move_to_end(trace_id)
        while len(_TRACES) > _CACHE_LIMIT:
            _TRACES.popitem(last=False)


def _trusted(resolution: Mapping[str, Any], rules: Sequence[Mapping[str, Any]]) -> bool:
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


def _validate_envelope(resolution: Mapping[str, Any]) -> None:
    required = {
        "resolver_contract_version", "context_hash", "state", "diagnostic_code",
        "candidates", "actor", "resolved_at", "trace_id",
    }
    if not isinstance(resolution, Mapping) or set(resolution) != required:
        raise FinanceError("RULE_RESOLUTION_INVALID")
    if resolution.get("resolver_contract_version") != RESOLVER_CONTRACT_VERSION:
        raise FinanceError("RULE_RESOLUTION_INVALID")
    if resolution.get("state") not in {"VALID", "BLOCKED", "CONFLICT", "UNAVAILABLE"}:
        raise FinanceError("RULE_RESOLUTION_INVALID")
    for field in ("context_hash", "trace_id"):
        value = resolution.get(field)
        if not isinstance(value, str) or _HASH_RE.fullmatch(value) is None:
            raise FinanceError("RULE_RESOLUTION_INVALID")
    if not _is_nonempty_string(resolution.get("actor")):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    _parse_rfc3339(resolution.get("resolved_at"), "RULE_RESOLUTION_INVALID")
    if canonical_hash(resolution, exclude=frozenset({"trace_id"})) != resolution["trace_id"]:
        raise FinanceError("RULE_RESOLUTION_TRACE_MISMATCH")
    state = resolution["state"]
    diagnostic = resolution.get("diagnostic_code")
    if (state == "VALID") != (diagnostic is None):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    candidates = resolution.get("candidates")
    if not isinstance(candidates, list):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    selected = 0
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise FinanceError("RULE_RESOLUTION_INVALID")
        if set(candidate) != {"rule", "eligible", "selected", "exclusion_reasons", "ordering_tuple"}:
            raise FinanceError("RULE_RESOLUTION_INVALID")
        if not isinstance(candidate.get("eligible"), bool) or not isinstance(candidate.get("selected"), bool):
            raise FinanceError("RULE_RESOLUTION_INVALID")
        ref = candidate.get("rule")
        if not isinstance(ref, Mapping) or set(ref) != {"rule_id", "version", "content_hash"}:
            raise FinanceError("RULE_RESOLUTION_INVALID")
        reasons = candidate.get("exclusion_reasons")
        if not isinstance(reasons, list) or any(not _is_nonempty_string(item) for item in reasons):
            raise FinanceError("RULE_RESOLUTION_INVALID")
        if candidate["selected"]:
            if not candidate["eligible"] or reasons or candidate.get("ordering_tuple") is None:
                raise FinanceError("RULE_RESOLUTION_INVALID")
            selected += 1
    if (state == "VALID" and selected != 1) or (state != "VALID" and selected != 0):
        raise FinanceError("RULE_RESOLUTION_INVALID")


def _selected_rule(
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


def _signature(rule: Mapping[str, Any]) -> tuple[str, str, str | None]:
    unit = str(rule["unit"])
    if unit.startswith("MONEY"):
        return "MONEY", unit, str(rule["currency"])
    if unit == "RATE":
        return "RATE", unit, None
    return "DECIMAL", unit, None


def resolve_rule(
    rules: Sequence[Mapping[str, Any]],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot = _snapshot(rules)
    resolution = _base_resolve(snapshot, context)
    _register(resolution, snapshot)
    return resolution


def evaluate_resolved_rule(
    resolution: Mapping[str, Any],
    rules: Sequence[Mapping[str, Any]],
    variables: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot = _snapshot(rules)
    _validate_envelope(resolution)
    if not _trusted(resolution, snapshot):
        raise FinanceError("RULE_RESOLUTION_REPLAY_MISMATCH")
    selected = _selected_rule(resolution, snapshot)
    if selected is not None and selected["status"] not in _APPROVED:
        raise FinanceError("RULE_NOT_APPROVED")
    if selected is not None:
        missing = sorted(set(selected["dependencies"]) - set(variables))
        if missing:
            value_type, unit, currency = _signature(selected)
            return _value_to_dict(_make_nonvalid(
                "UNAVAILABLE",
                value_type=value_type,
                unit=unit,
                currency=currency,
                reason_code=f"RULE_DEPENDENCY_UNAVAILABLE:{missing[0]}",
                source_ids=(str(resolution["trace_id"]), str(selected["content_hash"])),
            ))
    result = _base_evaluate(resolution, snapshot, variables, policy)
    if selected is not None and selected["method"] == "SAFE_EXPRESSION":
        actual = (result.get("value_type"), result.get("unit"), result.get("currency"))
        if actual != _signature(selected):
            raise FinanceError("RULE_EXPRESSION_SIGNATURE_MISMATCH")
        source_ids = result.get("source_ids")
        if not isinstance(source_ids, list):
            raise FinanceError("TYPED_VALUE_MALFORMED")
        enriched = deepcopy(dict(result))
        enriched["source_ids"] = sorted(set([
            *source_ids,
            str(resolution["trace_id"]),
            str(selected["content_hash"]),
        ]))
        return enriched
    return result


__all__ = ["evaluate_resolved_rule", "resolve_rule"]
