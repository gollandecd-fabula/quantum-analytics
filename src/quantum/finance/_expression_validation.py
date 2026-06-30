from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from ._common import (
    FinanceError,
    _INTEGER_RE,
    _MAX_EXPRESSION_ARGUMENTS,
    _MAX_EXPRESSION_DEPENDENCIES,
    _MAX_EXPRESSION_DEPTH,
    _MAX_EXPRESSION_NODES,
    _NUMERIC_TYPES,
    _Value,
    _is_nonempty_string,
    _make_valid,
    _parse_decimal,
    _validate_signature,
)
from ._expression import _validate_operation_signature


def _dummy_value(
    value_type: str,
    unit: str,
    currency: str | None,
) -> _Value:
    if value_type == "BOOLEAN":
        value: Decimal | int | bool = False
    elif value_type == "INTEGER":
        value = 0
    else:
        value = Decimal("0")
    return _make_valid(
        value,
        value_type=value_type,
        unit=unit,
        currency=currency,
    )


def validate_expression_ast(
    expression: object,
    dependencies: Sequence[str],
) -> None:
    if (
        not isinstance(dependencies, Sequence)
        or isinstance(dependencies, (str, bytes))
        or len(dependencies) > _MAX_EXPRESSION_DEPENDENCIES
        or len(dependencies) != len(set(dependencies))
        or any(not _is_nonempty_string(item) for item in dependencies)
    ):
        raise FinanceError("EXPRESSION_DEPENDENCY_UNDECLARED")
    dependency_set = set(dependencies)
    node_counter = 0

    def walk(node: object, depth: int) -> _Value:
        nonlocal node_counter
        node_counter += 1
        if node_counter > _MAX_EXPRESSION_NODES or depth > _MAX_EXPRESSION_DEPTH:
            raise FinanceError("EXPRESSION_LIMIT_EXCEEDED")
        if not isinstance(node, Mapping):
            raise FinanceError("EXPRESSION_SCHEMA_INVALID")

        kind = node.get("kind")
        if kind == "LITERAL":
            if set(node) != {"kind", "value", "value_type", "currency", "unit"}:
                raise FinanceError("EXPRESSION_SCHEMA_INVALID")
            value_type, unit, currency = _validate_signature(
                node.get("value_type"), node.get("unit"), node.get("currency")
            )
            raw = node.get("value")
            if value_type == "BOOLEAN":
                if not isinstance(raw, bool):
                    raise FinanceError("EXPRESSION_TYPE_MISMATCH")
            elif value_type == "INTEGER":
                if not isinstance(raw, str) or _INTEGER_RE.fullmatch(raw) is None:
                    raise FinanceError("EXPRESSION_TYPE_MISMATCH")
            else:
                _parse_decimal(raw, code="EXPRESSION_NON_FINITE_LITERAL")
            return _dummy_value(value_type, unit, currency)

        if kind == "VARIABLE":
            if set(node) != {"kind", "name", "value_type", "currency", "unit"}:
                raise FinanceError("EXPRESSION_SCHEMA_INVALID")
            name = node.get("name")
            if not _is_nonempty_string(name) or name not in dependency_set:
                raise FinanceError("EXPRESSION_DEPENDENCY_UNDECLARED")
            value_type, unit, currency = _validate_signature(
                node.get("value_type"), node.get("unit"), node.get("currency")
            )
            return _dummy_value(value_type, unit, currency)

        if kind != "OPERATION":
            raise FinanceError("EXPRESSION_SCHEMA_INVALID")
        required = {"kind", "operator", "value_type", "currency", "unit", "arguments"}
        if set(node) != required:
            raise FinanceError("EXPRESSION_SCHEMA_INVALID")
        operator = node.get("operator")
        arguments = node.get("arguments")
        if not isinstance(arguments, list) or len(arguments) > _MAX_EXPRESSION_ARGUMENTS:
            raise FinanceError("EXPRESSION_LIMIT_EXCEEDED")
        arity = len(arguments)
        arity_rules = {
            "ADD": arity >= 2,
            "SUBTRACT": arity == 2,
            "MULTIPLY": arity == 2,
            "DIVIDE": arity == 2,
            "NEGATE": arity == 1,
            "ABS": arity == 1,
            "MIN": arity >= 2,
            "MAX": arity >= 2,
            "IF": arity == 3,
            "EQUAL": arity == 2,
            "LESS_THAN": arity == 2,
            "LESS_OR_EQUAL": arity == 2,
            "GREATER_THAN": arity == 2,
            "GREATER_OR_EQUAL": arity == 2,
        }
        if operator not in arity_rules:
            raise FinanceError("EXPRESSION_OPERATOR_FORBIDDEN")
        if not arity_rules[operator]:
            raise FinanceError("EXPRESSION_ARITY_INVALID")
        declared = _validate_signature(
            node.get("value_type"), node.get("unit"), node.get("currency")
        )
        values = [walk(argument, depth + 1) for argument in arguments]
        _validate_operation_signature(str(operator), values, declared)
        return _dummy_value(*declared)

    result = walk(expression, 1)
    if result.value_type not in _NUMERIC_TYPES | {"BOOLEAN"}:
        raise FinanceError("EXPRESSION_TYPE_MISMATCH")


__all__ = ["validate_expression_ast"]
