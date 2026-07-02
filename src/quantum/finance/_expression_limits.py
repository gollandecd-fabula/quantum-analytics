from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._common import (
    FinanceError,
    _MAX_EXPRESSION_DEPTH,
    _MAX_EXPRESSION_NODES,
    _parse_integer,
)


def validate_expression_policy_limits(
    expression: object,
    policy: Mapping[str, Any],
) -> None:
    node_count = 0

    def walk(node: object, depth: int) -> None:
        nonlocal node_count
        node_count += 1
        if node_count > _MAX_EXPRESSION_NODES or depth > _MAX_EXPRESSION_DEPTH:
            raise FinanceError("EXPRESSION_LIMIT_EXCEEDED")
        if not isinstance(node, Mapping):
            raise FinanceError("EXPRESSION_SCHEMA_INVALID")
        kind = node.get("kind")
        if kind == "LITERAL":
            if node.get("value_type") == "INTEGER":
                _parse_integer(
                    node.get("value"),
                    code="EXPRESSION_TYPE_MISMATCH",
                    max_precision=policy["max_input_precision"],
                )
            return
        if kind == "VARIABLE":
            return
        if kind != "OPERATION":
            raise FinanceError("EXPRESSION_SCHEMA_INVALID")
        arguments = node.get("arguments")
        if not isinstance(arguments, list):
            raise FinanceError("EXPRESSION_SCHEMA_INVALID")
        for argument in arguments:
            walk(argument, depth + 1)

    walk(expression, 1)


__all__ = ["validate_expression_policy_limits"]
