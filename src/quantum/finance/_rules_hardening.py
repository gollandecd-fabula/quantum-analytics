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
    _is_positive_int,
    _make_nonvalid,
    _parse_rfc3339,
    _value_to_dict,
    canonical_hash,
)
from ._rules import (
    _validate_rule_document,
    evaluate_resolved_rule as _evaluate_resolved_rule,
    resolve_rule as _resolve_rule,
)

_APPROVED_RULE_STATUSES = {"SHADOW", "PILOT", "ACTIVE"}
_DIAGNOSTIC_CODES = {
    "RULE_REQUIRED_MISSING",
    "RULE_RESOLUTION_TIE",
    "RULE_EXCLUSIVITY_OVERLAP",
    "RULE_DEPENDENCY_UNKNOWN",
    "RULE_DEPENDENCY_CYCLE",
    "RULE_UNIT_MISMATCH",
    "RULE_CURRENCY_MISMATCH",
    "RULE_NOT_APPROVED",
}
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
_CANDIDATE_FIELDS = {
    "rule",
    "eligible",
    "selected",
    "exclusion_reasons",
    "ordering_tuple",
}
_RULE_REF_FIELDS = {"rule_id", "version", "content_hash"}
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


def _validate_rule_ref(ref: object) -> None:
    if (
        not isinstance(ref, Mapping)
        or set(ref) != _RULE_REF_FIELDS
        or not _is_nonempty_string(ref.get("rule_id"))
        or not _is_positive_int(ref.get("version"))
        or not isinstance(ref.get("content_hash"), str)
        or _HASH_RE.fullmatch(ref["content_hash"]) is None
    ):
        raise FinanceError("RULE_RESOLUTION_INVALID")


def _validate_candidate_shape(candidate: object) -> Mapping[str, Any]:
    if not isinstance(candidate, Mapping) or set(candidate) != _CANDIDATE_FIELDS:
        raise FinanceError("RULE_RESOLUTION_INVALID")
    _validate_rule_ref(candidate.get("rule"))

    eligible = candidate.get("eligible")
    selected = candidate.get("selected")
    if not isinstance(eligible, bool) or not isinstance(selected, bool):
        raise FinanceError("RULE_RESOLUTION_INVALID")

    exclusion_reasons = candidate.get("exclusion_reasons")
    if (
        not isinstance(exclusion_reasons, list)
        or any(not _is_nonempty_string(reason) for reason in exclusion_reasons)
        or len(exclusion_reasons) != len(set(exclusion_reasons))
    ):
        raise FinanceError("RULE_RESOLUTION_INVALID")

    ordering = candidate.get("ordering_tuple")
    if ordering is None:
        return candidate
    if not isinstance(ordering, list) or len(ordering) != 4:
        raise FinanceError("RULE_RESOLUTION_INVALID")
    specificity, priority, valid_from, version = ordering
    if (
        not isinstance(specificity, list)
        or len(specificity) != 6
        or any(
            not isinstance(item, int)
            or isinstance(item, bool)
            or item not in {0, 1}
            for item in specificity
        )
        or not isinstance(priority, int)
        or isinstance(priority, bool)
        or not _is_positive_int(version)
    ):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    _parse_rfc3339(valid_from, "RULE_RESOLUTION_INVALID")
    return candidate


def _validate_candidate_semantics(candidate: Mapping[str, Any]) -> bool:
    eligible = candidate["eligible"]
    selected = candidate["selected"]
    exclusion_reasons = candidate["exclusion_reasons"]
    ordering = candidate["ordering_tuple"]
    if not eligible:
        if selected or ordering is not None or not exclusion_reasons:
            raise FinanceError("RULE_RESOLUTION_INVALID")
        return False
    if exclusion_reasons or ordering is None:
        raise FinanceError("RULE_RESOLUTION_INVALID")
    return bool(selected)


