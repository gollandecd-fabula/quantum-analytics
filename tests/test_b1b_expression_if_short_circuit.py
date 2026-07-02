from __future__ import annotations

import unittest

from quantum.finance import evaluate_expression
from tests.test_b1b_rescue_smoke import policy


def literal(value: str | bool, value_type: str, unit: str) -> dict:
    return {
        "kind": "LITERAL",
        "value": value,
        "value_type": value_type,
        "unit": unit,
        "currency": None,
    }


def variable(name: str, value_type: str, unit: str) -> dict:
    return {
        "kind": "VARIABLE",
        "name": name,
        "value_type": value_type,
        "unit": unit,
        "currency": None,
    }


def operation(operator: str, arguments: list[dict], value_type: str = "DECIMAL", unit: str = "DIMENSIONLESS") -> dict:
    return {
        "kind": "OPERATION",
        "operator": operator,
        "value_type": value_type,
        "unit": unit,
        "currency": None,
        "arguments": arguments,
    }


def branch(condition: bool, first: dict, second: dict) -> dict:
    return operation(
        "IF",
        [literal(condition, "BOOLEAN", "BOOLEAN"), first, second],
    )


def division_by_zero() -> dict:
    return operation(
        "DIVIDE",
        [
            literal("1", "DECIMAL", "DIMENSIONLESS"),
            literal("0", "DECIMAL", "DIMENSIONLESS"),
        ],
    )


def typed(value: str | bool, value_type: str, unit: str, state: str = "VALID") -> dict:
    return {
        "state": state,
        "value": value if state == "VALID" else None,
        "value_type": value_type,
        "unit": unit,
        "currency": None,
        "reason_code": None if state == "VALID" else "NOT_SELECTED",
        "source_ids": [],
    }


class ExpressionIfShortCircuitTests(unittest.TestCase):
    def evaluate(self, expression: dict, variables: dict | None = None, dependencies: list[str] | None = None) -> dict:
        return evaluate_expression(expression, variables or {}, dependencies or [], policy())

    def test_false_condition_skips_first_branch_failure(self) -> None:
        result = self.evaluate(
            branch(
                False,
                division_by_zero(),
                literal("42", "DECIMAL", "DIMENSIONLESS"),
            )
        )
        self.assertEqual(result["state"], "VALID")
        self.assertEqual(result["value"], "42.0000")

    def test_true_condition_skips_second_branch_failure(self) -> None:
        result = self.evaluate(
            branch(
                True,
                literal("42", "DECIMAL", "DIMENSIONLESS"),
                division_by_zero(),
            )
        )
        self.assertEqual(result["state"], "VALID")
        self.assertEqual(result["value"], "42.0000")

    def test_sources_include_condition_and_selected_value_only(self) -> None:
        expression = operation(
            "IF",
            [
                variable("flag", "BOOLEAN", "BOOLEAN"),
                variable("chosen", "DECIMAL", "DIMENSIONLESS"),
                variable("other", "DECIMAL", "DIMENSIONLESS"),
            ],
        )
        result = self.evaluate(
            expression,
            {
                "flag": typed(True, "BOOLEAN", "BOOLEAN"),
                "chosen": typed("42", "DECIMAL", "DIMENSIONLESS"),
                "other": typed("0", "DECIMAL", "DIMENSIONLESS", "BLOCKED"),
            },
            ["flag", "chosen", "other"],
        )
        self.assertEqual(result["state"], "VALID")
        self.assertEqual(result["source_ids"], ["chosen", "flag"])


if __name__ == "__main__":
    unittest.main()
