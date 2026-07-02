from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ._common import FinanceError
from ._expression_eager import evaluate_expression as _evaluate_eager
from ._expression_validation import validate_expression_ast

_SYNTHETIC_PREFIX = "if_state."


def evaluate_expression(
    expression: object,
    variables: Mapping[str, Mapping[str, Any]],
    dependencies: Sequence[str],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate SAFE_EXPRESSION with short-circuit IF semantics.

    The complete original AST is validated before execution. Runtime evaluation then
    removes every unselected IF branch, so failures and unavailable dependencies in a
    branch that cannot execute do not contaminate the selected result.
    """
    validate_expression_ast(expression, dependencies)
    if not isinstance(variables, Mapping):
        raise FinanceError("EXPRESSION_VARIABLES_INVALID")

    working_variables: dict[str, Mapping[str, Any]] = dict(variables)
    working_dependencies = list(dependencies)
    condition_sources: set[str] = set()
    synthetic_names: set[str] = set()
    synthetic_counter = 0

    def register_nonvalid(
        value: Mapping[str, Any],
        *,
        value_type: object,
        unit: object,
        currency: object,
    ) -> dict[str, Any]:
        nonlocal synthetic_counter
        name = f"{_SYNTHETIC_PREFIX}{synthetic_counter}"
        synthetic_counter += 1
        synthetic_names.add(name)
        working_dependencies.append(name)
        working_variables[name] = dict(value)
        return {
            "kind": "VARIABLE",
            "name": name,
            "value_type": value_type,
            "unit": unit,
            "currency": currency,
        }

    def resolve(node: object) -> dict[str, Any]:
        if not isinstance(node, Mapping):
            raise FinanceError("EXPRESSION_SCHEMA_INVALID")
        copied = dict(node)
        if copied.get("kind") != "OPERATION":
            return copied

        arguments = copied.get("arguments")
        if not isinstance(arguments, list):
            raise FinanceError("EXPRESSION_SCHEMA_INVALID")
        if copied.get("operator") != "IF":
            copied["arguments"] = [resolve(argument) for argument in arguments]
            return copied

        condition_ast = resolve(arguments[0])
        condition = _evaluate_eager(
            condition_ast,
            working_variables,
            working_dependencies,
            policy,
        )
        condition_sources.update(
            source
            for source in condition.get("source_ids", [])
            if isinstance(source, str) and not source.startswith(_SYNTHETIC_PREFIX)
        )

        state = condition.get("state")
        if state != "VALID":
            reason_code = condition.get("reason_code")
            if not isinstance(state, str) or not isinstance(reason_code, str):
                raise FinanceError("TYPED_VALUE_MALFORMED")
            propagated = {
                "state": state,
                "value": None,
                "value_type": copied.get("value_type"),
                "unit": copied.get("unit"),
                "currency": copied.get("currency"),
                "reason_code": f"DEPENDENCY_{state}:{reason_code}",
                "source_ids": [
                    source
                    for source in condition.get("source_ids", [])
                    if isinstance(source, str)
                    and not source.startswith(_SYNTHETIC_PREFIX)
                ],
            }
            return register_nonvalid(
                propagated,
                value_type=copied.get("value_type"),
                unit=copied.get("unit"),
                currency=copied.get("currency"),
            )

        if condition.get("value_type") != "BOOLEAN" or not isinstance(
            condition.get("value"), bool
        ):
            raise FinanceError("EXPRESSION_TYPE_MISMATCH")
        selected_index = 1 if condition["value"] else 2
        return resolve(arguments[selected_index])

    transformed = resolve(expression)
    result = dict(
        _evaluate_eager(
            transformed,
            working_variables,
            working_dependencies,
            policy,
        )
    )
    result_sources = {
        source
        for source in result.get("source_ids", [])
        if isinstance(source, str) and source not in synthetic_names
    }
    result["source_ids"] = sorted(result_sources | condition_sources)
    return result


__all__ = ["evaluate_expression"]