def _validate_resolution_envelope(resolution: Mapping[str, Any]) -> None:
    if (
        not isinstance(resolution, Mapping)
        or set(resolution) != _RESOLUTION_FIELDS
        or resolution.get("resolver_contract_version")
        != RESOLVER_CONTRACT_VERSION
        or resolution.get("state")
        not in {"VALID", "BLOCKED", "CONFLICT", "UNAVAILABLE"}
        or not isinstance(resolution.get("context_hash"), str)
        or _HASH_RE.fullmatch(resolution["context_hash"]) is None
        or not _is_nonempty_string(resolution.get("actor"))
    ):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    _parse_rfc3339(resolution.get("resolved_at"), "RULE_RESOLUTION_INVALID")

    diagnostic = resolution.get("diagnostic_code")
    if diagnostic is not None and diagnostic not in _DIAGNOSTIC_CODES:
        raise FinanceError("RULE_RESOLUTION_INVALID")

    candidates = resolution.get("candidates")
    if not isinstance(candidates, list):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    validated_candidates = [
        _validate_candidate_shape(candidate) for candidate in candidates
    ]

    trace_id = resolution.get("trace_id")
    if (
        not isinstance(trace_id, str)
        or _HASH_RE.fullmatch(trace_id) is None
        or canonical_hash(resolution, exclude=frozenset({"trace_id"}))
        != trace_id
    ):
        raise FinanceError("RULE_RESOLUTION_TRACE_MISMATCH")

    state = resolution["state"]
    if (state == "VALID") != (diagnostic is None):
        raise FinanceError("RULE_RESOLUTION_INVALID")
    selected_count = sum(
        1 for candidate in validated_candidates
        if _validate_candidate_semantics(candidate)
    )
    if (state == "VALID" and selected_count != 1) or (
        state != "VALID" and selected_count != 0
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
        if candidate["eligible"] is True and candidate["selected"] is True
    ]
    ref = selected[0]["rule"]
    lookup = {
        (rule["rule_id"], rule["version"], rule["content_hash"]): rule
        for rule in rules_snapshot
    }
    key = (ref["rule_id"], ref["version"], ref["content_hash"])
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


def _attach_expression_provenance(
    result: Mapping[str, Any],
    resolution: Mapping[str, Any],
    selected_rule: Mapping[str, Any],
) -> dict[str, Any]:
    source_ids = result.get("source_ids")
    if (
        not isinstance(source_ids, list)
        or any(not _is_nonempty_string(source_id) for source_id in source_ids)
    ):
        raise FinanceError("TYPED_VALUE_MALFORMED")
    enriched = deepcopy(dict(result))
    enriched["source_ids"] = sorted(
        set(
            [
                *source_ids,
                str(resolution["trace_id"]),
                str(selected_rule["content_hash"]),
            ]
        )
    )
    return enriched


def _missing_dependency_result(
    resolution: Mapping[str, Any],
    selected_rule: Mapping[str, Any],
    variables: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any] | None:
    missing = sorted(set(selected_rule["dependencies"]) - set(variables))
    if not missing:
        return None
    value_type, unit, currency = _expected_signature(selected_rule)
    return _value_to_dict(
        _make_nonvalid(
            "UNAVAILABLE",
            value_type=value_type,
            unit=unit,
            currency=currency,
            reason_code=f"RULE_DEPENDENCY_UNAVAILABLE:{missing[0]}",
            source_ids=(
                str(resolution["trace_id"]),
                str(selected_rule["content_hash"]),
            ),
        )
    )


def evaluate_resolved_rule(
    resolution: Mapping[str, Any],
    rules: Sequence[Mapping[str, Any]],
    variables: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    rules_snapshot = _snapshot_rules(rules)
    _validate_resolution_envelope(resolution)

    if not _matches_trusted_trace(resolution, rules_snapshot):
        raise FinanceError("RULE_RESOLUTION_REPLAY_MISMATCH")

    selected_rule = _selected_rule(resolution, rules_snapshot)
    if (
        selected_rule is not None
        and selected_rule["status"] not in _APPROVED_RULE_STATUSES
    ):
        raise FinanceError("RULE_NOT_APPROVED")

    if selected_rule is not None:
        missing_result = _missing_dependency_result(
            resolution,
            selected_rule,
            variables,
        )
        if missing_result is not None:
            return missing_result

    result = _evaluate_resolved_rule(
        resolution,
        rules_snapshot,
        variables,
        policy,
    )

    if selected_rule is not None and selected_rule["method"] == "SAFE_EXPRESSION":
        if not _is_pre_evaluation_missing_dependency(result):
            actual_signature = (
                result.get("value_type"),
                result.get("unit"),
                result.get("currency"),
            )
            if actual_signature != _expected_signature(selected_rule):
                raise FinanceError("RULE_EXPRESSION_SIGNATURE_MISMATCH")
        result = _attach_expression_provenance(
            result,
            resolution,
            selected_rule,
        )

    return result


__all__ = ["evaluate_resolved_rule", "resolve_rule"]
