import unittest

from quantum.finance import (
    FinanceError,
    canonical_hash,
    evaluate_expression,
    evaluate_resolved_rule,
    resolve_rule,
)
from tests.test_b1b_rescue_smoke import context, money_rule, policy, typed


POLICY_OVERSIZED = "1" * 29
GLOBAL_OVERSIZED = "1" * 5001


def integer_literal(value):
    return {
        "kind": "LITERAL",
        "value": value,
        "value_type": "INTEGER",
        "currency": None,
        "unit": "ITEM",
    }


def money_literal(value):
    return {
        "kind": "LITERAL",
        "value": value,
        "value_type": "MONEY",
        "currency": "RUB",
        "unit": "MONEY",
    }


def governed_expression(integer_value):
    return {
        "kind": "OPERATION",
        "operator": "IF",
        "value_type": "MONEY",
        "currency": "RUB",
        "unit": "MONEY",
        "arguments": [
            {
                "kind": "OPERATION",
                "operator": "GREATER_THAN",
                "value_type": "BOOLEAN",
                "currency": None,
                "unit": "BOOLEAN",
                "arguments": [integer_literal(integer_value), integer_literal("0")],
            },
            {
                "kind": "VARIABLE",
                "name": "gross_sales_amount",
                "value_type": "MONEY",
                "currency": "RUB",
                "unit": "MONEY",
            },
            money_literal("0"),
        ],
    }


class B1bIntegerLiteralLimitTests(unittest.TestCase):
    def test_direct_integer_literal_respects_policy_precision(self):
        with self.assertRaises(FinanceError) as error:
            evaluate_expression(integer_literal(POLICY_OVERSIZED), {}, [], policy())
        self.assertEqual(error.exception.code, "ROUNDING_INPUT_PRECISION_EXCEEDED")

    def test_governed_integer_literal_respects_policy_precision(self):
        rule = money_rule()
        rule["expression"] = governed_expression(POLICY_OVERSIZED)
        rule["change_reason"] = "integer literal policy limit regression"
        rule["content_hash"] = canonical_hash(
            rule,
            exclude=frozenset({"content_hash"}),
        )
        resolution = resolve_rule([rule], context())
        with self.assertRaises(FinanceError) as error:
            evaluate_resolved_rule(
                resolution,
                [rule],
                {
                    "gross_sales_amount": typed(
                        "VALID", "100", "MONEY", "MONEY", "RUB"
                    )
                },
                policy(),
            )
        self.assertEqual(error.exception.code, "ROUNDING_INPUT_PRECISION_EXCEEDED")

    def test_integer_literal_global_cap_is_enforced_at_rule_admission(self):
        rule = money_rule()
        rule["expression"] = governed_expression(GLOBAL_OVERSIZED)
        rule["change_reason"] = "integer literal global cap regression"
        rule["content_hash"] = canonical_hash(
            rule,
            exclude=frozenset({"content_hash"}),
        )
        with self.assertRaises(FinanceError) as error:
            resolve_rule([rule], context())
        self.assertEqual(error.exception.code, "ROUNDING_INPUT_PRECISION_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
