from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from ._common import (
    FinanceError, _INTEGER_RE, _MAX_EXPRESSION_ARGUMENTS,
    _MAX_EXPRESSION_DEPENDENCIES, _NUMERIC_TYPES,
    _MAX_EXPRESSION_DEPTH, _MAX_EXPRESSION_NODES, _Value, _is_nonempty_string,
    _make_nonvalid, _make_valid, _parse_decimal, _value_from_dict,
    _value_to_dict, _validate_signature,
)
from ._rounding import (
    _input_decimal, _normalize_value, _propagate, _quantize,
    validate_rounding_policy,
)


def _signature(value: _Value) -> tuple[str, str, str | None]:
    return value.value_type, value.unit, value.currency


def _require_compatible(values: Sequence[_Value], code_prefix: str = "EXPRESSION") -> None:
    if not values:
        raise FinanceError(f"{code_prefix}_ARITY_INVALID")
    first = _signature(values[0])
    for value in values[1:]:
        if value.value_type != first[0]:
            raise FinanceError(f"{code_prefix}_TYPE_MISMATCH")
        if value.unit != first[1]:
            raise FinanceError(f"{code_prefix}_UNIT_MISMATCH")
        if value.currency != first[2]:
            raise FinanceError(f"{code_prefix}_CURRENCY_MISMATCH")


