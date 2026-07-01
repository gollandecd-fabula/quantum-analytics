from __future__ import annotations

import unittest

from quantum.finance import canonical_hash, evaluate_expression, evaluate_resolved_rule, resolve_rule
from tests.b1b_helpers import context, policy, rule_document, typed


class B1bDependencyLimitTests(unittest.TestCase):
    def test_missing_dependency_keeps_rule_signature(self) -> None:
        rule = rule_document(
            method="SAFE_EXPRESSION",
            expression={
                "kind": "VARIABLE",
                "name": "gross_sales_amount",
                "value_type": "MONEY",
                "currency": "EUR",
                "unit": "MONEY",
            },
        )
        resolution = resolve_rule([rule], context())
        result = evaluate_resolved_rule(
            resolution,
            [rule],
            {"tax_rate": typed("0.10", value_type="RATE", unit="RATE")},
            policy(),
        )
        self.assertEqual(
            (result["state"], result["value_type"], result["unit"], result["currency"]),
            ("UNAVAILABLE", "MONEY", "MONEY", "EUR"),
        )
        self.assertIn(rule["content_hash"], result["source_ids"])
        self.assertIn(resolution["trace_id"], result["source_ids"])

    def test_dependency_limit_accepts_128(self) -> None:
        dependencies = [f"metric_{index:03d}" for index in range(128)]
        expression = {
            "kind": "LITERAL",
            "value": "1",
            "value_type": "DECIMAL",
            "currency": None,
            "unit": "DIMENSIONLESS",
        }
        self.assertEqual(
            evaluate_expression(expression, {}, dependencies, policy())["state"],
            "VALID",
        )
        rule = rule_document(method="SAFE_EXPRESSION", expression=expression)
        rule["dependencies"] = dependencies
        rule["content_hash"] = canonical_hash(rule, exclude=frozenset({"content_hash"}))
        self.assertEqual(resolve_rule([rule], context())["state"], "VALID")


if __name__ == "__main__":
    unittest.main()
