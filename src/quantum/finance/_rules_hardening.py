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
    canonical_hash,
)
from ._rules import (
    _validate_rule_document,
    evaluate_resolved_rule as _evaluate_resolved_rule,
    resolve_rule as _resolve_rule,
)

_APPROVED_RULE_STATUSES = {"SHADOW", "PILOT", "ACTIVE"}
_RESOLUTION_FIELDS = {
    "resolver_contract_version",
    "context_hash",
    "state",
    "diagnostic_code",
    "candidates",
    "actor",
    "resolved_at",
    "trace_id",
}
_TRUSTED_TRACE_CACHE_LIMIT = 4096
_TRUSTED_TRACE_LOCK = RLock()
_TRUSTED_TRACES: OrderedDict[
    str, tuple[dict[str, Any], str]
] = OrderedDict()


def _snapshot_rules(
    rules: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    if not isinstance(rules, Sequence) or isinstance(rules, (str, bytes)):
        raise FinanceError("RULE_DOCUMENT_INVALID")
    return tuple(
        sorted(
            (_validate_rule_document(rule) for rule in rules),
            key=lambda item: (item["rule_id"], item["version"], item["content_hash"]),
        )
    )


def _snapshot_fingerprint(rules: Sequence[Mapping[str, Any]]) -> str:
    return canonical_hash({"rules": list(rules)})


def _register_trusted_trace(
    resolution: Mapping[str, Any],
    rules_snapshot: Sequence[Mapping[str, Any]],
) -> None:
    trace_id = resolution.get("trace_id")
    if not isinstance(trace_id, str):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    entry = (
        deepcopy(dict(resolution)),
        _snapshot_fingerprint(rules_snapshot),
    )
    with _TRUSTED_TRACE_LOCK:
        _TRUSTED_TRACES[trace_id] = entry
        _TRUSTED_TRACES.move_to_end(trace_id)
        while len(_TRUSTED_TRACES) > _TRUSTED_TRACE_CACHE_LIMIT:
            _TRUSTED_TRACES.popitem(last=False)


def _matches_trusted_trace(
    resolution: Mapping[str, Any],
    rules_snapshot: Sequence[Mapping[str, Any]],
) -> bool:
    trace_id = resolution.get("trace_id")
    if not isinstance(trace_id, str):
        return False
    with _TRUSTED_TRACE_LOCK:
        registered = _TRUSTED_TRACES.get(trace_id)
        if registered is None:
            return False
        expected_resolution, expected_rules_fingerprint = registered
        expected_resolution = deepcopy(expected_resolution)
        _TRUSTED_TRACES.move_to_end(trace_id)
    return (
        dict(resolution) == expected_resolution
        and _snapshot_fingerprint(rules_snapshot) == expected_rules_fingerprint
    )


def _validate_resolution_envelope(resolution: Mapping[str, Any]) -> None:
    if (
        not isinstance(resolution, Mapping)
        or set(resolution) != _RESOLUTION_FIELDS
        or resolution.get("resolver_contract_version")
        != RESOLVER_CONTRACT_VERSION
        or resolution.get("state")
        not in {"VALID", "BLOCKED", "CONFLICT", "UNAVAILABLE"}
    ):
        raise FinanceError("RULE_RESOLUTION_INVALID")

    trace_id = resolution.get("trace_id")
    if (
        not isinstance(trace_id, str)
        or _HASH_RE.fullmatch(trace_id) is None
        or canonical_hash(resolution, exclude=frozenset({"trace_id"}))
        != trace_id
    ):
        raise FinanceError("RULE_RESOLUTION_TRACE_MISMATCH")

    state = resolution["state"]
    diagnostic = resolution.get("diagnostic_code")
    if (state == "VALID") != (diagnostic is None):
        raise FinanceError("RULE_RESOLUTION_INVALID")

    candidates = resolution.get("candidates")
    if not isinstance(candidates, list):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    selected = [
        candidate
        for candidate in candidates
        if isinstance(candidate, Mapping)
        and candidate.get("eligible") is True
        and candidate.get("selected") is True
    ]
    if state != "VALID":
        if selected:
            raise FinanceError("RULE_RESOLUTION_INVALID")
        return
    if len(selected) != 1:
        raise FinanceError("RULE_RESOLUTION_INVALID")
    ref = selected[0].get("rule")
    if (
        not isinstance(ref, Mapping)
        or set(ref) != {"rule_id", "version", "content_hash"}
    ):
        raise FinanceError("RULE_RESOLUTION_INVALID")


def resolve_rule(
    rules: Sequence[Mapping[str, Any]],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    rules_snapshot = _snapshot_rules(rules)
    resolution = _resolve_rule(rules_snapshot, context)
    _register_trusted_trace(resolution, rules_snapshot)
    return resolution


def _selected_rule(
    resolution: Mapping[str, Any],
    rules_snapshot: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if resolution.get("state") != "VALID":
        return None
    selected = [
        candidate
        for candidate in resolution["candidates"]
        if isinstance(candidate, Mapping)
        and candidate.get("eligible") is True
        and candidate.get("selected") is True
    ]
    ref = selected[0]["rule"]
    lookup = {
        (rule["rule_id"], rule["version"], rule["content_hash"]): rule
        for rule in rules_snapshot
    }
    key = (ref.get("rule_id"), ref.get("version"), ref.get("content_hash"))
    return lookup.get(key)


def _expected_signature(rule: Mapping[str, Any]) -> tuple[str, str, str | None]:
    unit = str(rule["unit"])
    if unit.startswith("MONEY"):
        return "MONEY", unit, rule["currency"]
    if unit == "RATE":
        return "RATE", unit, None
    return "DECIMAL", unit, None


def _is_pre_evaluation_missing_dependency(result: Mapping[str, Any]) -> bool:
    reason_code = result.get("reason_code")
    return (
        result.get("state") == "UNAVAILABLE"
        and isinstance(reason_code, str)
        and reason_code.startswith("RULE_DEPENDENCY_UNAVAILABLE:")
    )


def evaluate_resolved_rule(
    resolution: Mapping[str, Any],
    rules: Sequence[Mapping[str, Any]],
    variables: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    rules_snapshot = _snapshot_rules(rules)
    _validate_resolution_envelope(resolution)

    selected_rule = _selected_rule(resolution, rules_snapshot)
    if (
        selected_rule is not None
        and selected_rule["status"] not in _APPROVED_RULE_STATUSES
    ):
        raise FinanceError("RULE_NOT_APPROVED")

    if not _matches_trusted_trace(resolution, rules_snapshot):
        raise FinanceError("RULE_RESOLUTION_REPLAY_MISMATCH")

    result = _evaluate_resolved_rule(
        resolution,
        rules_snapshot,
        variables,
        policy,
    )

    if (
        selected_rule is not None
        and selected_rule["method"] == "SAFE_EXPRESSION"
        and not _is_pre_evaluation_missing_dependency(result)
    ):
        actual_signature = (
            result.get("value_type"),
            result.get("unit"),
            result.get("currency"),
        )
        if actual_signature != _expected_signature(selected_rule):
            raise FinanceError("RULE_EXPRESSION_SIGNATURE_MISMATCH")

    return result


__all__ = ["evaluate_resolved_rule", "resolve_rule"]