def evaluate_expression(
    expression: object,
    variables: Mapping[str, Mapping[str, Any]],
    dependencies: Sequence[str],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    validated_policy = validate_rounding_policy(policy)
    if (
        not isinstance(dependencies, Sequence)
        or isinstance(dependencies, (str, bytes))
        or len(dependencies) > _MAX_EXPRESSION_DEPENDENCIES
        or len(dependencies) != len(set(dependencies))
        or any(not _is_nonempty_string(item) for item in dependencies)
    ):
        raise FinanceError("EXPRESSION_DEPENDENCY_UNDECLARED")
    dependency_set = set(dependencies)
    if set(variables) - dependency_set:
        raise FinanceError("EXPRESSION_DEPENDENCY_UNDECLARED")
    typed_variables = {
        name: _normalize_value(
            _value_from_dict(value, source_id=name), validated_policy
        )
        for name, value in variables.items()
    }
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
                return _make_valid(raw, value_type=value_type, unit=unit, currency=currency)
            if value_type == "INTEGER":
                if not isinstance(raw, str) or _INTEGER_RE.fullmatch(raw) is None:
                    raise FinanceError("EXPRESSION_TYPE_MISMATCH")
                return _make_valid(int(raw), value_type=value_type, unit=unit, currency=currency)
            parsed = _input_decimal(raw, validated_policy, code="EXPRESSION_NON_FINITE_LITERAL")
            return _make_valid(parsed, value_type=value_type, unit=unit, currency=currency)

        if kind == "VARIABLE":
            if set(node) != {"kind", "name", "value_type", "currency", "unit"}:
                raise FinanceError("EXPRESSION_SCHEMA_INVALID")
            name = node.get("name")
            if not _is_nonempty_string(name) or name not in dependency_set:
                raise FinanceError("EXPRESSION_DEPENDENCY_UNDECLARED")
            if name not in typed_variables:
                raise FinanceError("EXPRESSION_VARIABLE_UNKNOWN")
            declared = _validate_signature(
                node.get("value_type"), node.get("unit"), node.get("currency")
            )
            actual = typed_variables[str(name)]
            if declared[0] != actual.value_type:
                raise FinanceError("EXPRESSION_TYPE_MISMATCH")
            if declared[1] != actual.unit:
                raise FinanceError("EXPRESSION_UNIT_MISMATCH")
            if declared[2] != actual.currency:
                raise FinanceError("EXPRESSION_CURRENCY_MISMATCH")
            return actual

        if kind != "OPERATION":
            raise FinanceError("EXPRESSION_SCHEMA_INVALID")
        required = {"kind", "operator", "value_type", "currency", "unit", "arguments"}
        if set(node) != required:
            raise FinanceError("EXPRESSION_SCHEMA_INVALID")
        operator = node.get("operator")
        arguments = node.get("arguments")
        if (
            not isinstance(arguments, list)
            or len(arguments) > _MAX_EXPRESSION_ARGUMENTS
        ):
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
        declared_type, declared_unit, declared_currency = _validate_signature(
            node.get("value_type"), node.get("unit"), node.get("currency")
        )
        values = [walk(argument, depth + 1) for argument in arguments]
        propagated = _propagate(
            values,
            value_type=declared_type,
            unit=declared_unit,
            currency=declared_currency,
        )
        if propagated is not None:
            return propagated

        if operator in {"ADD", "SUBTRACT", "MIN", "MAX"}:
            _require_compatible(values)
            if _signature(values[0]) != (declared_type, declared_unit, declared_currency):
                raise FinanceError("EXPRESSION_TYPE_MISMATCH")
            raw_values = [value.value for value in values]
            if operator == "ADD":
                result = raw_values[0]
                for item in raw_values[1:]:
                    result = result + item  # type: ignore[operator]
            elif operator == "SUBTRACT":
                result = raw_values[0] - raw_values[1]  # type: ignore[operator]
            elif operator == "MIN":
                result = min(raw_values)
            else:
                result = max(raw_values)
            return _make_valid(
                result,  # type: ignore[arg-type]
                value_type=declared_type,
                unit=declared_unit,
                currency=declared_currency,
                source_ids=tuple(source for value in values for source in value.source_ids),
            )

        if operator in {"NEGATE", "ABS"}:
            value = values[0]
            if value.value_type not in _NUMERIC_TYPES or _signature(value) != (
                declared_type, declared_unit, declared_currency
            ):
                raise FinanceError("EXPRESSION_TYPE_MISMATCH")
            assert isinstance(value.value, (Decimal, int))
            result = -value.value if operator == "NEGATE" else abs(value.value)
            return _make_valid(
                result,
                value_type=declared_type,
                unit=declared_unit,
                currency=declared_currency,
                source_ids=value.source_ids,
            )

        if operator == "MULTIPLY":
            left, right = values
            pair = (left.value_type, right.value_type)
            if pair == ("MONEY", "RATE"):
                if right.unit != "RATE":
                    raise FinanceError("EXPRESSION_UNIT_MISMATCH")
                result_signature = ("MONEY", left.unit, left.currency)
            elif pair == ("RATE", "MONEY"):
                if left.unit != "RATE":
                    raise FinanceError("EXPRESSION_UNIT_MISMATCH")
                result_signature = ("MONEY", right.unit, right.currency)
            elif pair == ("MONEY", "DECIMAL"):
                if right.unit != "DIMENSIONLESS":
                    raise FinanceError("EXPRESSION_UNIT_MISMATCH")
                result_signature = ("MONEY", left.unit, left.currency)
            elif pair == ("DECIMAL", "MONEY"):
                if left.unit != "DIMENSIONLESS":
                    raise FinanceError("EXPRESSION_UNIT_MISMATCH")
                result_signature = ("MONEY", right.unit, right.currency)
            elif pair == ("DECIMAL", "DECIMAL"):
                if left.unit != "DIMENSIONLESS" or right.unit != "DIMENSIONLESS":
                    raise FinanceError("EXPRESSION_UNIT_MISMATCH")
                result_signature = ("DECIMAL", "DIMENSIONLESS", None)
            else:
                raise FinanceError("EXPRESSION_TYPE_MISMATCH")
            if result_signature != (declared_type, declared_unit, declared_currency):
                raise FinanceError("EXPRESSION_TYPE_MISMATCH")
            assert isinstance(left.value, Decimal) and isinstance(right.value, Decimal)
            return _make_valid(
                left.value * right.value,
                value_type=declared_type,
                unit=declared_unit,
                currency=declared_currency,
                source_ids=tuple((*left.source_ids, *right.source_ids)),
            )

        if operator == "DIVIDE":
            left, right = values
            assert isinstance(left.value, Decimal) and isinstance(right.value, Decimal)
            if right.value == 0:
                return _make_nonvalid(
                    "BLOCKED",
                    value_type=declared_type,
                    unit=declared_unit,
                    currency=declared_currency,
                    reason_code="EXPRESSION_DIVISION_BY_ZERO",
                    source_ids=tuple((*left.source_ids, *right.source_ids)),
                )
            pair = (left.value_type, right.value_type)
            if pair == ("MONEY", "MONEY"):
                if left.currency != right.currency:
                    raise FinanceError("EXPRESSION_CURRENCY_MISMATCH")
                if left.unit != right.unit:
                    raise FinanceError("EXPRESSION_UNIT_MISMATCH")
                result_signature = ("DECIMAL", "DIMENSIONLESS", None)
            elif pair == ("MONEY", "DECIMAL"):
                if right.unit != "DIMENSIONLESS":
                    raise FinanceError("EXPRESSION_UNIT_MISMATCH")
                result_signature = ("MONEY", left.unit, left.currency)
            elif pair == ("DECIMAL", "DECIMAL"):
                if left.unit != "DIMENSIONLESS" or right.unit != "DIMENSIONLESS":
                    raise FinanceError("EXPRESSION_UNIT_MISMATCH")
                result_signature = ("DECIMAL", "DIMENSIONLESS", None)
            else:
                raise FinanceError("EXPRESSION_TYPE_MISMATCH")
            if result_signature != (declared_type, declared_unit, declared_currency):
                raise FinanceError("EXPRESSION_TYPE_MISMATCH")
            return _make_valid(
                left.value / right.value,
                value_type=declared_type,
                unit=declared_unit,
                currency=declared_currency,
                source_ids=tuple((*left.source_ids, *right.source_ids)),
            )

        if operator == "IF":
            condition, true_value, false_value = values
            if condition.value_type != "BOOLEAN":
                raise FinanceError("EXPRESSION_TYPE_MISMATCH")
            _require_compatible([true_value, false_value])
            if _signature(true_value) != (declared_type, declared_unit, declared_currency):
                raise FinanceError("EXPRESSION_TYPE_MISMATCH")
            assert isinstance(condition.value, bool)
            selected = true_value if condition.value else false_value
            return _make_valid(
                selected.value,  # type: ignore[arg-type]
                value_type=declared_type,
                unit=declared_unit,
                currency=declared_currency,
                source_ids=tuple(
                    (*condition.source_ids, *true_value.source_ids, *false_value.source_ids)
                ),
            )

        left, right = values
        _require_compatible(values)
        if (declared_type, declared_unit, declared_currency) != ("BOOLEAN", "BOOLEAN", None):
            raise FinanceError("EXPRESSION_TYPE_MISMATCH")
        if operator != "EQUAL" and left.value_type == "BOOLEAN":
            raise FinanceError("EXPRESSION_TYPE_MISMATCH")
        if operator == "EQUAL":
            result = left.value == right.value
        elif operator == "LESS_THAN":
            result = left.value < right.value  # type: ignore[operator]
        elif operator == "LESS_OR_EQUAL":
            result = left.value <= right.value  # type: ignore[operator]
        elif operator == "GREATER_THAN":
            result = left.value > right.value  # type: ignore[operator]
        else:
            result = left.value >= right.value  # type: ignore[operator]
        return _make_valid(
            bool(result),
            value_type="BOOLEAN",
            unit="BOOLEAN",
            currency=None,
            source_ids=tuple((*left.source_ids, *right.source_ids)),
        )

    result = walk(expression, 1)
    if result.state == "VALID" and result.value_type in {"MONEY", "DECIMAL", "RATE"}:
        assert isinstance(result.value, Decimal)
        rounded, scale = _quantize(
            result.value,
            validated_policy,
            "RULE_COMPONENT_RESULT",
            result.value_type,
        )
        return _value_to_dict(
            _make_valid(
                rounded,
                value_type=result.value_type,
                unit=result.unit,
                currency=result.currency,
                source_ids=result.source_ids,
            ),
            scale=scale,
        )
    return _value_to_dict(result)
