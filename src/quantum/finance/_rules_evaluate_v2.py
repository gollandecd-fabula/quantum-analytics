from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from ._common import FinanceError, _MAX_EXPRESSION_NODES, _make_nonvalid, _value_to_dict
from ._expression_limits import validate_expression_policy_limits
from ._rounding import _decimal_context, validate_rounding_policy
from ._rule_method_evaluation import evaluate_selected_rule
from ._rules_precheck import prepare_rule_evaluation
from ._rules_trace_registry import rule_signature


def evaluate_resolved_rule(
    resolution: Mapping[str, Any],
    rules: Sequence[Mapping[str, Any]],
    variables: Mapping[str, Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    _, selected, early = prepare_rule_evaluation(resolution, rules, variables)
    if early is not None:
        return early
    if selected is None:
        return _value_to_dict(_make_nonvalid(
            str(resolution["state"]),
            value_type="DECIMAL",
            unit="DIMENSIONLESS",
            currency=None,
            reason_code=str(resolution["diagnostic_code"]),
            source_ids=(str(resolution["trace_id"]),),
        ))
    validated_policy = validate_rounding_policy(policy)
    if selected["method"] == "SAFE_EXPRESSION":
        validate_expression_policy_limits(selected["expression"], validated_policy)
    with _decimal_context(validated_policy, operation_budget=_MAX_EXPRESSION_NODES):
        result = evaluate_selected_rule(
            selected, variables, validated_policy, str(resolution["trace_id"])
        )
    if selected["method"] != "SAFE_EXPRESSION":
        return result
    actual = (result.get("value_type"), result.get("unit"), result.get("currency"))
    if actual != rule_signature(selected):
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
