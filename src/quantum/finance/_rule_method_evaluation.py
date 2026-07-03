from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._common import _make_valid, _value_from_dict, _value_to_dict
from ._expression import evaluate_expression
from ._rounding import _input_decimal, _propagate, _quantize


def evaluate_selected_rule(
    rule: Mapping[str, Any],
    variables: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
    trace_id: str,
) -> dict[str, Any]:
    dependencies = rule["dependencies"]
    if rule["method"] == "SAFE_EXPRESSION":
        return evaluate_expression(
            rule["expression"],
            {name: variables[name] for name in dependencies},
            dependencies,
            policy,
        )
    if rule["method"] == "FIXED_VALUE":
        value = _input_decimal(rule["value"], policy, code="RULE_VALUE_INVALID")
        result_type = "MONEY" if rule["unit"].startswith("MONEY") else "DECIMAL"
        currency = rule["currency"] if result_type == "MONEY" else None
        rounded, scale = _quantize(value, policy, "RULE_COMPONENT_RESULT", result_type)
        return _value_to_dict(_make_valid(
            rounded,
            value_type=result_type,
            unit=rule["unit"],
            currency=currency,
            source_ids=(trace_id, rule["content_hash"]),
        ), scale=scale)
    typed = {
        name: _value_from_dict(variables[name], source_id=name)
        for name in dependencies
    }
    propagated = _propagate(
        [typed[name] for name in dependencies],
        value_type="RATE",
        unit="RATE",
        currency=None,
    )
    if propagated is not None:
        return _value_to_dict(propagated)
    rate = _input_decimal(rule["rate"], policy, code="RULE_RATE_INVALID")
    rounded, scale = _quantize(rate, policy, "RULE_COMPONENT_RESULT", "RATE")
    return _value_to_dict(_make_valid(
        rounded,
        value_type="RATE",
        unit="RATE",
        currency=None,
        source_ids=(trace_id, rule["content_hash"]),
    ), scale=scale)
