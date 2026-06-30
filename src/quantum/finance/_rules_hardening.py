from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ._common import FinanceError
from ._rules import (
    _validate_rule_document,
    evaluate_resolved_rule as _evaluate_resolved_rule,
    resolve_rule,
)

_APPROVED_RULE_STATUSES = {"SHADOW", "PILOT", "ACTIVE"}


def _selected_rule(
    resolution: Mapping[str, Any],
    rules: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(resolution, Mapping) or resolution.get("state") != "VALID":
        return None
    candidates = resolution.get("candidates")
    if not isinstance(candidates, list):
        return None
    selected = [
        candidate
        for candidate in candidates
        if isinstance(candidate, Mapping)
        and candidate.get("eligible") is True
        and candidate.get("selected") is True
    ]
    if len(selected) != 1:
        return None
    ref = selected[0].get("rule")
    if not isinstance(ref, Mapping):
        return None
    normalized_rules = [_validate_rule_document(rule) for rule in rules]
    lookup = {
        (rule["rule_id"], rule["version"], rule["content_hash"]): rule
        for rule in normalized_rules
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


def evaluate_resolved_rule(
    resolution: Mapping[str, Any],
    rules: Sequence[Mapping[str, Any]],
    variables: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    selected_rule = _selected_rule(resolution, rules)
    if (
        selected_rule is not None
        and selected_rule["status"] not in _APPROVED_RULE_STATUSES
    ):
        raise FinanceError("RULE_NOT_APPROVED")

    result = _evaluate_resolved_rule(resolution, rules, variables, policy)

    if selected_rule is not None and selected_rule["method"] == "SAFE_EXPRESSION":
        actual_signature = (
            result.get("value_type"),
            result.get("unit"),
            result.get("currency"),
        )
        if actual_signature != _expected_signature(selected_rule):
            raise FinanceError("RULE_EXPRESSION_SIGNATURE_MISMATCH")

    return result


__all__ = ["evaluate_resolved_rule", "resolve_rule"]
