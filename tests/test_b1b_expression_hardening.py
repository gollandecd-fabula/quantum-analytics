from __future__ import annotations

import unittest

from quantum.finance import (
    FinanceError,
    evaluate_expression,
    evaluate_resolved_rule,
    resolve_rule,
)

from tests.b1b_helpers import context, policy, rule_document, typed


class B1bExpressionHardeningTests(unittest.TestCase):
    def test_invalid_variable_name_is_rejected_at_direct_and_rule_boundaries(self) -> None:
        expression = {
            "kind": "VARIABLE",
            "name": "Bad Name",
            "value_type": "MONEY",
            "currency": "EUR",
            "unit": "MONEY",
        }
        with self.assertRaisesRegex(FinanceError, "EXPRESSION_SCHEMA_INVALID"):
            evaluate_expression(
                expression,
                {},
                ["gross_sales_amount"],
                policy(),
            )

        rule = rule_document(
            method="SAFE_EXPRESSION",
            expression=expression,
        )
        with self.assertRaisesRegex(FinanceError, "EXPRESSION_SCHEMA_INVALID"):
            resolve_rule([rule], context())

    def test_boolean_arithmetic_is_rejected_before_python_operators(self) -> None:
        boolean_literal = {
            "kind": "LITERAL",
            "value": True,
            "value_type": "BOOLEAN",
            "currency": None,
            "unit": "BOOLEAN",
        }
        expression = {
            "kind": "OPERATION",
            "operator": "ADD",
            "value_type": "BOOLEAN",
            "currency": None,
            "unit": "BOOLEAN",
            "arguments": [dict(boolean_literal), dict(boolean_literal)],
        }
        with self.assertRaisesRegex(FinanceError, "EXPRESSION_TYPE_MISMATCH"):
            evaluate_expression(expression, {}, [], policy())

        rule = rule_document(
            method="SAFE_EXPRESSION",
            expression=expression,
        )
        with self.assertRaisesRegex(FinanceError, "EXPRESSION_TYPE_MISMATCH"):
            resolve_rule([rule], context())

    def test_safe_expression_result_contains_rule_and_trace_provenance(self) -> None:
        expression = {
            "kind": "VARIABLE",
            "name": "gross_sales_amount",
            "value_type": "MONEY",
            "currency": "EUR",
            "unit": "MONEY",
        }
        rule = rule_document(
            method="SAFE_EXPRESSION",
            expression=expression,
        )
        resolution = resolve_rule([rule], context())
        result = evaluate_resolved_rule(
            resolution,
            [rule],
            {
                "gross_sales_amount": typed(
                    "100",
                    value_type="MONEY",
                    unit="MONEY",
                    currency="EUR",
                ),
                "tax_rate": typed(
                    "0.10",
                    value_type="RATE",
                    unit="RATE",
                ),
            },
            policy(),
        )
        self.assertEqual(result["state"], "VALID")
        self.assertIn("gross_sales_amount", result["source_ids"])
        self.assertIn(rule["content_hash"], result["source_ids"])
        self.assertIn(resolution["trace_id"], result["source_ids"])
        self.assertEqual(result["source_ids"], sorted(set(result["source_ids"])))


if __name__ == "__main__":
    unittest.main()
