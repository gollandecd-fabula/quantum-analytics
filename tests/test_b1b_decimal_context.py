import unittest
from copy import deepcopy

from quantum.finance import (
    calculate,
    canonical_hash,
    evaluate_expression,
    evaluate_resolved_rule,
    resolve_rule,
)
from tests.test_b1b_rescue_smoke import context, money_rule, policy, typed


BIG = "12345678901234567890123456789"
BIG_PLUS_ONE = "12345678901234567890123456790.000000"


def high_precision_policy():
    value = policy()
    value["max_input_precision"] = 40
    value["content_hash"] = canonical_hash(
        value, exclude=frozenset({"content_hash"})
    )
    return value


def money_literal(value):
    return {
        "kind": "LITERAL",
        "value": value,
        "value_type": "MONEY",
        "currency": "RUB",
        "unit": "MONEY",
    }


def decimal_literal(value):
    return {
        "kind": "LITERAL",
        "value": value,
        "value_type": "DECIMAL",
        "currency": None,
        "unit": "DIMENSIONLESS",
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


class B1bDecimalContextTests(unittest.TestCase):
    def test_kernel_preserves_policy_precision_across_arithmetic(self):
        zero = typed("VALID", "0", "MONEY", "MONEY", "RUB")
        inputs = {
            "gross_sales_units": typed("VALID", "3", "INTEGER", "ITEM"),
            "returned_units": typed("VALID", "0", "INTEGER", "ITEM"),
            "gross_sales_amount": typed("VALID", BIG, "MONEY", "MONEY", "RUB"),
            "discounts_amount": deepcopy(zero),
            "subsidies_amount": deepcopy(zero),
            "marketplace_commission_amount": deepcopy(zero),
            "forward_logistics_amount": deepcopy(zero),
            "reverse_logistics_amount": deepcopy(zero),
            "storage_amount": deepcopy(zero),
            "advertising_amount": deepcopy(zero),
            "fines_withholdings_amount": deepcopy(zero),
        }
        request = {
            "calculation_id": "high-precision-kernel",
            "organization_id": "org-1",
            "mode": "ACTUAL",
            "scenario_id": None,
            "calculated_at": "2026-07-01T00:00:00Z",
            "profile_ref": {"id": "p", "version": 1, "content_hash": "0" * 64},
            "profile_status": "PILOT",
            "rounding_policy": high_precision_policy(),
            "currency": "RUB",
            "inputs": inputs,
            "cost_per_unit": typed(
                "VALID",
                "123456789012345678901234567.89",
                "MONEY",
                "MONEY_PER_ITEM",
                "RUB",
            ),
            "other_expense_components": [
                {
                    "component_id": "other-per-unit",
                    "value": typed(
                        "VALID",
                        "100000000000000000000000000.01",
                        "MONEY",
                        "MONEY_PER_ITEM",
                        "RUB",
                    ),
                }
            ],
            "tax_rate": typed("VALID", "0.06", "RATE", "RATE"),
            "tax_base_metric_id": "gross_sales_amount",
        }
        results = calculate(request)["results"]
        expected = {
            "product_cost_amount": "370370367037037036703703703.67",
            "other_expense_amount": "300000000000000000000000000.03",
            "tax_amount": "740740734074074073407407407.34",
            "net_marketplace_income_amount": "12345678901234567890123456789.00",
            "net_profit_amount": "10934567800123456780012345677.96",
            "profit_per_sold_unit": "3644855933374485593337448559.32",
        }
        for metric_id, value in expected.items():
            self.assertEqual(results[metric_id]["state"], "VALID", metric_id)
            self.assertEqual(results[metric_id]["value"], value, metric_id)

    def test_direct_expression_preserves_precision_for_all_decimal_operators(self):
        added = operation(
            "ADD", "MONEY", "RUB", "MONEY", [money_literal(BIG), money_literal("1")]
        )
        multiplied = operation(
            "MULTIPLY", "MONEY", "RUB", "MONEY", [added, decimal_literal("2")]
        )
        divided = operation(
            "DIVIDE", "MONEY", "RUB", "MONEY", [multiplied, decimal_literal("2")]
        )
        negated = operation("NEGATE", "MONEY", "RUB", "MONEY", [divided])
        expression = operation("ABS", "MONEY", "RUB", "MONEY", [negated])
        result = evaluate_expression(expression, {}, [], high_precision_policy())
        self.assertEqual((result["state"], result["value"]), ("VALID", BIG_PLUS_ONE))

    def test_resolved_rule_preserves_precision(self):
        rule = money_rule()
        rule["expression"] = operation(
            "ADD",
            "MONEY",
            "RUB",
            "MONEY",
            [
                {
                    "kind": "VARIABLE",
                    "name": "gross_sales_amount",
                    "value_type": "MONEY",
                    "currency": "RUB",
                    "unit": "MONEY",
                },
                money_literal("1"),
            ],
        )
        rule["change_reason"] = "high precision regression"
        rule["content_hash"] = canonical_hash(
            rule, exclude=frozenset({"content_hash"})
        )
        resolution = resolve_rule([rule], context())
        result = evaluate_resolved_rule(
            resolution,
            [rule],
            {"gross_sales_amount": typed("VALID", BIG, "MONEY", "MONEY", "RUB")},
            high_precision_policy(),
        )
        self.assertEqual((result["state"], result["value"]), ("VALID", BIG_PLUS_ONE))


if __name__ == "__main__":
    unittest.main()
