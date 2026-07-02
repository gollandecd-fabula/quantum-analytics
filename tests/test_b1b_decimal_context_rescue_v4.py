import unittest
from decimal import getcontext, localcontext

from quantum.finance import FinanceError, canonical_hash, evaluate_expression, resolve_rule
from quantum.finance._rounding import _decimal_context
from tests.test_b1b_rescue_smoke import context, money_rule, policy


def high_precision_policy():
    value = policy()
    value["max_input_precision"] = 40
    value["content_hash"] = canonical_hash(value, exclude=frozenset({"content_hash"}))
    return value


def literal(value, value_type="MONEY", currency="RUB", unit="MONEY"):
    return {
        "kind": "LITERAL",
        "value": value,
        "value_type": value_type,
        "currency": currency,
        "unit": unit,
    }


def operation(operator, value_type, currency, unit, arguments):
    return {
        "kind": "OPERATION",
        "operator": operator,
        "value_type": value_type,
        "currency": currency,
        "unit": unit,
        "arguments": arguments,
    }


class B1bDecimalContextRescueV4Tests(unittest.TestCase):
    def test_decimal_context_clamps_ambient_precision(self):
        governed = high_precision_policy()
        budget = 3
        work_scale = max(
            governed["max_input_scale"],
            governed["calculation_scale"],
            governed["money_scale"],
            governed["rate_scale"],
            governed["presentation_scale"],
        )
        expected = governed["max_input_precision"] * budget + work_scale + 8
        with localcontext() as ambient:
            ambient.prec = expected * 10
            with _decimal_context(governed, operation_budget=budget):
                self.assertEqual(getcontext().prec, expected)
            self.assertEqual(getcontext().prec, expected * 10)

    def test_oversized_expression_literal_fails_before_resolution(self):
        rule = money_rule()
        rule["expression"] = literal("1" * 1001)
        rule["change_reason"] = "oversized literal regression"
        rule["content_hash"] = canonical_hash(rule, exclude=frozenset({"content_hash"}))
        with self.assertRaises(FinanceError) as error:
            resolve_rule([rule], context())
        self.assertEqual(error.exception.code, "ROUNDING_INPUT_PRECISION_EXCEEDED")

    def test_decimal_operators_preserve_policy_precision(self):
        big = "12345678901234567890123456789"
        one = literal("1")
        added = operation("ADD", "MONEY", "RUB", "MONEY", [literal(big), one])
        factor = literal("2", "DECIMAL", None, "DIMENSIONLESS")
        multiplied = operation("MULTIPLY", "MONEY", "RUB", "MONEY", [added, factor])
        divided = operation("DIVIDE", "MONEY", "RUB", "MONEY", [multiplied, factor])
        result = evaluate_expression(divided, {}, [], high_precision_policy())
        self.assertEqual(result["state"], "VALID")
        self.assertEqual(result["value"], "12345678901234567890123456790.000000")


if __name__ == "__main__":
    unittest.main()
